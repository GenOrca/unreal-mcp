"""Arbitrary-action workflow planning and stale-state tests."""

from datetime import timedelta

import pytest

from unreal_mcp.registry import ActionRegistry
from unreal_mcp.workflows.models import (
    ActionInvocation,
    AssetFingerprint,
    WorkflowStatus,
)
from unreal_mcp.workflows.planner import WorkflowPlanner, WorkflowPlanningError
from unreal_mcp.workflows.store import WorkflowStore
from unreal_mcp.workflows.tokens import TokenService


class UndoableRegistry:
    def __init__(self):
        self.base = ActionRegistry()

    def get(self, domain, action):
        return self.base.get(domain, action).model_copy(update={"supports_undo": True})


class FakeContext:
    def __init__(self):
        self.identity = {
            "project_id": "project-1",
            "editor_session_id": "session-1",
            "current_map": "/Game/TestMap",
        }
        self.fingerprints = {}

    async def get_identity(self):
        return dict(self.identity)

    async def get_fingerprints(self, asset_paths):
        return {
            path: self.fingerprints.get(
                path, AssetFingerprint(asset_path=path, exists=False)
            )
            for path in asset_paths
        }


@pytest.fixture
def planner():
    return WorkflowPlanner(
        UndoableRegistry(),
        FakeContext(),
        token_service=TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10)),
        store=WorkflowStore(),
    )


@pytest.mark.asyncio
async def test_plan_orders_dependencies_and_collects_assets(planner):
    plan = await planner.plan(
        [
            ActionInvocation(
                id="compile",
                domain="blueprint",
                action="compile_blueprint",
                params={"asset_path": "/Game/BP_Player"},
                depends_on=["create"],
            ),
            ActionInvocation(
                id="create",
                domain="blueprint",
                action="create_blueprint",
                params={"asset_path": "/Game/BP_Player"},
            ),
        ]
    )
    assert [step.id for step in plan.steps] == ["create", "compile"]
    assert "/Game/BP_Player" in plan.asset_fingerprints
    assert plan.status is WorkflowStatus.AWAITING_CONFIRMATION
    assert plan.confirmation_token
    assert (await planner.store.get(plan.id)).digest() == plan.digest()


@pytest.mark.asyncio
async def test_plan_rejects_cycle(planner):
    with pytest.raises(ValueError, match="dependency cycle"):
        await planner.plan(
            [
                ActionInvocation(
                    id="a",
                    domain="asset",
                    action="save_asset",
                    params={"asset_path": "/Game/A"},
                    depends_on=["b"],
                ),
                ActionInvocation(
                    id="b",
                    domain="asset",
                    action="save_asset",
                    params={"asset_path": "/Game/B"},
                    depends_on=["a"],
                ),
            ]
        )


@pytest.mark.asyncio
async def test_plan_schema_validates_every_invocation(planner):
    with pytest.raises(ValueError, match="asset_path"):
        await planner.plan(
            [
                ActionInvocation(
                    id="create",
                    domain="blueprint",
                    action="create_blueprint",
                    params={},
                )
            ]
        )


@pytest.mark.asyncio
async def test_non_undoable_step_requires_explicit_signed_opt_in():
    context = FakeContext()
    service = WorkflowPlanner(
        ActionRegistry(),
        context,
        token_service=TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10)),
    )
    operation = ActionInvocation(
        id="compile",
        domain="blueprint",
        action="compile_blueprint",
        params={"asset_path": "/Game/BP_Player"},
    )
    with pytest.raises(WorkflowPlanningError) as caught:
        await service.plan([operation])
    assert caught.value.result.errors[0].code == "CONFIRMATION_REQUIRED"

    plan = await service.plan([operation], allow_non_undoable=True)
    assert plan.allow_non_undoable is True
    digest = plan.digest()
    plan.allow_non_undoable = False
    assert plan.digest() != digest


@pytest.mark.asyncio
async def test_verify_preconditions_reports_all_stale_state(planner):
    plan = await planner.plan(
        [
            ActionInvocation(
                id="create",
                domain="blueprint",
                action="create_blueprint",
                params={"asset_path": "/Game/BP_Player"},
            )
        ]
    )
    planner.context.identity["current_map"] = "/Game/OtherMap"
    planner.context.fingerprints["/Game/BP_Player"] = AssetFingerprint(
        asset_path="/Game/BP_Player", exists=True, package_guid="changed"
    )
    result = await planner.verify_preconditions(plan)
    assert result.success is False
    assert result.errors[0].code == "PRECONDITION_FAILED"
    mismatches = result.errors[0].details["mismatches"]
    assert {item["field"] for item in mismatches} == {
        "current_map",
        "asset_fingerprints./Game/BP_Player",
    }
