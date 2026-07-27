"""Local LLM-friendly action discovery and capability reporting."""

import base64
import json
from importlib.metadata import version
import re
from typing import Awaitable, Callable

from unreal_mcp.config import load_settings
from unreal_mcp.contracts import Effect, ErrorCode, Risk
from unreal_mcp.errors import error_result
from unreal_mcp.registry import ActionRegistry, UnknownActionError


ProjectInfoLoader = Callable[[], Awaitable[dict]]


def _success(summary: str, data: dict, **top_level) -> dict:
    return {
        "success": True,
        "status": "succeeded",
        "summary": summary,
        "data": data,
        **top_level,
    }


def _encode_cursor(qualified_action: str) -> str:
    payload = json.dumps(
        {"after": qualified_action}, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> str:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        after = payload["after"]
        if set(payload) != {"after"} or not isinstance(after, str) or not after:
            raise ValueError
        return after
    except Exception as exc:
        raise ValueError("cursor must be a valid discovery cursor") from exc


class DiscoveryService:
    def __init__(self, registry: ActionRegistry):
        self.registry = registry

    def search(
        self,
        *,
        query: str = "",
        domain: str = "",
        effect: str = "",
        risk: str = "",
        required_plugin: str = "",
        limit: int = 20,
        cursor: str = "",
    ) -> dict:
        if effect and effect not in {item.value for item in Effect}:
            return self._invalid("effect", "effect must be read, write, or destructive")
        if risk and risk not in {item.value for item in Risk}:
            return self._invalid("risk", "risk must be low, medium, or high")
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            return self._invalid("limit", "limit must be an integer from 1 to 100")

        tokens = re.findall(r"[a-z0-9_]+", query.casefold())
        ranked = []
        for spec in self.registry.iter_actions():
            if domain and spec.domain != domain:
                continue
            if effect and spec.effect.value != effect:
                continue
            if risk and spec.risk.value != risk:
                continue
            if required_plugin and required_plugin.casefold() not in {
                plugin.casefold() for plugin in spec.required_plugins
            }:
                continue
            qualified = f"{spec.domain}.{spec.action}"
            haystack = " ".join(
                [qualified, spec.title, spec.description]
            ).casefold()
            score = sum(1 for token in tokens if token in haystack)
            if tokens and score == 0:
                continue
            ranked.append((score, qualified, spec))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        start = 0
        if cursor:
            try:
                after = _decode_cursor(cursor)
                start = next(
                    index + 1
                    for index, (_, qualified, _) in enumerate(ranked)
                    if qualified == after
                )
            except (ValueError, StopIteration):
                return self._invalid("cursor", "cursor is malformed or stale")

        selected = ranked[start : start + limit]
        matches = [self._compact(spec) for _, _, spec in selected]
        has_more = start + len(selected) < len(ranked)
        next_cursor = (
            _encode_cursor(selected[-1][1]) if selected and has_more else None
        )
        data = {
            "matches": matches,
            "next_cursor": next_cursor,
            "total_matches": len(ranked),
        }
        return _success(
            f"Found {len(ranked)} matching actions.",
            data,
            matches=matches,
            next_cursor=next_cursor,
        )

    def describe(self, domain: str, action: str) -> dict:
        try:
            spec = self.registry.get(domain, action)
        except UnknownActionError:
            return error_result(
                code=ErrorCode.UNKNOWN_ACTION,
                message=f"Unknown action '{domain}.{action}'",
                path="params.action",
                hint="Call util.search_actions to find the action name.",
            ).model_dump(mode="json")
        data = spec.model_dump(mode="json")
        return _success(f"Description for {domain}.{action}.", data)

    async def get_capabilities(self, project_info_loader: ProjectInfoLoader) -> dict:
        settings = load_settings()
        unreal_data: dict = {
            "connected": False,
            "retry_hint": "Start Unreal Editor with the UnrealMCPython plugin, then retry.",
        }
        try:
            project_info = await project_info_loader()
            if isinstance(project_info, dict) and project_info.get("success"):
                unreal_data = {
                    "connected": True,
                    **{key: value for key, value in project_info.items() if key != "success"},
                }
            else:
                unreal_data = {
                    "connected": True,
                    "project_info_error": project_info,
                    "retry_hint": "Retry get_capabilities after checking the Unreal output log.",
                }
        except Exception as exc:
            unreal_data["error"] = str(exc)

        data = {
            "registry_version": 2,
            "action_count": self.registry.count,
            "domains": sorted(self.registry.export()),
            "server": {
                "fastmcp_version": version("fastmcp"),
                "discovery": True,
                "catalog_resource": "unreal://catalog",
                "gameplay_foundation_prompt": True,
            },
            "safety": {"mode": settings.safety_mode.value},
            "unreal": unreal_data,
        }
        return _success("Reported MCP and Unreal capabilities.", data)

    @staticmethod
    def _compact(spec) -> dict:
        return {
            "qualified_action": f"{spec.domain}.{spec.action}",
            "domain": spec.domain,
            "action": spec.action,
            "title": spec.title,
            "description": spec.description,
            "effect": spec.effect.value,
            "risk": spec.risk.value,
            "result_kind": spec.result_kind.value,
            "requires_confirmation": spec.requires_confirmation,
            "required_plugins": spec.required_plugins,
        }

    @staticmethod
    def _invalid(parameter: str, message: str) -> dict:
        return error_result(
            code=ErrorCode.INVALID_INPUT,
            message=message,
            path=f"params.{parameter}",
            retryable=True,
            hint=f"Correct params.{parameter} and retry util.search_actions.",
        ).model_dump(mode="json")
