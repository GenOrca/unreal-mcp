"""Offline contract tests for Unreal workflow Python wrappers."""

import importlib.util
import json
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest


ACTION_FILE = (
    Path(__file__).parents[2]
    / "Plugins"
    / "UnrealMCPython"
    / "Content"
    / "Python"
    / "UnrealMCPython"
    / "workflow_actions.py"
)


def _load(monkeypatch, action_result=None, action_raises=None):
    calls = []

    class Helper:
        @staticmethod
        def get_workflow_editor_context(paths):
            calls.append(("context", paths))
            return json.dumps({"success": True})

        @staticmethod
        def begin_workflow_transaction(
            transaction_id,
            description,
            total_steps=1,
            show_dialog=True,
            idle_timeout_seconds=60.0,
        ):
            calls.append(
                (
                    "begin",
                    transaction_id,
                    description,
                    total_steps,
                    show_dialog,
                    idle_timeout_seconds,
                )
            )
            return json.dumps({"success": True})

        @staticmethod
        def commit_workflow_transaction(transaction_id):
            calls.append(("commit", transaction_id))
            return json.dumps({"success": True})

        @staticmethod
        def heartbeat_workflow_transaction(
            transaction_id,
            completed_steps,
            total_steps,
            message,
            has_successful_write,
        ):
            calls.append(
                (
                    "heartbeat",
                    transaction_id,
                    completed_steps,
                    total_steps,
                    message,
                    has_successful_write,
                )
            )
            return json.dumps({"success": True, "cancel_requested": False})

        @staticmethod
        def begin_workflow_atomic_step(transaction_id):
            calls.append(("atomic_begin", transaction_id))
            return json.dumps({"success": True})

        @staticmethod
        def end_workflow_atomic_step(transaction_id):
            calls.append(("atomic_end", transaction_id))
            return json.dumps({"success": True})

        @staticmethod
        def request_workflow_cancellation(transaction_id):
            calls.append(("request_cancel", transaction_id))
            return json.dumps({"success": True, "cancel_requested": True})

        @staticmethod
        def cancel_workflow_transaction(transaction_id):
            calls.append(("cancel", transaction_id))
            return json.dumps({"success": True})

        @staticmethod
        def rollback_workflow_transaction(transaction_id):
            calls.append(("rollback", transaction_id))
            return json.dumps({"success": True})

        @staticmethod
        def undo_workflow_transaction(transaction_id):
            calls.append(("undo", transaction_id))
            return json.dumps({"success": True})

    monkeypatch.setitem(
        sys.modules, "unreal", SimpleNamespace(MCPythonHelper=Helper)
    )

    def execute_action(module_name, function_name, params):
        calls.append(("action", module_name, function_name, params))
        if action_raises is not None:
            raise action_raises
        return json.dumps(action_result or {"success": True})

    package = types.ModuleType("UnrealMCPython")
    package.__path__ = []
    dispatcher = types.ModuleType("UnrealMCPython.mcp_unreal_actions")
    dispatcher.execute_action = execute_action
    package.mcp_unreal_actions = dispatcher
    monkeypatch.setitem(sys.modules, "UnrealMCPython", package)
    monkeypatch.setitem(
        sys.modules, "UnrealMCPython.mcp_unreal_actions", dispatcher
    )
    spec = importlib.util.spec_from_file_location("_workflow_actions_test", ACTION_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, calls


def test_context_wrapper_forwards_paths(monkeypatch):
    module, calls = _load(monkeypatch)
    assert json.loads(module.ue_get_editor_context(["/Game/A"]))["success"]
    assert calls == [("context", ["/Game/A"])]


def test_transaction_wrapper_validates_required_parameters(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(module.ue_begin_transaction(transaction_id="tx"))
    assert result["success"] is False
    assert calls == []


def test_begin_forwards_lease_configuration(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(
        module.ue_begin_transaction(
            transaction_id="tx",
            description="Build",
            total_steps=3,
            show_dialog=False,
            idle_timeout_seconds=2.5,
        )
    )
    assert result["success"] is True
    assert calls == [("begin", "tx", "Build", 3, False, 2.5)]


def test_heartbeat_forwards_progress_and_write_state(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(
        module.ue_heartbeat_transaction(
            transaction_id="tx",
            completed_steps=2,
            total_steps=3,
            message="Compiled",
            has_successful_write=True,
        )
    )
    assert result["success"] is True
    assert calls == [("heartbeat", "tx", 2, 3, "Compiled", True)]


def test_execute_step_always_leaves_atomic_phase(monkeypatch):
    module, calls = _load(
        monkeypatch,
        action_result={"success": False, "message": "compile failed"},
    )
    result = json.loads(
        module.ue_execute_step(
            transaction_id="tx",
            action_module="UnrealMCPython.blueprint_actions",
            action_name="ue_compile_blueprint",
            params={"asset_path": "/Game/BP"},
        )
    )
    assert result["success"] is False
    assert calls == [
        ("atomic_begin", "tx"),
        (
            "action",
            "UnrealMCPython.blueprint_actions",
            "ue_compile_blueprint",
            {"asset_path": "/Game/BP"},
        ),
        ("atomic_end", "tx"),
    ]


def test_execute_step_leaves_atomic_phase_when_action_raises(monkeypatch):
    module, calls = _load(monkeypatch, action_raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        module.ue_execute_step(
            transaction_id="tx",
            action_module="UnrealMCPython.actor_actions",
            action_name="ue_set_location",
            params={},
        )
    assert calls[-1] == ("atomic_end", "tx")


@pytest.mark.parametrize(
    "module_name",
    [
        "UnrealMCPython.workflow_actions",
        "os",
        "UnrealMCPython../actor_actions",
    ],
)
def test_execute_step_rejects_internal_or_unsafe_modules(
    monkeypatch, module_name
):
    module, calls = _load(monkeypatch)
    result = json.loads(
        module.ue_execute_step(
            transaction_id="tx",
            action_module=module_name,
            action_name="ue_anything",
            params={},
        )
    )
    assert result["success"] is False
    assert calls == []


def test_request_cancel_forwards_an_id(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(module.ue_request_cancel(transaction_id="tx"))
    assert result["success"] is True
    assert result["cancel_requested"] is True
    assert calls == [("request_cancel", "tx")]


@pytest.mark.parametrize(
    "wrapper_name",
    [
        "ue_commit_transaction",
        "ue_cancel_transaction",
        "ue_rollback_transaction",
        "ue_undo_transaction",
    ],
)
def test_transaction_wrappers_require_an_id(monkeypatch, wrapper_name):
    module, calls = _load(monkeypatch)
    result = json.loads(getattr(module, wrapper_name)())
    assert result["success"] is False
    assert calls == []


@pytest.mark.parametrize(
    ("wrapper_name", "expected_call"),
    [
        ("ue_commit_transaction", ("commit", "tx")),
        ("ue_cancel_transaction", ("cancel", "tx")),
        ("ue_rollback_transaction", ("rollback", "tx")),
        ("ue_undo_transaction", ("undo", "tx")),
    ],
)
def test_transaction_wrappers_forward_an_id(
    monkeypatch, wrapper_name, expected_call
):
    module, calls = _load(monkeypatch)
    result = json.loads(getattr(module, wrapper_name)(transaction_id="tx"))
    assert result["success"] is True
    assert calls == [expected_call]
