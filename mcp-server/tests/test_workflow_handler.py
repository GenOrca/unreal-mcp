"""Server-local workflow namespace routing tests."""

from types import SimpleNamespace

import pytest

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import ErrorCode
from unreal_mcp.registry import ActionRegistry
from unreal_mcp.workflows.handler import WorkflowHandler
from unreal_mcp.workflows.models import (
    ActionInvocation,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)


def make_plan(plan_id: str = "plan-1") -> WorkflowPlan:
    return WorkflowPlan(
        id=plan_id,
        status=WorkflowStatus.AWAITING_CONFIRMATION,
        safety_mode=SafetyMode.COMPATIBLE,
        project_id="project-1",
        editor_session_id="session-1",
        current_map="/Game/TestMap",
        confirmation_token="confirm-token",
    )


class FakePlanner:
    def __init__(self):
        self.calls = []
        self.result = make_plan()

    async def plan(self, operations, *, allow_non_undoable=False):
        self.calls.append((list(operations), allow_non_undoable))
        return self.result


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.cancel_result = True

    async def start(self, plan_id, token):
        self.calls.append(("start", plan_id, token))
        return SimpleNamespace(get_name=lambda: f"workflow:{plan_id}")

    async def run(self, plan_id, token, progress=None):
        self.calls.append(("run", plan_id, token, progress))
        return WorkflowResult(
            success=True,
            status=WorkflowStatus.SUCCEEDED,
            summary="Workflow completed successfully.",
            plan_id=plan_id,
            trace_id="apply-trace",
        )

    async def cancel(self, plan_id):
        self.calls.append(("cancel", plan_id))
        return self.cancel_result

    async def undo(self, plan_id, token):
        self.calls.append(("undo", plan_id, token))
        return WorkflowResult(
            success=True,
            status=WorkflowStatus.SUCCEEDED,
            summary="Workflow transaction was undone.",
            plan_id=plan_id,
            data={"undone": True},
            trace_id="undo-trace",
        )


class FakeStore:
    def __init__(self):
        self.plan = make_plan()
        self.calls = []

    async def get(self, plan_id):
        self.calls.append(plan_id)
        if plan_id != self.plan.id:
            raise KeyError(f"Unknown workflow plan '{plan_id}'")
        return self.plan.model_copy(deep=True)


class FakeProgress:
    pass


class FakeHook:
    def __init__(self, action):
        self.action = action
        self.calls = []

    async def __call__(self, spec):
        self.calls.append(spec)
        return {
            "success": True,
            "status": "succeeded",
            "summary": f"{self.action} completed",
            "data": {"spec": spec},
        }


@pytest.fixture
def runtime():
    planner = FakePlanner()
    executor = FakeExecutor()
    store = FakeStore()
    gameplay_planner = FakeHook("plan_gameplay_foundation")
    gameplay_verifier = FakeHook("verify_gameplay_foundation")
    handler = WorkflowHandler(
        ActionRegistry(),
        planner,
        executor,
        store,
        gameplay_planner=gameplay_planner,
        gameplay_verifier=gameplay_verifier,
    )
    return SimpleNamespace(
        planner=planner,
        executor=executor,
        store=store,
        gameplay_planner=gameplay_planner,
        gameplay_verifier=gameplay_verifier,
        handler=handler,
    )


@pytest.mark.asyncio
async def test_workflow_plan_routes_valid_operations(runtime):
    result = await runtime.handler.handle(
        "plan",
        {
            "operations": [
                {
                    "id": "create",
                    "domain": "blueprint",
                    "action": "create_blueprint",
                    "params": {"asset_path": "/Game/BP_Player"},
                    "depends_on": [],
                }
            ],
            "allow_non_undoable": True,
        },
    )
    assert result["success"] is True
    assert result["status"] == "awaiting_confirmation"
    assert result["data"]["workflow_id"] == "plan-1"
    assert result["data"]["confirmation_token"] == "confirm-token"
    operations, allow_non_undoable = runtime.planner.calls[0]
    assert operations == [
        ActionInvocation(
            id="create",
            domain="blueprint",
            action="create_blueprint",
            params={"asset_path": "/Game/BP_Player"},
        )
    ]
    assert allow_non_undoable is True


