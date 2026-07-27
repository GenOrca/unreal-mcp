"""Offline tests for LLM-friendly registry discovery and capabilities."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from unreal_mcp.discovery import DiscoveryService
from unreal_mcp.registry import ActionRegistry


def test_search_actions_filters_effect_and_text():
    service = DiscoveryService(ActionRegistry())
    result = service.search(query="blueprint function", effect="write", limit=5)
    assert result["success"] is True
    assert result["matches"]
    assert all(item["effect"] == "write" for item in result["matches"])


def test_search_actions_uses_deterministic_cursor_pagination():
    service = DiscoveryService(ActionRegistry())
    first = service.search(domain="blueprint", limit=2)
    second = service.search(
        domain="blueprint", limit=2, cursor=first["next_cursor"]
    )
    assert first["next_cursor"]
    assert {item["qualified_action"] for item in first["matches"]}.isdisjoint(
        item["qualified_action"] for item in second["matches"]
    )


def test_search_actions_rejects_malformed_cursor():
    result = DiscoveryService(ActionRegistry()).search(cursor="not-a-cursor")
    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_INPUT"


def test_describe_action_returns_full_schema():
    result = DiscoveryService(ActionRegistry()).describe(
        "blueprint", "create_blueprint"
    )
    assert result["data"]["input_schema"]["type"] == "object"
    assert result["data"]["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_catalog_resource_is_registered():
    from unreal_mcp.dispatcher import dispatcher_mcp

    resources = await dispatcher_mcp.list_resources()
    assert "unreal://catalog" in {str(resource.uri) for resource in resources}


@pytest.mark.asyncio
async def test_gameplay_foundation_prompt_is_registered():
    from unreal_mcp.dispatcher import dispatcher_mcp

    prompts = await dispatcher_mcp.list_prompts()
    assert "gameplay_foundation" in {prompt.name for prompt in prompts}


@pytest.mark.asyncio
async def test_util_search_and_describe_are_local(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    async def fail_tcp(*args, **kwargs):
        raise AssertionError("local discovery must not contact Unreal")

    monkeypatch.setattr(dispatcher, "send_to_unreal", fail_tcp)
    searched = await dispatcher.util(
        action="search_actions", params={"query": "blueprint", "limit": 1}
    )
    described = await dispatcher.util(
        action="describe_action",
        params={"domain": "blueprint", "action": "create_blueprint"},
    )
    assert searched["success"] is True
    assert described["data"]["action"] == "create_blueprint"


@pytest.mark.asyncio
async def test_capabilities_succeeds_when_unreal_is_offline(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    async def offline(*args, **kwargs):
        raise dispatcher.UnrealExecutionError("editor offline")

    monkeypatch.setattr(dispatcher, "send_to_unreal", offline)
    result = await dispatcher.util(action="get_capabilities", params={})
    assert result["success"] is True
    assert result["data"]["unreal"]["connected"] is False
    assert result["data"]["unreal"]["retry_hint"]


def test_project_info_reports_concrete_availability_flags(monkeypatch):
    checked_plugins = []

    class PluginBlueprintLibrary:
        @staticmethod
        def is_plugin_enabled(name):
            checked_plugins.append(name)
            return name in {"EnhancedInput", "PythonScriptPlugin"}

    fake_unreal = SimpleNamespace(
        PluginBlueprintLibrary=PluginBlueprintLibrary,
        InputAction=object(),
        InputMappingContext=object(),
        WidgetBlueprint=object(),
        PythonScriptLibrary=object(),
        MCPythonHelper=object(),
        SystemLibrary=SimpleNamespace(
            get_game_name=lambda: "TestGame",
            get_engine_version=lambda: "5.6.0",
        ),
        Paths=SimpleNamespace(
            project_dir=lambda: "/Project/",
            project_content_dir=lambda: "/Project/Content/",
        ),
    )
    monkeypatch.setitem(sys.modules, "unreal", fake_unreal)
    action_file = (
        Path(__file__).parents[2]
        / "Plugins"
        / "UnrealMCPython"
        / "Content"
        / "Python"
        / "UnrealMCPython"
        / "util_actions.py"
    )
    spec = importlib.util.spec_from_file_location("_test_util_actions", action_file)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    result = json.loads(module.ue_get_project_info())

    assert result["project_name"] == "TestGame"
    assert result["engine_version"] == "5.6.0"
    assert result["availability"] == {
        "enhanced_input": True,
        "umg": True,
        "python_script_plugin": True,
        "live_coding": True,
    }
    assert {"EnhancedInput", "PythonScriptPlugin"}.issubset(checked_plugins)
