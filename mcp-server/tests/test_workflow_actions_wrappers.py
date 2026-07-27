"""Offline contract tests for Unreal workflow Python wrappers."""

import importlib.util
import json
from pathlib import Path
import sys
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


def _load(monkeypatch):
    calls = []

    class Helper:
        @staticmethod
        def get_workflow_editor_context(paths):
            calls.append(("context", paths))
            return json.dumps({"success": True})

        @staticmethod
        def begin_workflow_transaction(transaction_id, description):
            calls.append(("begin", transaction_id, description))
            return json.dumps({"success": True})

        @staticmethod
        def commit_workflow_transaction(transaction_id):
            calls.append(("commit", transaction_id))
            return json.dumps({"success": True})

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
