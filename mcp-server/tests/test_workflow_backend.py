"""Concrete Unreal workflow backend routing tests."""

import pytest

from unreal_mcp.contracts import Effect, Risk
import unreal_mcp.workflows.backend as backend_module
from unreal_mcp.workflows.backend import UnrealWorkflowBackend
from unreal_mcp.workflows.models import (
    ActionCall,
    ActionInvocation,
    PlanStep,
)


def test_concrete_backend_satisfies_workflow_protocol():
    assert isinstance(
        UnrealWorkflowBackend(sender=lambda *_args: None),
        backend_module.WorkflowBackend,
    )


@pytest.mark.asyncio
async def test_backend_routes_lease_and_atomic_step_calls():
    calls = []

    async def sender(module, action, params):
        calls.append((module, action, params))
        return {"success": True}

    backend = UnrealWorkflowBackend(sender=sender)
    invocation = ActionInvocation(
        id="move",
        domain="actor",
        action="set_location",
        params={"actor_label": "Cube", "location": [0, 0, 100]},
    )

    await backend.begin("tx", "Build", 4)
    await backend.heartbeat("tx", 1, 4, "Created", True)
    await backend.execute_step("tx", invocation)
    await backend.commit("tx")

    assert calls == [
        (
            "UnrealMCPython.workflow_actions",
            "ue_begin_transaction",
            {
                "transaction_id": "tx",
                "description": "Build",
                "total_steps": 4,
            },
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_heartbeat_transaction",
            {
                "transaction_id": "tx",
                "completed_steps": 1,
                "total_steps": 4,
                "message": "Created",
                "has_successful_write": True,
            },
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_execute_step",
            {
                "transaction_id": "tx",
                "action_module": "UnrealMCPython.actor_actions",
                "action_name": "ue_set_location",
                "params": {
                    "actor_label": "Cube",
                    "location": [0, 0, 100],
                },
            },
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_commit_transaction",
            {"transaction_id": "tx"},
        ),
    ]


@pytest.mark.asyncio
async def test_backend_returns_validated_identity_and_fingerprints():
    calls = []

    async def sender(module, action, params):
        calls.append((module, action, params))
        paths = params["asset_paths"]
        return {
            "success": True,
            "project_id": "project-1",
            "editor_session_id": "session-1",
            "current_map": "/Game/Map",
            "engine_version": "5.7.4",
            "asset_fingerprints": {
                path: {"asset_path": path, "exists": path == "/Game/A"}
                for path in paths
            },
        }

    backend = UnrealWorkflowBackend(sender=sender)
    assert await backend.get_identity() == {
        "project_id": "project-1",
        "editor_session_id": "session-1",
        "current_map": "/Game/Map",
    }
    fingerprints = await backend.get_fingerprints(["/Game/A", "/Game/B"])
    assert fingerprints["/Game/A"].exists is True
    assert fingerprints["/Game/B"].exists is False
    assert calls == [
        (
            "UnrealMCPython.workflow_actions",
            "ue_get_editor_context",
            {"asset_paths": []},
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_get_editor_context",
            {"asset_paths": ["/Game/A", "/Game/B"]},
        ),
    ]


@pytest.mark.asyncio
async def test_backend_routes_terminal_transaction_calls():
    calls = []

    async def sender(module, action, params):
        calls.append((module, action, params))
        return {"success": True}

    backend = UnrealWorkflowBackend(sender=sender)
    await backend.request_cancel("tx")
    await backend.cancel_transaction("tx")
    await backend.rollback_transaction("tx")
    await backend.undo_transaction("tx")
    assert calls == [
        (
            "UnrealMCPython.workflow_actions",
            "ue_request_cancel",
            {"transaction_id": "tx"},
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_cancel_transaction",
            {"transaction_id": "tx"},
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_rollback_transaction",
            {"transaction_id": "tx"},
        ),
        (
            "UnrealMCPython.workflow_actions",
            "ue_undo_transaction",
            {"transaction_id": "tx"},
        ),
    ]


@pytest.mark.asyncio
async def test_backend_runs_explicit_and_snapshot_restore_actions():
    calls = []

    async def sender(module, action, params):
        calls.append((module, action, params))
        return {"success": True}

    backend = UnrealWorkflowBackend(sender=sender)
    inverse = ActionCall(
        domain="asset",
        action="delete_asset",
        params={"asset_path": "/Game/New"},
    )
    await backend.execute_recovery(inverse)
    snapshot_step = PlanStep(
        invocation=ActionInvocation(
            id="restore",
            domain="asset",
            action="save_asset",
            params={"asset_path": "/Game/New"},
        ),
        rollback_mode="snapshot",
        pre_state_snapshot={"restore": inverse.model_dump(mode="json")},
        effect=Effect.WRITE,
        risk=Risk.MEDIUM,
    )
    await backend.restore_snapshot(snapshot_step)
    assert calls == [
        (
            "UnrealMCPython.asset_actions",
            "ue_delete_asset",
            {"asset_path": "/Game/New"},
        ),
        (
            "UnrealMCPython.asset_actions",
            "ue_delete_asset",
            {"asset_path": "/Game/New"},
        ),
    ]
