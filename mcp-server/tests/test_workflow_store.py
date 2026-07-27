"""Workflow plan model and lock-protected store tests."""

import pytest

from unreal_mcp.workflows.models import WorkflowPlan, WorkflowStatus
from unreal_mcp.workflows.store import WorkflowStore


@pytest.mark.asyncio
async def test_store_compare_and_set_status():
    store = WorkflowStore()
    plan = WorkflowPlan.empty("plan-1")
    await store.put(plan)
    updated = await store.transition(
        "plan-1", WorkflowStatus.PLANNED, WorkflowStatus.RUNNING
    )
    assert updated.status is WorkflowStatus.RUNNING


@pytest.mark.asyncio
async def test_store_returns_deep_copies():
    store = WorkflowStore()
    plan = WorkflowPlan.empty("plan-1")
    await store.put(plan)
    fetched = await store.get("plan-1")
    fetched.step_results.append({"changed": True})
    assert (await store.get("plan-1")).step_results == []


@pytest.mark.asyncio
async def test_store_rejects_stale_status_transition():
    store = WorkflowStore()
    await store.put(WorkflowPlan.empty("plan-1"))
    with pytest.raises(ValueError, match="status mismatch"):
        await store.transition(
            "plan-1", WorkflowStatus.RUNNING, WorkflowStatus.SUCCEEDED
        )


def test_plan_digest_excludes_runtime_state_but_signs_identity():
    plan = WorkflowPlan.empty("plan-1")
    digest = plan.digest()
    plan.step_results.append({"success": True})
    plan.status = WorkflowStatus.RUNNING
    assert plan.digest() == digest
    plan.current_map = "/Game/OtherMap"
    assert plan.digest() != digest
