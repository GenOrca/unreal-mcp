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
import json
import logging
import re
import traceback
from typing import Annotated
from jsonschema import Draft202012Validator
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from unreal_mcp.core import send_to_unreal, UnrealExecutionError, send_python_exec, send_livecoding_compile
from unreal_mcp.config import load_settings
from unreal_mcp.contracts import ErrorCode
from unreal_mcp.discovery import DiscoveryService
from unreal_mcp.dispatchers._catalog import CATALOG
from unreal_mcp.errors import error_result
from unreal_mcp.legacy_namespace_contract import LEGACY_NAMESPACE_DESCRIPTIONS
from unreal_mcp.policy import DispatchDecision, SafetyPolicy
from unreal_mcp.registry import ActionRegistry

dispatcher_mcp = FastMCP(
    name="UnrealMCP",
    instructions=(
        "Unreal Engine MCP via namespace dispatchers. "
        "Each domain tool accepts (action, params). "
        "Pass action='list_actions' to any tool to get available actions and parameter docs."
    )
)

# Domains using standard python_call routing. util and vision have hand-written
# handlers (special TCP types / MCP Image return).
_SPECIAL_DOMAINS = {"util", "vision"}
_STANDARD_DOMAINS = [d for d in CATALOG if d not in _SPECIAL_DOMAINS]
_LOCAL_ACTIONS = {
    "util": frozenset(
        {
            "execute_python",
            "livecoding_compile",
            "search_actions",
            "describe_action",
            "get_capabilities",
        }
    )
}
_registry = ActionRegistry()
_discovery = DiscoveryService(_registry)
_settings = load_settings()
_policy = SafetyPolicy(_settings.safety_mode)
_runtime_capabilities = {"ue_version": None, "plugins": {}}
_logger = logging.getLogger(__name__)


@dispatcher_mcp.resource("unreal://catalog")
def action_catalog_resource() -> str:
    """Complete generated Action Registry v2 catalog."""
    return json.dumps(
        {"version": 2, "actions": _registry.export()},
        ensure_ascii=False,
    )


@dispatcher_mcp.prompt(name="gameplay_foundation")
def gameplay_foundation_prompt() -> str:
    return (
        "Inspect capabilities, call workflow plan_gameplay_foundation, "
        "review changes and conflicts, apply with the confirmation token, "
        "poll workflow get, then call verify_gameplay_foundation."
    )


def _module(domain: str) -> str:
    return f"UnrealMCPython.{domain}_actions"


def _structured_result(**kwargs) -> dict:
    result = error_result(**kwargs).model_dump(mode="json")
    # Legacy callers commonly read message; structured clients use summary/errors.
    result["message"] = result["summary"]
    return result


def _local_exception_result(
    domain: str,
    action: str,
    exc: Exception,
    *,
    code: ErrorCode = ErrorCode.INTERNAL_ERROR,
    retryable: bool = False,
) -> dict:
    message = (
        str(exc)
        if code is ErrorCode.UE_UNAVAILABLE
        else f"Unexpected failure while running {domain}.{action}"
    )
    details = {}
    if _settings.debug:
        details["debug_traceback"] = traceback.format_exc()
    result = _structured_result(
        code=code,
        message=message,
        path="action",
        retryable=retryable,
        hint=(
            "Start Unreal Editor and retry."
            if code is ErrorCode.UE_UNAVAILABLE
            else "Check the server log using this trace_id, then retry."
        ),
        details=details,
    )
    _logger.error(
        "Local action %s.%s failed trace_id=%s exception_type=%s",
        domain,
        action,
        result["trace_id"],
        type(exc).__name__,
        exc_info=_settings.debug,
    )
    return result


def _schema_error(domain: str, action: str, params: dict, spec) -> dict | None:
    error = next(Draft202012Validator(spec.input_schema).iter_errors(params), None)
    if error is None:
        return None
    if error.validator == "required":
        missing = next(
            name for name in error.validator_value if name not in error.instance
        )
        message = f"{missing} is required"
        path = f"params.{missing}"
    elif error.validator == "additionalProperties":
        allowed = set(spec.input_schema.get("properties", {}))
        unexpected = sorted(set(params) - allowed)[0]
        message = f"{unexpected} is not an allowed parameter"
        path = f"params.{unexpected}"
    else:
        suffix = ".".join(str(part) for part in error.absolute_path)
        path = f"params.{suffix}" if suffix else "params"
        message = error.message
    return _structured_result(
        code=ErrorCode.INVALID_INPUT,
        message=message,
        path=path,
        retryable=True,
        hint=f"Call util.describe_action for {domain}.{action}, correct params, and retry.",
        details={"validator": error.validator},
    )


