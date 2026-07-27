"""Schema-validating, dependency-aware workflow planning and stale checks."""

from collections import defaultdict
from datetime import timedelta
import heapq
from secrets import token_bytes
from typing import Protocol
from uuid import uuid4

from jsonschema import Draft202012Validator

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import Effect, ErrorCode, ToolResult
from unreal_mcp.errors import error_result
from unreal_mcp.workflows.models import (
    ActionInvocation,
    AssetFingerprint,
    ChangeRecord,
    PlanStep,
    WorkflowPlan,
    WorkflowStatus,
)
from unreal_mcp.workflows.store import WorkflowStore
from unreal_mcp.workflows.tokens import TokenService


class EditorContextProvider(Protocol):
    async def get_identity(self) -> dict: ...

    async def get_fingerprints(
        self, asset_paths: list[str]
    ) -> dict[str, AssetFingerprint | dict]: ...


class WorkflowPlanningError(ValueError):
    def __init__(self, result: ToolResult):
        self.result = result
        super().__init__(result.summary)


class WorkflowPlanner:
    def __init__(
        self,
        registry,
        context: EditorContextProvider,
        *,
        token_service: TokenService | None = None,
        store: WorkflowStore | None = None,
        safety_mode: SafetyMode = SafetyMode.COMPATIBLE,
    ):
        self.registry = registry
        self.context = context
        self.tokens = token_service or TokenService(
            secret=token_bytes(32), ttl=timedelta(minutes=10)
        )
        self.store = store or WorkflowStore()
        self.safety_mode = safety_mode

    async def plan(
        self,
        operations: list[ActionInvocation],
        *,
        allow_non_undoable: bool = False,
    ) -> WorkflowPlan:
        if not operations:
            raise ValueError("workflow requires at least one operation")
        ordered = self._order_and_validate(operations)
        steps: list[PlanStep] = []
        all_asset_paths: set[str] = set()
        non_undoable: list[str] = []

        for invocation in ordered:
            spec = self.registry.get(invocation.domain, invocation.action)
            schema_error = next(
                Draft202012Validator(spec.input_schema).iter_errors(
                    invocation.params
                ),
                None,
            )
            if schema_error is not None:
                raise ValueError(
                    f"step '{invocation.id}' has invalid params: {schema_error.message}"
                )
            asset_paths = self._extract_asset_paths(spec.input_schema, invocation.params)
            all_asset_paths.update(asset_paths)
            if spec.effect is Effect.READ:
                rollback_mode = "none"
            elif spec.supports_undo:
                rollback_mode = "transaction"
            else:
                rollback_mode = "none"
                non_undoable.append(invocation.id)
            steps.append(
                PlanStep(
                    invocation=invocation,
                    rollback_mode=rollback_mode,
                    effect=spec.effect,
                    risk=spec.risk,
                    asset_paths=asset_paths,
                )
            )

        if non_undoable and not allow_non_undoable:
            result = error_result(
                code=ErrorCode.CONFIRMATION_REQUIRED,
                message="Workflow contains non-undoable steps",
                path="allow_non_undoable",
                retryable=True,
                hint="Review non_undoable_steps, then plan again with allow_non_undoable=true.",
                details={"non_undoable_steps": non_undoable},
            )
            raise WorkflowPlanningError(result)

        identity = await self.context.get_identity()
        required_identity = {"project_id", "editor_session_id", "current_map"}
        missing_identity = sorted(required_identity - set(identity))
        if missing_identity:
            raise ValueError(f"editor context missing fields: {missing_identity}")
        fingerprint_values = await self.context.get_fingerprints(
            sorted(all_asset_paths)
        )
        fingerprints = {
            path: AssetFingerprint.model_validate(
                fingerprint_values.get(
                    path, AssetFingerprint(asset_path=path, exists=False)
                )
            )
            for path in sorted(all_asset_paths)
        }
        predicted_changes = self._predict_changes(steps, fingerprints)
        plan = WorkflowPlan(
            id=uuid4().hex,
            status=WorkflowStatus.AWAITING_CONFIRMATION,
            safety_mode=self.safety_mode,
            project_id=identity["project_id"],
            editor_session_id=identity["editor_session_id"],
            current_map=identity["current_map"],
            allow_non_undoable=allow_non_undoable,
            steps=steps,
            asset_fingerprints=fingerprints,
            predicted_changes=predicted_changes,
        )
        plan.confirmation_token = self.tokens.issue_confirmation(
            plan.id, plan.digest()
        )
        await self.store.put(plan)
        return plan.model_copy(deep=True)

    async def verify_preconditions(self, plan: WorkflowPlan) -> ToolResult:
        identity = await self.context.get_identity()
        mismatches = []
        for field in ("project_id", "editor_session_id", "current_map"):
            expected = getattr(plan, field)
            actual = identity.get(field)
            if actual != expected:
                mismatches.append(
                    {"field": field, "expected": expected, "actual": actual}
                )

        current_fingerprints = await self.context.get_fingerprints(
            sorted(plan.asset_fingerprints)
        )
        for path, expected_model in plan.asset_fingerprints.items():
            actual_model = AssetFingerprint.model_validate(
                current_fingerprints.get(
                    path, AssetFingerprint(asset_path=path, exists=False)
                )
            )
            expected = expected_model.model_dump(mode="json")
            actual = actual_model.model_dump(mode="json")
            if actual != expected:
                mismatches.append(
                    {
                        "field": f"asset_fingerprints.{path}",
                        "expected": expected,
                        "actual": actual,
                    }
                )

        if mismatches:
            return error_result(
                code=ErrorCode.PRECONDITION_FAILED,
                message="Workflow preconditions changed after planning",
                path="plan_id",
                hint="Create a new plan against the current editor state.",
                details={"mismatches": mismatches},
            )
        trace_id = uuid4().hex
        return ToolResult(
            success=True,
            status="succeeded",
            summary="Workflow preconditions still match.",
            data={"plan_id": plan.id},
            trace_id=trace_id,
        )

    def _order_and_validate(
        self, operations: list[ActionInvocation]
    ) -> list[ActionInvocation]:
        by_id: dict[str, ActionInvocation] = {}
        for operation in operations:
            if operation.domain == "workflow":
                raise ValueError("nested workflow actions are not allowed")
            if operation.id in by_id:
                raise ValueError(f"duplicate workflow step id '{operation.id}'")
            by_id[operation.id] = operation

        dependents: dict[str, list[str]] = defaultdict(list)
        indegree = {}
        for operation in operations:
            dependencies = set(operation.depends_on)
            missing = sorted(dependencies - set(by_id))
            if missing:
                raise ValueError(
                    f"step '{operation.id}' has unknown dependencies: {missing}"
                )
            indegree[operation.id] = len(dependencies)
            for dependency in dependencies:
                dependents[dependency].append(operation.id)

        ready = [step_id for step_id, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        ordered = []
        while ready:
            step_id = heapq.heappop(ready)
            ordered.append(by_id[step_id])
            for dependent in sorted(dependents[step_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(ordered) != len(operations):
            raise ValueError("workflow dependency cycle detected")
        return ordered

    @staticmethod
    def _extract_asset_paths(schema: dict, params: dict) -> list[str]:
        paths = set()
        for name, property_schema in schema.get("properties", {}).items():
            value = params.get(name)
            if property_schema.get("format") == "unreal-asset-path":
                if isinstance(value, str) and value:
                    paths.add(value)
            elif (
                property_schema.get("type") == "array"
                and property_schema.get("items", {}).get("format")
                == "unreal-asset-path"
                and isinstance(value, list)
            ):
                paths.update(item for item in value if isinstance(item, str) and item)
        return sorted(paths)

    @staticmethod
    def _predict_changes(
        steps: list[PlanStep],
        fingerprints: dict[str, AssetFingerprint],
    ) -> list[ChangeRecord]:
        changes = []
        for step in steps:
            for path in step.asset_paths:
                if step.effect is Effect.READ:
                    kind = "skip"
                elif step.effect is Effect.DESTRUCTIVE:
                    kind = "delete"
                elif not fingerprints[path].exists:
                    kind = "create"
                else:
                    kind = "update"
                changes.append(
                    ChangeRecord(step_id=step.id, kind=kind, asset_path=path)
                )
        return changes
