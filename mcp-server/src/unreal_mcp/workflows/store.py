"""Async lock-protected in-memory workflow plan store."""

import asyncio
from typing import Any

from unreal_mcp.workflows.models import WorkflowPlan, WorkflowStatus


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
