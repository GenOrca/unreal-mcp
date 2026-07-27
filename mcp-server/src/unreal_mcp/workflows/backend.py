"""Unreal TCP backend for workflow context, leases, steps, and recovery."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from unreal_mcp.core import send_to_unreal
from unreal_mcp.workflows.models import (
    ActionCall,
    ActionInvocation,
    AssetFingerprint,
    PlanStep,
)


Sender = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


@runtime_checkable
class WorkflowBackend(Protocol):
    async def get_identity(self) -> dict[str, Any]: ...

    async def get_fingerprints(
        self, asset_paths: list[str]
    ) -> dict[str, AssetFingerprint]: ...

    async def begin(
        self, transaction_id: str, description: str, total_steps: int
    ) -> dict: ...

    async def heartbeat(
        self,
        transaction_id: str,
        completed_steps: int,
        total_steps: int,
        message: str,
        has_successful_write: bool,
    ) -> dict: ...

    async def execute_step(
        self, transaction_id: str, invocation: ActionInvocation
    ) -> dict: ...

    async def execute_recovery(self, call: ActionCall) -> dict: ...

    async def restore_snapshot(self, step: PlanStep) -> dict: ...

    async def commit(self, transaction_id: str) -> dict: ...

    async def request_cancel(self, transaction_id: str) -> dict: ...

    async def cancel_transaction(self, transaction_id: str) -> dict: ...

    async def rollback_transaction(self, transaction_id: str) -> dict: ...

    async def undo_transaction(self, transaction_id: str) -> dict: ...


class UnrealWorkflowBackend:
    """Routes workflow operations through the internal Unreal action module."""

    _WORKFLOW_MODULE = "UnrealMCPython.workflow_actions"

    def __init__(self, sender: Sender = send_to_unreal):
        self._sender = sender

    async def _workflow(self, action: str, params: dict[str, Any]) -> dict:
        return await self._sender(self._WORKFLOW_MODULE, action, params)

    async def _context(self, asset_paths: list[str]) -> dict:
        return await self._workflow(
            "ue_get_editor_context", {"asset_paths": asset_paths}
        )

    async def get_identity(self) -> dict[str, Any]:
        context = await self._context([])
        return {
            field: context[field]
            for field in ("project_id", "editor_session_id", "current_map")
        }

    async def get_fingerprints(
        self, asset_paths: list[str]
    ) -> dict[str, AssetFingerprint]:
        context = await self._context(asset_paths)
        values = context.get("asset_fingerprints", {})
        return {
            path: AssetFingerprint.model_validate(
                values.get(
                    path, AssetFingerprint(asset_path=path, exists=False)
                )
            )
            for path in asset_paths
        }

    async def begin(
        self,
        transaction_id: str,
        description: str,
        total_steps: int,
    ) -> dict:
        return await self._workflow(
            "ue_begin_transaction",
            {
                "transaction_id": transaction_id,
                "description": description,
                "total_steps": total_steps,
            },
        )

    async def heartbeat(
        self,
        transaction_id: str,
        completed_steps: int,
        total_steps: int,
        message: str,
        has_successful_write: bool,
    ) -> dict:
        return await self._workflow(
            "ue_heartbeat_transaction",
            {
                "transaction_id": transaction_id,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "message": message,
                "has_successful_write": has_successful_write,
            },
        )

    async def execute_step(
        self, transaction_id: str, invocation: ActionInvocation
    ) -> dict:
        return await self._workflow(
            "ue_execute_step",
            {
                "transaction_id": transaction_id,
                "action_module": (
                    f"UnrealMCPython.{invocation.domain}_actions"
                ),
                "action_name": f"ue_{invocation.action}",
                "params": invocation.params,
            },
        )

    async def execute_recovery(self, call: ActionCall) -> dict:
        return await self._sender(
            f"UnrealMCPython.{call.domain}_actions",
            f"ue_{call.action}",
            call.params,
        )

    async def restore_snapshot(self, step: PlanStep) -> dict:
        snapshot = step.pre_state_snapshot or {}
        restore = snapshot.get("restore")
        if not isinstance(restore, dict):
            return {
                "success": False,
                "message": "snapshot has no restore action",
            }
        return await self.execute_recovery(ActionCall.model_validate(restore))

    async def commit(self, transaction_id: str) -> dict:
        return await self._workflow(
            "ue_commit_transaction", {"transaction_id": transaction_id}
        )

    async def request_cancel(self, transaction_id: str) -> dict:
        return await self._workflow(
            "ue_request_cancel", {"transaction_id": transaction_id}
        )

    async def cancel_transaction(self, transaction_id: str) -> dict:
        return await self._workflow(
            "ue_cancel_transaction", {"transaction_id": transaction_id}
        )

    async def rollback_transaction(self, transaction_id: str) -> dict:
        return await self._workflow(
            "ue_rollback_transaction", {"transaction_id": transaction_id}
        )

    async def undo_transaction(self, transaction_id: str) -> dict:
        return await self._workflow(
            "ue_undo_transaction", {"transaction_id": transaction_id}
        )
