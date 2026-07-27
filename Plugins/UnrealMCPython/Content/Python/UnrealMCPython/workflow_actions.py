# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Internal Unreal wrappers used only by the MCP workflow service."""

import json
import re

import unreal
from UnrealMCPython import mcp_unreal_actions


def _error(message: str) -> str:
    return json.dumps({"success": False, "message": message})


def ue_get_editor_context(asset_paths: list[str] = None) -> str:
    """Returns project, editor-session, map, engine, and asset fingerprints."""
    return unreal.MCPythonHelper.get_workflow_editor_context(asset_paths or [])


def ue_begin_transaction(
    transaction_id: str = None,
    description: str = None,
    total_steps: int = 1,
    show_dialog: bool = True,
    idle_timeout_seconds: float = 60.0,
) -> str:
    """Begins one scoped MCP workflow transaction."""
    if not transaction_id or not description:
        return json.dumps(
            {
                "success": False,
                "message": "transaction_id and description are required",
            }
        )
    return unreal.MCPythonHelper.begin_workflow_transaction(
        transaction_id,
        description,
        total_steps,
        show_dialog,
        idle_timeout_seconds,
    )


def ue_commit_transaction(transaction_id: str = None) -> str:
    """Commits the active MCP workflow transaction to Unreal's undo buffer."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.commit_workflow_transaction(transaction_id)


def ue_heartbeat_transaction(
    transaction_id: str = None,
    completed_steps: int = 0,
    total_steps: int = 1,
    message: str = "",
    has_successful_write: bool = False,
) -> str:
    """Refreshes the active workflow lease and reports safe-boundary cancel state."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.heartbeat_workflow_transaction(
        transaction_id,
        completed_steps,
        total_steps,
        message,
        has_successful_write,
    )


def ue_execute_step(
    transaction_id: str = None,
    action_module: str = None,
    action_name: str = None,
    params: dict = None,
) -> str:
    """Runs one public action while the workflow lease is in atomic phase."""
    valid_module = re.fullmatch(
        r"UnrealMCPython\.[a-z0-9_]+_actions", action_module or ""
    )
    if (
        not transaction_id
        or valid_module is None
        or action_module == "UnrealMCPython.workflow_actions"
    ):
        return _error(
            "valid transaction_id and public action module are required"
        )
    if re.fullmatch(r"ue_[a-z0-9_]+", action_name or "") is None:
        return _error("action_name must be a ue_* function")

    entered = json.loads(
        unreal.MCPythonHelper.begin_workflow_atomic_step(transaction_id)
    )
    if not entered.get("success"):
        return json.dumps(entered)

    try:
        result = mcp_unreal_actions.execute_action(
            action_module, action_name, params or {}
        )
    finally:
        ended = json.loads(
            unreal.MCPythonHelper.end_workflow_atomic_step(transaction_id)
        )
    return result if ended.get("success") else json.dumps(ended)


def ue_request_cancel(transaction_id: str = None) -> str:
    """Requests cancellation for the active lease at the next safe boundary."""
    if not transaction_id:
        return _error("transaction_id is required")
    return unreal.MCPythonHelper.request_workflow_cancellation(transaction_id)


def ue_cancel_transaction(transaction_id: str = None) -> str:
    """Cancels undo recording for an active transaction without restoring state."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.cancel_workflow_transaction(transaction_id)


def ue_rollback_transaction(transaction_id: str = None) -> str:
    """Closes and immediately undoes the active MCP workflow transaction."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.rollback_workflow_transaction(transaction_id)


def ue_undo_transaction(transaction_id: str = None) -> str:
    """Undoes a committed transaction after server-side fingerprint validation."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.undo_workflow_transaction(transaction_id)
