"""Schema-validated server-local routing for the workflow namespace."""

from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from unreal_mcp.contracts import ErrorCode
from unreal_mcp.dispatchers._catalog import CATALOG
from unreal_mcp.errors import error_result
from unreal_mcp.workflows.models import ActionInvocation
from unreal_mcp.workflows.planner import WorkflowPlanningError


class WorkflowHandler:
    def __init__(
        self,
        registry,
        planner,
        executor,
        store,
        *,
        gameplay_planner=None,
        gameplay_verifier=None,
    ):
        self.registry = registry
        self.planner = planner
        self.executor = executor
        self.store = store
        self.gameplay_planner = gameplay_planner
        self.gameplay_verifier = gameplay_verifier

    async def handle(
        self,
        action: str,
        params: dict[str, Any],
        progress=None,
    ) -> dict[str, Any]:
        if action not in CATALOG.get("workflow", {}):
            return self._error(
                ErrorCode.UNKNOWN_ACTION,
                f"Unknown workflow action '{action}'",
                path="action",
                hint="Call workflow with action='list_actions'.",
                details={
                    "available_actions": sorted(
                        CATALOG.get("workflow", {})
                    )
                },
            )

        spec = self.registry.get("workflow", action)
        schema_error = next(
            Draft202012Validator(spec.input_schema).iter_errors(params),
            None,
        )
        if schema_error is not None:
            return self._schema_error(action, params, spec, schema_error)

        try:
            if action == "plan":
                return await self._plan(params)
            if action == "apply":
                return await self._apply(params, progress)
            if action == "get":
                return await self._get(params["plan_id"])
            if action == "cancel":
                return await self._cancel(params["plan_id"])
            if action == "undo":
                result = await self.executor.undo(
                    params["plan_id"], params["undo_token"]
                )
                return result.model_dump(mode="json")
            if action == "plan_gameplay_foundation":
                return await self._foundation(
                    self.gameplay_planner, params.get("spec", {})
                )
            if action == "verify_gameplay_foundation":
                return await self._foundation(
                    self.gameplay_verifier, params.get("spec", {})
                )
        except WorkflowPlanningError as exc:
            return exc.result.model_dump(mode="json")
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self._error(
                ErrorCode.INVALID_INPUT,
                str(exc),
                path="params",
                hint=(
                    f"Call util.describe_action for workflow.{action}, "
                    "correct params, and retry."
                ),
            )
        except Exception:
            return self._error(
                ErrorCode.INTERNAL_ERROR,
                f"Unexpected failure while running workflow.{action}",
                path="action",
                hint="Check the server log using this trace_id, then retry.",
            )

        return self._error(
            ErrorCode.UNKNOWN_ACTION,
            f"Workflow action '{action}' has no handler",
            path="action",
            hint="Update the server-local workflow handler.",
        )

    async def _plan(self, params: dict[str, Any]) -> dict[str, Any]:
        operations = [
            ActionInvocation.model_validate(operation)
            for operation in params["operations"]
        ]
        nested = [
            (index, operation)
            for index, operation in enumerate(operations)
            if operation.domain == "workflow"
        ]
        if nested:
            index, operation = nested[0]
            return self._error(
                ErrorCode.INVALID_INPUT,
                "Workflow operations cannot invoke the workflow domain",
                path=f"params.operations.{index}.domain",
                hint=(
                    f"Replace nested workflow.{operation.action} with its "
                    "underlying Unreal actions."
                ),
            )
        plan = await self.planner.plan(
            operations,
            allow_non_undoable=params.get("allow_non_undoable", False),
        )
        return {
            "success": True,
            "status": plan.status.value,
            "summary": "Workflow plan created and awaiting confirmation.",
            "data": {
                "workflow_id": plan.id,
                "confirmation_token": plan.confirmation_token,
                "plan": plan.model_dump(mode="json"),
            },
            "changes": [
                change.model_dump(mode="json")
                for change in plan.predicted_changes
            ],
            "warnings": [],
            "errors": [],
            "next_actions": [
                {
                    "domain": "workflow",
                    "action": "apply",
                    "params": {
                        "plan_id": plan.id,
                        "confirmation_token": plan.confirmation_token,
                    },
                }
            ],
        }

    async def _apply(
        self, params: dict[str, Any], progress
    ) -> dict[str, Any]:
        plan_id = params["plan_id"]
        token = params["confirmation_token"]
        if params.get("wait_for_completion", False):
            result = await self.executor.run(plan_id, token, progress)
            return result.model_dump(mode="json")
        await self.executor.start(plan_id, token)
        return {
            "success": True,
            "status": "running",
            "summary": "Workflow execution started.",
            "data": {"workflow_id": plan_id},
            "changes": [],
            "warnings": [],
            "errors": [],
            "next_actions": [
                {
                    "domain": "workflow",
                    "action": "get",
                    "params": {"plan_id": plan_id},
                }
            ],
        }

    async def _get(self, plan_id: str) -> dict[str, Any]:
        plan = await self.store.get(plan_id)
        return {
            "success": True,
            "status": plan.status.value,
            "summary": "Workflow runtime state loaded.",
            "data": {"workflow": plan.model_dump(mode="json")},
            "changes": [],
            "warnings": [],
            "errors": [],
            "next_actions": [],
        }

    async def _cancel(self, plan_id: str) -> dict[str, Any]:
        if not await self.executor.cancel(plan_id):
            return self._error(
                ErrorCode.CONFLICT,
                "Workflow is not currently running",
                path="params.plan_id",
                hint="Call workflow.get to inspect its current status.",
            )
        return {
            "success": True,
            "status": "cancellation_requested",
            "summary": "Workflow cancellation was requested.",
            "data": {"workflow_id": plan_id},
            "changes": [],
            "warnings": [],
            "errors": [],
            "next_actions": [
                {
                    "domain": "workflow",
                    "action": "get",
                    "params": {"plan_id": plan_id},
                }
            ],
        }

    async def _foundation(self, hook, spec: dict[str, Any]) -> dict[str, Any]:
        if hook is None:
            return self._error(
                ErrorCode.UE_VERSION_UNSUPPORTED,
                "Gameplay foundation authoring is not installed",
                path="action",
                hint=(
                    "Complete the Blueprint authoring stage before using "
                    "this workflow branch."
                ),
                details={"capability": "gameplay_foundation_v1"},
            )
        return await hook(spec)

    @classmethod
    def _schema_error(cls, action, params, spec, error) -> dict[str, Any]:
        if error.validator == "required":
            missing = next(
                name
                for name in error.validator_value
                if name not in error.instance
            )
            message = f"{missing} is required"
            base_path = [*error.absolute_path, missing]
        elif error.validator == "additionalProperties":
            allowed = set(
                error.schema.get("properties", spec.input_schema.get("properties", {}))
            )
            unexpected = sorted(set(error.instance) - allowed)[0]
            message = f"{unexpected} is not an allowed parameter"
            base_path = [*error.absolute_path, unexpected]
        else:
            message = error.message
            base_path = list(error.absolute_path)
        suffix = ".".join(str(part) for part in base_path)
        path = f"params.{suffix}" if suffix else "params"
        return cls._error(
            ErrorCode.INVALID_INPUT,
            message,
            path=path,
            hint=(
                f"Call util.describe_action for workflow.{action}, correct "
                "params, and retry."
            ),
            details={"validator": error.validator},
        )

    @staticmethod
    def _error(
        code: ErrorCode,
        message: str,
        *,
        path: str,
        hint: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return error_result(
            code=code,
            message=message,
            path=path,
            retryable=code in {
                ErrorCode.INVALID_INPUT,
                ErrorCode.UE_VERSION_UNSUPPORTED,
            },
            hint=hint,
            details=details,
        ).model_dump(mode="json")

