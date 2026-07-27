"""Async lock-protected in-memory workflow plan store."""

import asyncio
from typing import Any

from unreal_mcp.workflows.models import (
    AssetFingerprint,
    WorkflowPlan,
    WorkflowStatus,
)


class WorkflowStore:
    def __init__(self):
        self._plans: dict[str, WorkflowPlan] = {}
        self._lock = asyncio.Lock()

    async def put(self, plan: WorkflowPlan) -> WorkflowPlan:
        async with self._lock:
            stored = plan.model_copy(deep=True)
            self._plans[plan.id] = stored
            return stored.model_copy(deep=True)

    async def get(self, plan_id: str) -> WorkflowPlan:
        async with self._lock:
            try:
                return self._plans[plan_id].model_copy(deep=True)
            except KeyError as exc:
                raise KeyError(f"Unknown workflow plan '{plan_id}'") from exc

    async def transition(
        self,
        plan_id: str,
        expected: WorkflowStatus,
        target: WorkflowStatus,
    ) -> WorkflowPlan:
        async with self._lock:
            try:
                plan = self._plans[plan_id]
            except KeyError as exc:
                raise KeyError(f"Unknown workflow plan '{plan_id}'") from exc
            if plan.status is not expected:
                raise ValueError(
                    f"status mismatch for {plan_id}: expected {expected.value}, "
                    f"found {plan.status.value}"
                )
            plan.status = target
            return plan.model_copy(deep=True)

    async def append_step_result(
        self, plan_id: str, result: dict[str, Any]
    ) -> WorkflowPlan:
        async with self._lock:
            try:
                plan = self._plans[plan_id]
            except KeyError as exc:
                raise KeyError(f"Unknown workflow plan '{plan_id}'") from exc
            plan.step_results.append(dict(result))
            return plan.model_copy(deep=True)

    async def update_runtime(
        self,
        plan_id: str,
        *,
        status: WorkflowStatus | None = None,
        transaction_id: str | None = None,
        undo_token: str | None = None,
        post_state_fingerprints: dict[str, AssetFingerprint] | None = None,
        residual_fingerprints: dict[str, AssetFingerprint] | None = None,
        step_result: dict[str, Any] | None = None,
    ) -> WorkflowPlan:
        async with self._lock:
            try:
                plan = self._plans[plan_id]
            except KeyError as exc:
                raise KeyError(f"Unknown workflow plan '{plan_id}'") from exc
            if status is not None:
                plan.status = status
            if transaction_id is not None:
                plan.transaction_id = transaction_id
            if undo_token is not None:
                plan.undo_token = undo_token
            if post_state_fingerprints is not None:
                plan.post_state_fingerprints = {
                    path: AssetFingerprint.model_validate(fingerprint)
                    for path, fingerprint in post_state_fingerprints.items()
                }
            if residual_fingerprints is not None:
                plan.residual_fingerprints = {
                    path: AssetFingerprint.model_validate(fingerprint)
                    for path, fingerprint in residual_fingerprints.items()
                }
            if step_result is not None:
                plan.step_results.append(dict(step_result))
            return plan.model_copy(deep=True)
