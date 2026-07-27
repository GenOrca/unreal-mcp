"""FastMCP v3 public-API and legacy tool-contract tests."""

import asyncio
import copy
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.utilities.types import Image

from unreal_mcp.dispatcher import dispatcher_mcp
from unreal_mcp.dispatchers._catalog import CATALOG


def run(coro):
    return asyncio.run(coro)


def normalize_input_schema(schema):
    """Remove framework-only schema decoration while preserving semantics."""
    normalized = copy.deepcopy(schema)

    def remove_titles(value):
        if isinstance(value, dict):
            value.pop("title", None)
            for child in value.values():
                remove_titles(child)
        elif isinstance(value, list):
            for child in value:
                remove_titles(child)

    remove_titles(normalized)
    normalized.pop("additionalProperties", None)
    return normalized


def test_image_uses_supported_fastmcp_import():
    assert Image.__module__ == "fastmcp.utilities.types"


def test_public_list_tools_contains_each_domain():
    tools = run(dispatcher_mcp.list_tools())
    assert {tool.name for tool in tools} == set(CATALOG)


def test_in_memory_client_lists_tools():
    async def list_tools():
        async with Client(transport=dispatcher_mcp) as client:
            return await client.list_tools()

    tools = run(list_tools())
    assert {tool.name for tool in tools} == set(CATALOG)


def test_workflow_tool_is_optional_task_with_injected_progress():
    tools = {tool.name: tool for tool in run(dispatcher_mcp.list_tools())}
    workflow = tools["workflow"]
    assert workflow.task_config.mode == "optional"
    assert set(workflow.parameters["properties"]) == {"action", "params"}


def test_legacy_namespace_tool_golden_is_unchanged():
    golden_path = Path(__file__).parent / "golden" / "namespace_tools_v2.json"
    expected = {
        item["name"]: item
        for item in json.loads(golden_path.read_text(encoding="utf-8"))
    }
    actual = {
        tool.name: {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters,
        }
        for tool in run(dispatcher_mcp.list_tools())
    }
    for record in expected.values():
        record["inputSchema"] = normalize_input_schema(record["inputSchema"])
    for record in actual.values():
        record["inputSchema"] = normalize_input_schema(record["inputSchema"])

    assert {name: actual[name] for name in expected} == expected
