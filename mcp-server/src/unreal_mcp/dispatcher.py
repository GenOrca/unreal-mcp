# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Namespace dispatcher — thin assembler.

One MCP tool per domain. Each accepts (action, params) and routes to the
Unreal TCP server as ue_<action>(**params). action='list_actions' returns the
domain's action catalog (param names + one-line docs).

The catalog is AUTO-GENERATED from the plugin's ue_* signatures
(see generate_catalog.py). Param names are therefore guaranteed to match —
no hand transcription. This file never grows when actions are added.
"""

import base64
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP, Image

from unreal_mcp.core import send_to_unreal, UnrealExecutionError, send_python_exec, send_livecoding_compile
from unreal_mcp.dispatchers._catalog import CATALOG

dispatcher_mcp = FastMCP(
    name="UnrealMCP",
    description=(
        "Unreal Engine MCP via namespace dispatchers. "
        "Each domain tool accepts (action, params). "
        "Pass action='list_actions' to any tool to get available actions and parameter docs."
    )
)

# Domains using standard python_call routing. util and vision have hand-written
# handlers (special TCP types / MCP Image return).
_SPECIAL_DOMAINS = {"util", "vision"}
_STANDARD_DOMAINS = [d for d in CATALOG if d not in _SPECIAL_DOMAINS]


def _module(domain: str) -> str:
    return f"UnrealMCPython.{domain}_actions"


async def _dispatch(domain: str, action: str, params: dict) -> dict:
    if action == "list_actions":
        return {"success": True, "domain": domain, "actions": CATALOG[domain]}
    if action not in CATALOG[domain]:
        return {"success": False, "message": f"Unknown action '{action}'. Available: {list(CATALOG[domain])}"}
    try:
        return await send_to_unreal(_module(domain), f"ue_{action}", params)
    except UnrealExecutionError as e:
        return {"success": False, "message": str(e), "details": getattr(e, "details", {})}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {e}"}


def _desc(domain: str) -> str:
    actions = ", ".join(CATALOG[domain])
    return f"Unreal {domain} tools. Actions: {actions}. Pass action='list_actions' for parameter docs."


def _make_handler(domain: str):
    async def handler(
        action: Annotated[str, Field(description="Action name. Use 'list_actions' for full parameter docs.")],
        params: Annotated[dict, Field(description="Action parameters (keys must match the action's documented params).")] = {}
    ) -> dict:
        return await _dispatch(domain, action, params)
    handler.__name__ = domain
    return handler


for _domain in _STANDARD_DOMAINS:
    dispatcher_mcp.tool(name=_domain, description=_desc(_domain))(_make_handler(_domain))


# ─── util: special routing (execute_python / livecoding_compile use dedicated TCP types) ──

@dispatcher_mcp.tool(name="util", description=_desc("util"))
async def util(
    action: Annotated[str, Field(description="Action name. Use 'list_actions' for full parameter docs.")],
    params: Annotated[dict, Field(description="Action parameters. execute_python: {code}. get_output_log: {line_count, keyword}.")] = {}
) -> dict:
    if action == "list_actions":
        return {"success": True, "domain": "util", "actions": CATALOG["util"]}

    if action == "execute_python":
        code = params.get("code", "")
        if not code:
            return {"success": False, "message": "params.code is required"}
        try:
            return await send_python_exec(code)
        except UnrealExecutionError as e:
            return {"success": False, "message": str(e)}

    if action == "livecoding_compile":
        try:
            return await send_livecoding_compile()
        except UnrealExecutionError as e:
            return {"success": False, "message": str(e)}

    if action in CATALOG["util"]:
        try:
            return await send_to_unreal(_module("util"), f"ue_{action}", params)
        except UnrealExecutionError as e:
            return {"success": False, "message": str(e)}

    return {"success": False, "message": f"Unknown action '{action}'. Available: {list(CATALOG['util'])}"}


# ─── vision: special routing (returns an MCP Image for captures) ────────────────

@dispatcher_mcp.tool(name="vision", description=_desc("vision"))
async def vision(
    action: Annotated[str, Field(description="Action name. Use 'list_actions' for full parameter docs.")],
    params: Annotated[dict, Field(description="Action parameters. capture_viewport: {width, height, fov}.")] = {}
) -> "Image | dict":
    if action == "list_actions":
        return {"success": True, "domain": "vision", "actions": CATALOG["vision"]}

    if action not in CATALOG["vision"]:
        return {"success": False, "message": f"Unknown action '{action}'. Available: {list(CATALOG['vision'])}"}

    try:
        result = await send_to_unreal(_module("vision"), f"ue_{action}", params)
    except UnrealExecutionError as e:
        return {"success": False, "message": str(e)}

    # Capture actions return base64 PNG in 'image_data' → hand back an MCP Image.
    if isinstance(result, dict):
        img_b64 = result.get("image_data")
        if result.get("success") and img_b64:
            return Image(data=base64.b64decode(img_b64), format="png")
    return result
