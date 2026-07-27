"""Workflow plan model and lock-protected store tests."""

import pytest

import unreal_mcp.workflows.models as workflow_models
from unreal_mcp.workflows.models import (
    AssetFingerprint,
    WorkflowPlan,
    WorkflowStatus,
)
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


@pytest.mark.asyncio
async def test_store_updates_runtime_fields_atomically():
    store = WorkflowStore()
    await store.put(WorkflowPlan.empty("plan-1"))
    post = {
        "/Game/A": AssetFingerprint(
            asset_path="/Game/A", exists=True, package_guid="post"
        )
    }
    updated = await store.update_runtime(
        "plan-1",
        status=WorkflowStatus.SUCCEEDED,
        transaction_id="plan-1",
        undo_token="undo-token",
        post_state_fingerprints=post,
        residual_fingerprints={},
        step_result={"step_id": "create", "success": True},
    )
    assert updated.status is WorkflowStatus.SUCCEEDED
    assert updated.transaction_id == "plan-1"
    assert updated.undo_token == "undo-token"
    assert updated.post_state_fingerprints == post
    assert updated.residual_fingerprints == {}
    assert updated.step_results == [{"step_id": "create", "success": True}]
    updated.step_results.append({"mutated": True})
    assert len((await store.get("plan-1")).step_results) == 1


def test_plan_digest_excludes_runtime_state_but_signs_identity():
    plan = WorkflowPlan.empty("plan-1")
    digest = plan.digest()
    plan.step_results.append({"success": True})
    plan.status = WorkflowStatus.RUNNING
    assert plan.digest() == digest
    plan.current_map = "/Game/OtherMap"
    assert plan.digest() != digest


def test_plan_digest_excludes_transaction_and_fingerprint_runtime_state():
    plan = WorkflowPlan.empty("plan-1")
    digest = plan.digest()
    plan.transaction_id = "plan-1"
    plan.post_state_fingerprints["/Game/A"] = AssetFingerprint(
        asset_path="/Game/A", exists=True, package_guid="post"
    )
    plan.residual_fingerprints["/Game/B"] = AssetFingerprint(
        asset_path="/Game/B", exists=True, package_guid="residual"
    )
    assert plan.digest() == digest


def test_verification_result_defaults_to_success():
    result = workflow_models.VerificationResult()
    assert result.success is True
    assert result.summary == "Verification passed."
    assert result.warnings == []
    assert result.errors == []
