# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Offline routing tests for the namespace dispatcher.

These do NOT need Unreal running. They mock the TCP layer (send_to_unreal /
send_python_exec / send_livecoding_compile) and assert that each domain tool
routes (action, params) to the correct module + ue_<action> + params.

Run:
    cd mcp-server && uv run pytest
"""

import asyncio
import importlib

import pytest

import unreal_mcp.dispatcher as disp
from unreal_mcp.dispatchers._catalog import CATALOG


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def recorder(monkeypatch):
    """Replace send_to_unreal with an async recorder; return the call log."""
    calls = []

    async def fake_send_to_unreal(module, fn, params):
        calls.append((module, fn, params))
        return {"success": True, "echo": {"module": module, "fn": fn, "params": params}}

    monkeypatch.setattr(disp, "send_to_unreal", fake_send_to_unreal)
    return calls


# ─── entrypoint smoke ─────────────────────────────────────────────────────────

def test_entrypoints_import():
    """main.py and server.py must import cleanly (catches removed public names)."""
    import unreal_mcp.server as server
    import unreal_mcp.main as main
    assert hasattr(server, "main_mcp")
    assert hasattr(server, "run_server")
    assert callable(main.main)


# ─── tool registration ────────────────────────────────────────────────────────

def test_domain_tools_match_catalog():
    """Exactly one MCP tool per catalog domain — no more, no less."""
    tools = disp.dispatcher_mcp._tool_manager.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(CATALOG.keys())


# ─── standard routing ─────────────────────────────────────────────────────────

def test_standard_routing_module_fn_params(recorder):
    result = run(disp._dispatch("actor", "set_location",
                                {"actor_label": "Cube", "location": [0, 0, 100]}))
    assert result["success"] is True
    assert recorder == [
        ("UnrealMCPython.actor_actions", "ue_set_location",
         {"actor_label": "Cube", "location": [0, 0, 100]})
    ]


def _standard_action_pairs():
    """Every (domain, action) routed via the standard path (excludes hand-written domains)."""
    pairs = []
    for domain in CATALOG:
        if domain in ("util", "vision"):
            continue  # special-cased handlers
        for action in CATALOG[domain]:
            pairs.append((domain, action))
    return pairs


@pytest.mark.parametrize("domain,action", _standard_action_pairs())
def test_every_catalog_action_routes(domain, action, recorder):
    """Full coverage: each catalog action routes to its module + ue_<action>."""
    run(disp._dispatch(domain, action, {}))
    module, fn, _ = recorder[0]
    assert module == f"UnrealMCPython.{domain}_actions"
    assert fn == f"ue_{action}"


def test_params_passed_through_untouched(recorder):
    payload = {"asset_path": "/Game/BP", "graph_name": "EventGraph", "node_json": {"type": "Branch"}}
    run(disp._dispatch("blueprint", "add_blueprint_node", payload))
    assert recorder[0][2] == payload  # dispatcher must not mutate/translate params


# ─── list_actions ─────────────────────────────────────────────────────────────

def test_list_actions_returns_catalog(recorder):
    result = run(disp._dispatch("material", "list_actions", {}))
    assert result["success"] is True
    assert result["domain"] == "material"
    assert result["actions"] == CATALOG["material"]
    assert recorder == []  # list_actions must NOT hit the TCP layer


def test_list_actions_entries_have_params_and_doc():
    for domain, actions in CATALOG.items():
        for action, info in actions.items():
            assert "params" in info and "doc" in info, f"{domain}.{action} missing keys"


# ─── error handling ───────────────────────────────────────────────────────────

def test_unknown_action_errors_without_tcp(recorder):
    result = run(disp._dispatch("actor", "fly_to_the_moon", {}))
    assert result["success"] is False
    assert "Unknown action" in result["message"]
    assert recorder == []  # never reaches the TCP layer


# ─── util special routing ─────────────────────────────────────────────────────

def test_util_execute_python(monkeypatch):
    seen = {}

    async def fake_exec(code):
        seen["code"] = code
        return {"success": True}

    monkeypatch.setattr(disp, "send_python_exec", fake_exec)
    result = run(disp.util.fn(action="execute_python", params={"code": "import unreal"}))
    assert result["success"] is True
    assert seen["code"] == "import unreal"


def test_util_execute_python_requires_code(monkeypatch):
    async def fake_exec(code):
        raise AssertionError("should not be called when code is missing")

    monkeypatch.setattr(disp, "send_python_exec", fake_exec)
    result = run(disp.util.fn(action="execute_python", params={}))
    assert result["success"] is False
    assert "code is required" in result["message"]


def test_util_livecoding_compile(monkeypatch):
    called = {"n": 0}

    async def fake_compile():
        called["n"] += 1
        return {"success": True}

    monkeypatch.setattr(disp, "send_livecoding_compile", fake_compile)
    result = run(disp.util.fn(action="livecoding_compile", params={}))
    assert result["success"] is True
    assert called["n"] == 1


def test_util_get_output_log_routes_to_ue_function(recorder):
    run(disp.util.fn(action="get_output_log", params={"line_count": 20}))
    assert recorder == [
        ("UnrealMCPython.util_actions", "ue_get_output_log", {"line_count": 20})
    ]


def test_util_list_actions(recorder):
    result = run(disp.util.fn(action="list_actions", params={}))
    assert result["actions"] == CATALOG["util"]
    assert recorder == []


def test_util_unknown_action(recorder):
    result = run(disp.util.fn(action="nope", params={}))
    assert result["success"] is False
    assert "Unknown action" in result["message"]