@pytest.mark.asyncio
async def test_workflow_apply_starts_background_by_default(runtime):
    result = await runtime.handler.handle(
        "apply",
        {"plan_id": "plan-1", "confirmation_token": "confirm-token"},
    )
    assert result["success"] is True
    assert result["status"] == "running"
    assert result["data"]["workflow_id"] == "plan-1"
    assert runtime.executor.calls == [
        ("start", "plan-1", "confirm-token")
    ]


@pytest.mark.asyncio
async def test_workflow_apply_waits_and_forwards_progress(runtime):
    progress = FakeProgress()
    result = await runtime.handler.handle(
        "apply",
        {
            "plan_id": "plan-1",
            "confirmation_token": "confirm-token",
            "wait_for_completion": True,
        },
        progress,
    )
    assert result["status"] == "succeeded"
    assert runtime.executor.calls == [
        ("run", "plan-1", "confirm-token", progress)
    ]


@pytest.mark.asyncio
async def test_workflow_get_returns_stored_runtime_state(runtime):
    result = await runtime.handler.handle("get", {"plan_id": "plan-1"})
    assert result["success"] is True
    assert result["status"] == "awaiting_confirmation"
    assert result["data"]["workflow"]["id"] == "plan-1"
    assert runtime.store.calls == ["plan-1"]


@pytest.mark.asyncio
async def test_workflow_cancel_sets_executor_event(runtime):
    result = await runtime.handler.handle("cancel", {"plan_id": "plan-1"})
    assert result["success"] is True
    assert result["status"] == "cancellation_requested"
    assert runtime.executor.calls == [("cancel", "plan-1")]


@pytest.mark.asyncio
async def test_workflow_undo_routes_signed_token(runtime):
    result = await runtime.handler.handle(
        "undo", {"plan_id": "plan-1", "undo_token": "undo-token"}
    )
    assert result["success"] is True
    assert result["data"]["undone"] is True
    assert runtime.executor.calls == [
        ("undo", "plan-1", "undo-token")
    ]


@pytest.mark.asyncio
async def test_workflow_plan_gameplay_foundation_uses_installed_hook(runtime):
    spec = {"name": "Third Person Foundation"}
    result = await runtime.handler.handle(
        "plan_gameplay_foundation", {"spec": spec}
    )
    assert result["success"] is True
    assert runtime.gameplay_planner.calls == [spec]


@pytest.mark.asyncio
async def test_workflow_verify_gameplay_foundation_uses_installed_hook(runtime):
    spec = {"expected_map": "/Game/Maps/Arena"}
    result = await runtime.handler.handle(
        "verify_gameplay_foundation", {"spec": spec}
    )
    assert result["success"] is True
    assert runtime.gameplay_verifier.calls == [spec]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "params", "code"),
    [
        ("does_not_exist", {}, ErrorCode.UNKNOWN_ACTION),
        ("get", {}, ErrorCode.INVALID_INPUT),
        ("get", {"plan_id": "plan-1", "extra": True}, ErrorCode.INVALID_INPUT),
    ],
)
async def test_workflow_rejects_unknown_or_schema_invalid_action(
    runtime, action, params, code
):
    result = await runtime.handler.handle(action, params)
    assert result["success"] is False
    assert result["errors"][0]["code"] == code.value
    assert runtime.planner.calls == []
    assert runtime.executor.calls == []


@pytest.mark.asyncio
async def test_workflow_plan_rejects_nested_workflow_operation(runtime):
    result = await runtime.handler.handle(
        "plan",
        {
            "operations": [
                {
                    "id": "nested",
                    "domain": "workflow",
                    "action": "apply",
                    "params": {
                        "plan_id": "other",
                        "confirmation_token": "token",
                    },
                }
            ]
        },
    )
    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_INPUT"
    assert runtime.planner.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ["plan_gameplay_foundation", "verify_gameplay_foundation"],
)
async def test_foundation_branch_without_hook_returns_capability_error(action):
    handler = WorkflowHandler(
        ActionRegistry(), FakePlanner(), FakeExecutor(), FakeStore()
    )
    result = await handler.handle(action, {"spec": {}})
    error = result["errors"][0]
    assert error["code"] == "UE_VERSION_UNSUPPORTED"
    assert error["details"] == {"capability": "gameplay_foundation_v1"}

