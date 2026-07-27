# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Internal Unreal wrappers used only by the MCP workflow service."""

import json

import unreal


def ue_get_editor_context(asset_paths: list[str] = None) -> str:
    """Returns project, editor-session, map, engine, and asset fingerprints."""
    return unreal.MCPythonHelper.get_workflow_editor_context(asset_paths or [])


def ue_begin_transaction(
    transaction_id: str = None, description: str = None
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
        transaction_id, description
    )


def ue_commit_transaction(transaction_id: str = None) -> str:
    """Commits the active MCP workflow transaction to Unreal's undo buffer."""
    if not transaction_id:
        return json.dumps(
            {"success": False, "message": "transaction_id is required"}
        )
    return unreal.MCPythonHelper.commit_workflow_transaction(transaction_id)


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