def _preflight(
    domain: str,
    action: str,
    params: dict,
    *,
    validate_input: bool = False,
) -> dict | None:
    spec = _registry.get(domain, action)
    engine_version = _runtime_capabilities.get("ue_version")
    if engine_version:
        match = re.match(r"(\d+\.\d+)", str(engine_version))
        current = match.group(1) if match else str(engine_version)
        if current not in spec.ue_versions:
            return _structured_result(
                code=ErrorCode.UE_VERSION_UNSUPPORTED,
                message=f"{domain}.{action} does not support Unreal Engine {current}",
                path="action",
                hint=f"Use Unreal Engine {', '.join(spec.ue_versions)} or choose another action.",
                details={"current_version": current, "supported_versions": spec.ue_versions},
            )

    known_plugins = _runtime_capabilities.get("plugins", {})
    missing_plugins = [
        plugin
        for plugin in spec.required_plugins
        if known_plugins.get(plugin) is False
    ]
    if missing_plugins:
        return _structured_result(
            code=ErrorCode.PLUGIN_REQUIRED,
            message=f"{domain}.{action} requires unavailable plugins",
            path="action",
            hint="Enable the listed plugins in Unreal Editor, restart, and retry.",
            details={"missing_plugins": missing_plugins},
        )

    if domain != "workflow" and _policy.decide(spec) is DispatchDecision.PLAN_REQUIRED:
        return _structured_result(
            code=ErrorCode.CONFIRMATION_REQUIRED,
            message=f"{domain}.{action} requires an approved workflow plan",
            path="action",
            retryable=True,
            hint="Call workflow plan with details.operation as its single operations item.",
            details={
                "operation": {
                    "id": "step-1",
                    "domain": domain,
                    "action": action,
                    "params": params,
                    "depends_on": [],
                },
                "risk": spec.risk.value,
            },
        )

    if validate_input:
        return _schema_error(domain, action, params, spec)
    return None


def _remember_unreal_capabilities(project_info: dict) -> None:
    if not isinstance(project_info, dict) or not project_info.get("success"):
        return
    _runtime_capabilities["ue_version"] = project_info.get("engine_version")
    availability = project_info.get("availability", {})
    key_to_plugin = {
        "enhanced_input": "EnhancedInput",
        "umg": "UMG",
        "python_script_plugin": "PythonScriptPlugin",
        "live_coding": "LiveCoding",
    }
    _runtime_capabilities["plugins"].update(
        {
            plugin: bool(availability[key])
            for key, plugin in key_to_plugin.items()
            if key in availability
        }
    )


async def _dispatch(domain: str, action: str, params: dict) -> dict:
    if action == "list_actions":
        return {"success": True, "domain": domain, "actions": CATALOG[domain]}
    if action not in CATALOG[domain]:
        return {"success": False, "message": f"Unknown action '{action}'. Available: {list(CATALOG[domain])}"}
    blocked = _preflight(domain, action, params)
    if blocked is not None:
        return blocked
    try:
        return await send_to_unreal(_module(domain), f"ue_{action}", params)
    except UnrealExecutionError as e:
        return {"success": False, "message": str(e), "details": getattr(e, "details", {})}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {e}"}


def _desc(domain: str) -> str:
    if domain in LEGACY_NAMESPACE_DESCRIPTIONS:
        return LEGACY_NAMESPACE_DESCRIPTIONS[domain]
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

    if action not in CATALOG["util"]:
        return {"success": False, "message": f"Unknown action '{action}'. Available: {list(CATALOG['util'])}"}

    blocked = _preflight(
        "util",
        action,
        params,
        validate_input=action in _LOCAL_ACTIONS["util"],
    )
    if blocked is not None:
        return blocked

    if action == "search_actions":
        try:
            return _discovery.search(**params)
        except TypeError as exc:
            return error_result(
                code="INVALID_INPUT",
                message=str(exc),
                path="params",
                hint="Call util.describe_action for util.search_actions.",
            ).model_dump(mode="json")
        except Exception as exc:
            return _local_exception_result("util", action, exc)

    if action == "describe_action":
        try:
            return _discovery.describe(
                params.get("domain", ""), params.get("action", "")
            )
        except Exception as exc:
            return _local_exception_result("util", action, exc)

    if action == "get_capabilities":
        async def load_project_info():
            project_info = await send_to_unreal(
                _module("util"), "ue_get_project_info", {}
            )
            _remember_unreal_capabilities(project_info)
            return project_info

        return await _discovery.get_capabilities(load_project_info)

    if action == "execute_python":
        code = params.get("code", "")
        if not code:
            return {"success": False, "message": "params.code is required"}
        try:
            return await send_python_exec(code)
        except UnrealExecutionError as e:
            return _local_exception_result(
                "util", action, e, code=ErrorCode.UE_UNAVAILABLE, retryable=True
            )
        except Exception as exc:
            return _local_exception_result("util", action, exc)

    if action == "livecoding_compile":
        try:
            return await send_livecoding_compile()
        except UnrealExecutionError as e:
            return _local_exception_result(
                "util", action, e, code=ErrorCode.UE_UNAVAILABLE, retryable=True
            )
        except Exception as exc:
            return _local_exception_result("util", action, exc)

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

    blocked = _preflight("vision", action, params)
    if blocked is not None:
        return blocked

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
