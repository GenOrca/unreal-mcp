# Unreal MCP Blueprint-First Gameplay Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend GenOrca Unreal MCP with LLM-friendly discovery, safe workflows, deep Blueprint authoring, and an idempotent workflow that creates and verifies a universal playable game foundation.

**Architecture:** Keep the current namespace dispatcher and legacy `(action, params)` calls. Add a generated Action Registry v2 and a workflow service in the Python MCP server; keep Unreal operations as small Python actions backed by narrow C++ editor helpers only where UE 5.6 lacks a stable Python API.

**Tech Stack:** Python 3.11+, FastMCP 3.2.4 with task support, Pydantic 2, pytest/pytest-asyncio, Unreal Engine 5.6-5.8 Python API, Unreal Editor C++, UBT, Enhanced Input, UMG.

---

## Scope and sequencing

The design contains four dependent stages, not four independent products. Execute tasks in order:

1. Registry, discovery, structured errors, and FastMCP 3 migration.
2. Safe workflow planning, confirmation, transactions, progress, cancellation, and undo.
3. Blueprint 2.0 inspection and authoring primitives.
4. Gameplay-foundation planning, application, verification, CI, and documentation.

Do not begin a later stage until the prior stage passes its offline gates. C++ UFUNCTION additions require a full editor-closed UBT build before in-editor tests.

## File responsibility map

### MCP server

- `mcp-server/src/unreal_mcp/contracts.py` — enums and Pydantic contracts shared by registry, dispatcher, and workflow code.
- `mcp-server/src/unreal_mcp/config.py` — startup settings and safety-mode parsing.
- `mcp-server/src/unreal_mcp/errors.py` — stable error construction and traceback sanitization.
- `mcp-server/src/unreal_mcp/registry.py` — read/query interface over the generated Action Registry.
- `mcp-server/src/unreal_mcp/special_action_specs.py` — literal specs for dispatcher-only backends.
- `mcp-server/src/unreal_mcp/discovery.py` — search, describe, capabilities, and MCP catalog resource.
- `mcp-server/src/unreal_mcp/policy.py` — compatible/strict dispatch decisions.
- `mcp-server/src/unreal_mcp/workflows/models.py` — plan, step, state, change, and fingerprint contracts.
- `mcp-server/src/unreal_mcp/workflows/tokens.py` — expiring single-use confirmation and undo tokens.
- `mcp-server/src/unreal_mcp/workflows/store.py` — in-memory plan state with async locking.
- `mcp-server/src/unreal_mcp/workflows/planner.py` — registry validation, dependency ordering, and arbitrary-action plans.
- `mcp-server/src/unreal_mcp/workflows/executor.py` — background execution, progress, cancellation, rollback, and verification.
- `mcp-server/src/unreal_mcp/workflows/handler.py` — namespace action routing for `workflow`.
- `mcp-server/src/unreal_mcp/workflows/gameplay_foundation.py` — recipe expansion and static verifier.
- `mcp-server/src/unreal_mcp/dispatchers/_registry.py` — generated complete ActionSpec data.
- `mcp-server/src/unreal_mcp/dispatchers/_catalog.py` — generated legacy view; never edit manually.

### Unreal plugin

- Every `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/*_actions.py` — literal `ACTION_METADATA` for existing actions.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py` — internal editor context, fingerprint, and transaction wrappers.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint2.py` — shared JSON validation and Blueprint 2.0 wrapper helpers.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py` — public `ue_*` wrappers retained in the existing `blueprint` domain.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/game_actions.py` — typed class-default and Enhanced Input helpers.
- `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h` — narrow reflected helper declarations.
- `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp` — transactions, undo, and asset fingerprints.
- `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp` — Blueprint inspection/member/graph primitives.

### Tests and docs

- New focused offline tests under `mcp-server/tests/`, one file per responsibility.
- New in-editor tests `test_workflow.py` and `test_gameplay_foundation.py`; extend `test_blueprint.py` for public Blueprint actions.
- `.github/workflows/test.yml` — FastMCP 3 offline gates.
- `.github/workflows/e2e-selfhosted.yml` — UE 5.6/5.7/5.8 manual matrix.
- `README.md` and `mcp-server/README.md` — strict mode, discovery, and gameplay workflow usage.

---

### Task 1: Pin and migrate to FastMCP 3.2.4

**Files:**
- Modify: `mcp-server/pyproject.toml`
- Modify: `mcp-server/uv.lock`
- Modify: `mcp-server/src/unreal_mcp/main.py`
- Modify: `mcp-server/src/unreal_mcp/dispatcher.py`
- Modify: `mcp-server/tests/test_dispatcher.py`
- Create: `mcp-server/tests/capture_legacy_tool_golden.py`
- Create: `mcp-server/tests/golden/namespace_tools_v2.json`
- Create: `mcp-server/tests/test_fastmcp_v3.py`

- [ ] **Step 1: Write the FastMCP 3 public-API test**

Before changing the lock, capture the normalized public contracts of the 21
existing namespace tools. The one-shot capture script uses the current FastMCP
2 manager only to read tool objects, writes sorted `name`, `description`, and
`inputSchema` records, and
refuses to overwrite an existing golden:

~~~python
import asyncio
import json
from pathlib import Path

from unreal_mcp.dispatcher import dispatcher_mcp


async def main():
    output = Path(__file__).parent / "golden" / "namespace_tools_v2.json"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    tools = dispatcher_mcp._tool_manager.list_tools()
    records = [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters,
        }
        for tool in sorted(tools, key=lambda item: item.name)
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
~~~

Run: `cd mcp-server; uv run python tests/capture_legacy_tool_golden.py`

Review that the file contains exactly the current 21 tools. The compatibility
test loads this immutable baseline and asserts every baseline tool still has the
same normalized description/schema; later additions such as `workflow` are
allowed but cannot change a baseline record.

~~~python
import json
from pathlib import Path

import pytest
from fastmcp import Client

from unreal_mcp.dispatcher import dispatcher_mcp
from unreal_mcp.dispatchers._catalog import CATALOG


@pytest.mark.asyncio
async def test_public_list_tools_contains_each_domain():
    tools = await dispatcher_mcp.list_tools()
    assert {tool.name for tool in tools} == set(CATALOG)


@pytest.mark.asyncio
async def test_in_memory_client_lists_tools():
    async with Client(transport=dispatcher_mcp) as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == set(CATALOG)


@pytest.mark.asyncio
async def test_legacy_namespace_tool_golden_is_unchanged():
    golden_path = Path(__file__).parent / "golden" / "namespace_tools_v2.json"
    expected = {item["name"]: item for item in json.loads(golden_path.read_text())}
    actual = {
        tool.name: {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters,
        }
        for tool in await dispatcher_mcp.list_tools()
    }
    assert {name: actual[name] for name in expected} == expected
~~~

- [ ] **Step 2: Run the test against the current lock**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_fastmcp_v3.py -q`

Expected: FAIL because FastMCP 2.7.1 does not expose the v3 `list_tools()`
contract used by the test. Immediately after updating the lock, collection also
fails until the removed FastMCP 2 root `Image` export and constructor
`description=` argument are migrated.

- [ ] **Step 3: Pin the runtime and test dependencies**

Use these dependency sections:

~~~toml
dependencies = [
    "fastmcp[tasks]==3.2.4",
    "jsonschema>=4.23,<5",
    "pydantic>=2.11,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.4",
    "pytest-asyncio>=1.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
~~~

Run: `cd mcp-server; uv lock --upgrade-package fastmcp`

Expected: `uv.lock` resolves `fastmcp 3.2.4` and the task extra dependencies.

- [ ] **Step 4: Migrate internal tool-list access**

Change `main.py::test_server` and `test_dispatcher.py::test_domain_tools_match_catalog` to await `dispatcher_mcp.list_tools()` and consume a list:

~~~python
async def test_server():
    print("Testing Unreal MCP Server")
    tools = await main_mcp.list_tools()
    print(f"Available tools: {[tool.name for tool in tools]}")
~~~

In `dispatcher.py`, migrate the two verified FastMCP 3.2.4 API changes:

~~~python
from fastmcp import FastMCP
from fastmcp.utilities.types import Image


dispatcher_mcp = FastMCP(
    name="UnrealMCP",
    instructions=(
        "Unreal Engine MCP via namespace dispatchers. "
        "Each domain tool accepts (action, params). "
        "Pass action='list_actions' to any tool to get available actions and parameter docs."
    ),
)
~~~

Keep each domain tool's `description=` unchanged; only the server constructor
renamed this concept to `instructions`. Add an import smoke assertion for
`fastmcp.utilities.types.Image` so a future FastMCP upgrade cannot silently
break the vision namespace at module import.

- [ ] **Step 5: Run the migration gate**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_fastmcp_v3.py tests/test_dispatcher.py tests/test_core.py -q`

Expected: PASS with no deprecation warnings from `get_tools` or private `_tool_manager` access.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/pyproject.toml mcp-server/uv.lock mcp-server/src/unreal_mcp/main.py mcp-server/src/unreal_mcp/dispatcher.py mcp-server/tests/test_dispatcher.py mcp-server/tests/capture_legacy_tool_golden.py mcp-server/tests/golden/namespace_tools_v2.json mcp-server/tests/test_fastmcp_v3.py
git commit -m "build: migrate MCP server to FastMCP 3"
~~~

---

### Task 2: Add shared contracts, settings, and structured errors

**Files:**
- Create: `mcp-server/src/unreal_mcp/contracts.py`
- Create: `mcp-server/src/unreal_mcp/config.py`
- Create: `mcp-server/src/unreal_mcp/errors.py`
- Create: `mcp-server/tests/test_contracts.py`
- Create: `mcp-server/tests/test_config.py`

- [ ] **Step 1: Write contract and configuration tests**

~~~python
import pytest

from unreal_mcp.config import SafetyMode, load_settings
from unreal_mcp.contracts import ActionSpec, Effect, ResultKind, Risk, ToolResult
from unreal_mcp.errors import error_result


def test_action_spec_rejects_destructive_without_confirmation():
    with pytest.raises(ValueError):
        ActionSpec(
            domain="asset",
            action="delete_asset",
            title="Delete asset",
            description="Delete one asset.",
            result_kind=ResultKind.JSON,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            effect=Effect.DESTRUCTIVE,
            risk=Risk.HIGH,
            idempotent=False,
            supports_preview=True,
            supports_undo=False,
            requires_confirmation=False,
            ue_versions=["5.6", "5.7", "5.8"],
        )


def test_settings_default_compatible_and_accept_strict():
    assert load_settings({}).safety_mode is SafetyMode.COMPATIBLE
    assert load_settings({"UNREAL_MCP_SAFETY_MODE": "strict"}).safety_mode is SafetyMode.STRICT


def test_settings_reject_unknown_mode():
    with pytest.raises(ValueError, match="UNREAL_MCP_SAFETY_MODE"):
        load_settings({"UNREAL_MCP_SAFETY_MODE": "unsafe"})


def test_error_result_is_actionable_and_sanitized():
    result = error_result(
        code="INVALID_INPUT",
        message="asset_path is required",
        path="params.asset_path",
        retryable=True,
        hint="Call describe_action for blueprint.create_blueprint.",
        details={"traceback": "secret stack", "received": None},
    )
    assert result.success is False
    assert result.errors[0].code == "INVALID_INPUT"
    assert result.errors[0].details == {"received": None}
    assert "secret stack" not in result.model_dump_json()
~~~

- [ ] **Step 2: Run tests to verify missing modules**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_contracts.py tests/test_config.py -q`

Expected: collection FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the contracts**

~~~python
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Effect(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResultKind(StrEnum):
    JSON = "json"
    IMAGE = "image"
    TEXT = "text"
    MIXED = "mixed"


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    CONFLICT = "CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    PLUGIN_REQUIRED = "PLUGIN_REQUIRED"
    UE_VERSION_UNSUPPORTED = "UE_VERSION_UNSUPPORTED"
    UE_UNAVAILABLE = "UE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    COMPILE_FAILED = "COMPILE_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ActionSpec(BaseModel):
    domain: str
    action: str
    title: str
    description: str
    result_kind: ResultKind
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    effect: Effect
    risk: Risk
    idempotent: bool
    supports_preview: bool
    supports_undo: bool
    requires_confirmation: bool
    ue_versions: list[str]
    required_plugins: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    error_examples: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_safety(self):
        if self.effect is Effect.DESTRUCTIVE and not self.requires_confirmation:
            raise ValueError("destructive actions require confirmation")
        if self.result_kind is ResultKind.JSON and self.output_schema is None:
            raise ValueError("json actions require output_schema")
        return self


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    path: str | None = None
    retryable: bool = False
    hint: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class ToolResult(BaseModel):
    success: bool
    status: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str
~~~

- [ ] **Step 4: Implement settings and error construction**

~~~python
# config.py
from dataclasses import dataclass
from enum import StrEnum
from os import environ
from typing import Mapping


class SafetyMode(StrEnum):
    COMPATIBLE = "compatible"
    STRICT = "strict"


@dataclass(frozen=True)
class Settings:
    safety_mode: SafetyMode
    debug: bool


def load_settings(values: Mapping[str, str] | None = None) -> Settings:
    source = environ if values is None else values
    raw_mode = source.get("UNREAL_MCP_SAFETY_MODE", "compatible").lower()
    try:
        mode = SafetyMode(raw_mode)
    except ValueError as exc:
        raise ValueError(
            "UNREAL_MCP_SAFETY_MODE must be 'compatible' or 'strict'"
        ) from exc
    return Settings(mode, source.get("UNREAL_MCP_DEBUG", "0") == "1")
~~~

~~~python
# errors.py
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from unreal_mcp.contracts import ErrorCode, ErrorDetail, ToolResult


_OMITTED_DETAIL_KEYS = {"traceback", "stack", "stacktrace", "exception"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in _OMITTED_DETAIL_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def error_result(
    *,
    code: ErrorCode | str,
    message: str,
    hint: str,
    path: str | None = None,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> ToolResult:
    trace_id = uuid4().hex
    error = ErrorDetail(
        code=code,
        message=message,
        path=path,
        retryable=retryable,
        hint=hint,
        details=_sanitize(details or {}),
        trace_id=trace_id,
    )
    return ToolResult(
        success=False,
        status="failed",
        summary=message,
        errors=[error],
        trace_id=trace_id,
    )
~~~

- [ ] **Step 5: Run tests**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_contracts.py tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/contracts.py mcp-server/src/unreal_mcp/config.py mcp-server/src/unreal_mcp/errors.py mcp-server/tests/test_contracts.py mcp-server/tests/test_config.py
git commit -m "feat: add MCP action and error contracts"
~~~

---

### Task 3: Generate Action Registry v2 and migrate all action metadata

**Files:**
- Create: `mcp-server/bootstrap_action_metadata.py`
- Create: `mcp-server/src/unreal_mcp/special_action_specs.py`
- Modify: `mcp-server/generate_catalog.py`
- Modify: `mcp-server/validate_tools.py`
- Create: `mcp-server/src/unreal_mcp/dispatchers/_registry.py`
- Modify: every `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/*_actions.py`
- Create: `mcp-server/tests/test_registry_generation.py`

- [ ] **Step 1: Write registry-generation failure tests**

~~~python
from jsonschema import Draft202012Validator

from generate_catalog import build_registry
from unreal_mcp.contracts import ToolResult


def test_every_catalog_action_has_complete_registry_spec():
    registry = build_registry()
    for domain, actions in registry.items():
        for action, spec in actions.items():
            assert spec["domain"] == domain
            assert spec["action"] == action
            assert spec["effect"] in {"read", "write", "destructive"}
            assert spec["risk"] in {"low", "medium", "high"}
            assert spec["result_kind"] in {"json", "image", "text", "mixed"}
            assert spec["input_schema"]["type"] == "object"
            assert spec["examples"], f"{domain}.{action} has no valid-call example"
            assert spec["error_examples"], f"{domain}.{action} has no error example"
            for example in spec["examples"]:
                assert example["action"] == action
                Draft202012Validator(spec["input_schema"]).validate(example["params"])
            for error_example in spec["error_examples"]:
                ToolResult.model_validate(error_example)


def test_destructive_actions_require_confirmation():
    registry = build_registry()
    destructive = [
        spec
        for actions in registry.values()
        for spec in actions.values()
        if spec["effect"] == "destructive"
    ]
    assert destructive
    assert all(spec["requires_confirmation"] for spec in destructive)
~~~

- [ ] **Step 2: Run to verify the registry does not exist**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_registry_generation.py -q`

Expected: FAIL because `build_registry` is not defined.

- [ ] **Step 3: Add literal specs for dispatcher-only actions**

~~~python
SPECIAL_ACTION_SPECS = {
    "util": {
        "execute_python": {
            "title": "Execute Unreal Python",
            "description": "Execute arbitrary Python in the Unreal editor.",
            "effect": "destructive",
            "risk": "high",
            "result_kind": "json",
            "idempotent": False,
            "supports_preview": False,
            "supports_undo": False,
            "requires_confirmation": True,
            "ue_versions": ["5.6", "5.7", "5.8"],
            "required_plugins": ["PythonScriptPlugin"],
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string", "minLength": 1}},
                "required": ["code"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"success": {"type": "boolean"}},
                "required": ["success"],
                "additionalProperties": True,
            },
        },
        "livecoding_compile": {
            "title": "Compile C++ with Live Coding",
            "description": "Run one Live Coding compilation and return diagnostics.",
            "effect": "write",
            "risk": "high",
            "result_kind": "json",
            "idempotent": False,
            "supports_preview": False,
            "supports_undo": False,
            "requires_confirmation": True,
            "ue_versions": ["5.6", "5.7", "5.8"],
            "required_plugins": [],
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"success": {"type": "boolean"}},
                "required": ["success"],
                "additionalProperties": True,
            },
        },
    }
}
~~~

- [ ] **Step 4: Implement the one-shot metadata bootstrap**

The script must parse each `ue_*` function, classify reads by the prefixes `get_`, `list_`, `find_`, `is_`, `capture_`, `project_`, and classify deletes, raw execution, level loading, project settings, and compilation with explicit high-risk overrides. It appends a literal map and refuses to overwrite an existing one.

~~~python
READ_PREFIXES = ("get_", "list_", "find_", "is_", "capture_", "project_")
DESTRUCTIVE_PREFIXES = ("delete_", "remove_")
HIGH_RISK = {
    "asset.delete_asset",
    "asset.delete_directory",
    "level.create_level",
    "level.load_level",
    "game.set_game_mode",
    "util.execute_console_command",
    "util.set_cvar",
}


def classify(domain: str, action: str) -> dict:
    qualified = f"{domain}.{action}"
    if action.startswith(READ_PREFIXES):
        effect, risk = "read", "low"
    elif action.startswith(DESTRUCTIVE_PREFIXES):
        effect, risk = "destructive", "high"
    else:
        effect, risk = "write", "medium"
    if qualified in HIGH_RISK:
        effect, risk = "destructive", "high"
    return {
        "title": action.replace("_", " ").title(),
        "effect": effect,
        "risk": risk,
        "result_kind": "image" if domain == "vision" and action.startswith("capture_") else "json",
        "idempotent": effect == "read",
        "supports_preview": effect != "read",
        "supports_undo": effect == "write",
        "requires_confirmation": effect != "read",
        "ue_versions": ["5.6", "5.7", "5.8"],
        "required_plugins": [],
    }
~~~

After the script writes all maps, manually review **every** generated entry before
committing. Unknown actions default to `write` so the bootstrap cannot silently
classify a mutation as a read. In particular, correct these classes and flags:

- All `delete_*`, `remove_*`, `rename_*`, `load_level`, `create_level`, `set_game_mode`, `execute_console_command`, `execute_python`, and `livecoding_compile` entries.
- Optional plugin requirements already documented in first-line docstrings.
- `vision` image results and dispatcher-only results.
- Read actions whose names do not begin with a read prefix, and write actions
  whose names misleadingly do begin with one (for example compile/health calls).
- `supports_preview` and `supports_undo` for imports, saves, console commands,
  project settings, PIE controls, and any backend that cannot actually roll back.

- [ ] **Step 5: Extend the generator**

Add AST readers for `ACTION_METADATA` and `SPECIAL_ACTION_SPECS`, generate JSON Schema from annotations/defaults, render both `_registry.py` and the legacy `_catalog.py`, and make `--check` compare both files. Preserve current parameter strings exactly in the legacy rendering.
Treat a `None` default on an annotated legacy parameter as the repository's
"required, validated inside" sentinel: include the field in `required` and do
not add `null` to its schema type. Add `format: unreal-asset-path` to parameters
explicitly marked as asset paths in metadata; do not guess formats solely from
arbitrary string values.

Generate one schema-valid call example for an action that does not provide one:
use `/Game/Example` for Unreal asset-path strings, the first enum value, `0` for
numbers, `false` for booleans, empty containers, and `"example"` for other
required strings. Validate generated examples with
`jsonschema.Draft202012Validator` before rendering. Generate one
complete structured-result `INVALID_INPUT` error example from the first
required parameter; for zero-parameter actions, use a rejected
`params.unexpected` additional property. Validate it with `ToolResult`. Explicit
`ACTION_METADATA` examples always take precedence.

The registry render must expose:

~~~python
ACTION_SPECS = {
    "blueprint": {
        "create_blueprint": {
            "domain": "blueprint",
            "action": "create_blueprint",
            "title": "Create Blueprint",
            "description": "Creates a Blueprint asset with the requested parent class.",
            "result_kind": "json",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_path": {"type": "string", "format": "unreal-asset-path"},
                    "parent_class_path": {"type": "string", "default": "/Script/Engine.Actor"},
                },
                "required": ["asset_path"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"success": {"type": "boolean"}},
                "required": ["success"],
                "additionalProperties": True,
            },
            "effect": "write",
            "risk": "medium",
            "idempotent": False,
            "supports_preview": True,
            "supports_undo": True,
            "requires_confirmation": True,
            "ue_versions": ["5.6", "5.7", "5.8"],
            "required_plugins": [],
            "examples": [
                {
                    "action": "create_blueprint",
                    "params": {"asset_path": "/Game/Example"},
                }
            ],
            "error_examples": [
                {
                    "success": False,
                    "status": "failed",
                    "summary": "asset_path is required",
                    "data": {},
                    "changes": [],
                    "warnings": [],
                    "errors": [
                        {
                            "code": "INVALID_INPUT",
                            "path": "params.asset_path",
                            "message": "asset_path is required",
                            "retryable": True,
                            "hint": "Provide params.asset_path and retry.",
                            "details": {},
                            "trace_id": "example-trace",
                        }
                    ],
                    "next_actions": [
                        {
                            "domain": "util",
                            "action": "describe_action",
                            "params": {"domain": "blueprint", "action": "create_blueprint"},
                        }
                    ],
                    "trace_id": "example-trace",
                }
            ],
        }
    }
}
~~~

- [ ] **Step 6: Generate and validate**

Run:

~~~powershell
cd mcp-server
uv run python bootstrap_action_metadata.py
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_registry_generation.py tests/test_dispatcher.py tests/test_coverage.py -q
~~~

Expected: catalog and registry checks pass; the registry action count equals the
legacy catalog action count exactly, including dispatcher-only actions once.

- [ ] **Step 7: Commit**

~~~powershell
git add mcp-server/bootstrap_action_metadata.py mcp-server/generate_catalog.py mcp-server/validate_tools.py mcp-server/src/unreal_mcp/special_action_specs.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py mcp-server/tests/test_registry_generation.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython
git commit -m "feat: generate rich MCP action registry"
~~~

---

### Task 4: Add registry queries, discovery tools, capabilities, and catalog resource

**Files:**
- Create: `mcp-server/src/unreal_mcp/registry.py`
- Create: `mcp-server/src/unreal_mcp/discovery.py`
- Modify: `mcp-server/src/unreal_mcp/special_action_specs.py`
- Modify: `mcp-server/src/unreal_mcp/dispatcher.py`
- Modify: `mcp-server/tests/test_coverage.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/util_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_util.py`
- Create: `mcp-server/tests/test_discovery.py`

- [ ] **Step 1: Write discovery tests**

~~~python
import json

import pytest

from unreal_mcp.discovery import DiscoveryService
from unreal_mcp.registry import ActionRegistry


def test_search_actions_filters_effect_and_text():
    service = DiscoveryService(ActionRegistry())
    result = service.search(query="blueprint function", effect="write", limit=5)
    assert result["success"] is True
    assert result["matches"]
    assert all(item["effect"] == "write" for item in result["matches"])


def test_describe_action_returns_full_schema():
    result = DiscoveryService(ActionRegistry()).describe("blueprint", "create_blueprint")
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
~~~

- [ ] **Step 2: Run tests**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_discovery.py -q`

Expected: FAIL because registry/discovery modules and resource are missing.

- [ ] **Step 3: Implement registry and cursor-based search**

`ActionRegistry` validates generated dictionaries into `ActionSpec` once, exposes `get`, `iter_actions`, and `legacy_catalog`, and returns deterministic sorted search results. Encode cursors as URL-safe JSON containing the last qualified action name; reject malformed cursors with `INVALID_INPUT`.

~~~python
class ActionRegistry:
    def __init__(self, raw: dict | None = None):
        source = ACTION_SPECS if raw is None else raw
        self._actions = {
            (domain, action): ActionSpec.model_validate(spec)
            for domain, actions in source.items()
            for action, spec in actions.items()
        }

    def get(self, domain: str, action: str) -> ActionSpec:
        try:
            return self._actions[(domain, action)]
        except KeyError as exc:
            raise UnknownActionError(domain, action) from exc

    def iter_actions(self):
        for key in sorted(self._actions):
            yield self._actions[key]
~~~

- [ ] **Step 4: Implement local discovery and the MCP resource**

Register `search_actions`, `describe_action`, and `get_capabilities` as local branches in the existing `util` namespace before TCP dispatch. Register:

Add those three actions to `SPECIAL_ACTION_SPECS["util"]` with complete input
and output schemas before regenerating. Mark them `read`/`low`, idempotent,
non-confirming, and supported on 5.6-5.8. `validate_tools.py` must fail if a
server-side special spec has no matching local branch, or a local branch has no
spec. This keeps `util/list_actions`, discovery, and `unreal://catalog` on the
same generated source of truth.

Extend `test_coverage.py`'s server-local classification with
`search_actions`, `describe_action`, and `get_capabilities`. These entries are
not debt/`KNOWN_UNTESTED`: assert that each maps to a named offline test in
`test_discovery.py`, while backend `ue_*` actions continue to require in-editor
coverage.

~~~python
@dispatcher_mcp.resource("unreal://catalog")
def action_catalog_resource() -> str:
    return json.dumps(
        {"version": 2, "actions": registry.export()},
        ensure_ascii=False,
    )
~~~

Register a prompt that teaches the safe sequence without embedding action
schemas that can drift:

~~~python
@dispatcher_mcp.prompt(name="gameplay_foundation")
def gameplay_foundation_prompt() -> str:
    return (
        "Inspect capabilities, call workflow plan_gameplay_foundation, "
        "review changes and conflicts, apply with the confirmation token, "
        "poll workflow get, then call verify_gameplay_foundation."
    )
~~~

`get_capabilities` combines local server/FastMCP/safety information with `ue_get_project_info`. If Unreal is offline it still succeeds with `unreal.connected=false` and a retry hint.

- [ ] **Step 5: Add an in-editor capability test**

Extend `test_util.py` to assert engine version, project name, and the availability flags for Enhanced Input, UMG, PythonScriptPlugin, and Live Coding. The action must use concrete checks such as `hasattr(unreal, "InputAction")` and plugin manager lookups without auto-enabling a plugin.

- [ ] **Step 6: Run gates**

Run:

~~~powershell
cd mcp-server
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_discovery.py tests/test_dispatcher.py tests/test_coverage.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/registry.py mcp-server/src/unreal_mcp/discovery.py mcp-server/src/unreal_mcp/special_action_specs.py mcp-server/src/unreal_mcp/dispatcher.py mcp-server/tests/test_discovery.py mcp-server/tests/test_coverage.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/util_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_util.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: add LLM action discovery and capabilities"
~~~

---

### Task 5: Enforce policy and structured errors without breaking compatibility mode

**Files:**
- Create: `mcp-server/src/unreal_mcp/policy.py`
- Modify: `mcp-server/src/unreal_mcp/dispatcher.py`
- Modify: `mcp-server/src/unreal_mcp/server.py`
- Create: `mcp-server/tests/test_policy.py`
- Modify: `mcp-server/tests/test_dispatcher.py`

- [ ] **Step 1: Write compatible and strict policy tests**

~~~python
import pytest

from unreal_mcp.config import SafetyMode
from unreal_mcp.policy import DispatchDecision, SafetyPolicy
from unreal_mcp.registry import ActionRegistry


def test_compatible_mode_allows_legacy_delete():
    spec = ActionRegistry().get("asset", "delete_asset")
    assert SafetyPolicy(SafetyMode.COMPATIBLE).decide(spec) is DispatchDecision.EXECUTE


def test_strict_mode_requires_plan_for_write():
    spec = ActionRegistry().get("blueprint", "create_blueprint")
    assert SafetyPolicy(SafetyMode.STRICT).decide(spec) is DispatchDecision.PLAN_REQUIRED


def test_strict_mode_allows_read():
    spec = ActionRegistry().get("asset", "get_asset_info")
    assert SafetyPolicy(SafetyMode.STRICT).decide(spec) is DispatchDecision.EXECUTE
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_policy.py -q`

Expected: FAIL because `policy.py` is missing.

- [ ] **Step 3: Implement policy**

~~~python
from enum import StrEnum

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import ActionSpec, Effect


class DispatchDecision(StrEnum):
    EXECUTE = "execute"
    PLAN_REQUIRED = "plan_required"


class SafetyPolicy:
    def __init__(self, mode: SafetyMode):
        self.mode = mode

    def decide(self, spec: ActionSpec) -> DispatchDecision:
        if self.mode is SafetyMode.STRICT and spec.effect is not Effect.READ:
            return DispatchDecision.PLAN_REQUIRED
        return DispatchDecision.EXECUTE
~~~

- [ ] **Step 4: Integrate policy additively**

At dispatcher startup, build settings, registry, policy, and discovery once. The
shared dispatch preflight resolves the spec, rejects unsupported UE versions or
missing required plugins with `UE_VERSION_UNSUPPORTED`/`PLUGIN_REQUIRED`, and
validates server-local and newly added actions with
`jsonschema.Draft202012Validator`. Keep legacy backend validation and its exact
result shape in `compatible` mode so existing missing-parameter/error responses
do not change. Workflow planning always schema-validates every wrapped action.

Before standard or special action execution, return this structured result when strict mode blocks a mutation:

~~~python
return error_result(
    code="CONFIRMATION_REQUIRED",
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
).model_dump(mode="json")
~~~

Keep `compatible` as the process default. Preserve the original dict from Unreal for legacy success/failure responses.
Workflow namespace actions are exempt from this direct-mutation block because
their own handler enforces the signed confirmation token. Convert dispatcher
exceptions for new/local actions to stable structured errors, log the sanitized
exception once with the same `trace_id`, and never expose the raw traceback
unless `UNREAL_MCP_DEBUG=1`.

- [ ] **Step 5: Run legacy golden and strict tests**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_policy.py tests/test_dispatcher.py tests/test_core.py tests/test_discovery.py -q`

Expected: PASS. Existing routing assertions remain unchanged under compatible
mode; strict writes, invalid local inputs, missing plugins, and unsupported
versions return their exact stable codes.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/policy.py mcp-server/src/unreal_mcp/dispatcher.py mcp-server/src/unreal_mcp/server.py mcp-server/tests/test_policy.py mcp-server/tests/test_dispatcher.py
git commit -m "feat: add compatible and strict dispatch policy"
~~~

---

### Task 6: Add workflow models, plan store, and expiring single-use tokens

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/__init__.py`
- Create: `mcp-server/src/unreal_mcp/workflows/models.py`
- Create: `mcp-server/src/unreal_mcp/workflows/tokens.py`
- Create: `mcp-server/src/unreal_mcp/workflows/store.py`
- Create: `mcp-server/tests/test_workflow_store.py`
- Create: `mcp-server/tests/test_workflow_tokens.py`

- [ ] **Step 1: Write replay, expiry, and concurrency tests**

~~~python
from datetime import UTC, datetime, timedelta

import pytest

from unreal_mcp.workflows.models import WorkflowPlan, WorkflowStatus
from unreal_mcp.workflows.store import WorkflowStore
from unreal_mcp.workflows.tokens import TokenService


def test_confirmation_token_is_single_use():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    token = service.issue_confirmation("plan-1", "digest-1", now=datetime(2026, 7, 27, tzinfo=UTC))
    assert service.consume_confirmation(token, "plan-1", "digest-1", now=datetime(2026, 7, 27, tzinfo=UTC))
    with pytest.raises(ValueError, match="already used"):
        service.consume_confirmation(token, "plan-1", "digest-1", now=datetime(2026, 7, 27, tzinfo=UTC))


def test_confirmation_token_expires():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    issued = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=issued)
    with pytest.raises(ValueError, match="expired"):
        service.consume_confirmation(token, "plan-1", "digest-1", now=issued + timedelta(minutes=11))


def test_confirmation_token_rejects_other_digest_without_consuming_it():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_confirmation("plan-1", "digest-1", now=now)
    with pytest.raises(ValueError, match="mismatch"):
        service.consume_confirmation(token, "plan-1", "digest-2", now=now)
    assert service.consume_confirmation(token, "plan-1", "digest-1", now=now)


def test_undo_token_is_bound_to_post_state_and_single_use():
    service = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    token = service.issue_undo("plan-1", "post-digest-1", now=now)
    with pytest.raises(ValueError, match="mismatch"):
        service.consume_undo(token, "plan-1", "changed", now=now)
    assert service.consume_undo(token, "plan-1", "post-digest-1", now=now)
    with pytest.raises(ValueError, match="already used"):
        service.consume_undo(token, "plan-1", "post-digest-1", now=now)


@pytest.mark.asyncio
async def test_store_compare_and_set_status():
    store = WorkflowStore()
    plan = WorkflowPlan.empty("plan-1")
    await store.put(plan)
    updated = await store.transition("plan-1", WorkflowStatus.PLANNED, WorkflowStatus.RUNNING)
    assert updated.status is WorkflowStatus.RUNNING
~~~

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_workflow_store.py tests/test_workflow_tokens.py -q`

Expected: FAIL on missing workflow modules.

- [ ] **Step 3: Implement exact workflow contracts**

Define `WorkflowStatus`, `ActionCall`, `ActionInvocation`, `AssetFingerprint`,
`PlanStep`, `ChangeRecord`, `WorkflowPlan`, and `WorkflowResult` as Pydantic
models. Use these exact field relationships so the planner, executor, recipe,
and tests share one vocabulary:

~~~python
class WorkflowStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    NEEDS_ATTENTION = "needs_attention"
    FAILED_ROLLED_BACK = "failed_rolled_back"
    FAILED_PARTIAL = "failed_partial"


class ActionCall(BaseModel):
    domain: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class ActionInvocation(ActionCall):
    id: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)


class AssetFingerprint(BaseModel):
    asset_path: str
    exists: bool
    package_guid: str | None = None
    disk_size: int | None = None
    modified_time: str | None = None
    dirty: bool = False


class PlanStep(BaseModel):
    invocation: ActionInvocation
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    postconditions: list[dict[str, Any]] = Field(default_factory=list)
    rollback_mode: Literal["transaction", "explicit", "snapshot", "none"]
    rollback: ActionCall | None = None
    pre_state_snapshot: dict[str, Any] | None = None
    effect: Effect
    risk: Risk
    asset_paths: list[str] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.invocation.id

    @property
    def dependencies(self) -> list[str]:
        return self.invocation.depends_on

    @model_validator(mode="after")
    def validate_rollback_payload(self):
        if self.rollback_mode == "explicit" and self.rollback is None:
            raise ValueError("explicit rollback requires rollback action")
        if self.rollback_mode == "snapshot" and self.pre_state_snapshot is None:
            raise ValueError("snapshot rollback requires pre_state_snapshot")
        return self


class ChangeRecord(BaseModel):
    step_id: str
    kind: Literal["create", "update", "reuse", "skip", "delete"]
    asset_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WorkflowPlan(BaseModel):
    id: str
    status: WorkflowStatus
    safety_mode: SafetyMode
    project_id: str
    editor_session_id: str
    current_map: str
    steps: list[PlanStep] = Field(default_factory=list)
    asset_fingerprints: dict[str, AssetFingerprint] = Field(default_factory=dict)
    predicted_changes: list[ChangeRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confirmation_token: str | None = None
    undo_token: str | None = None
    step_results: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def empty(cls, plan_id: str) -> "WorkflowPlan":
        return cls(
            id=plan_id,
            status=WorkflowStatus.PLANNED,
            safety_mode=SafetyMode.COMPATIBLE,
            project_id="test-project",
            editor_session_id="test-session",
            current_map="/Game/TestMap",
        )

    def digest(self) -> str:
        signed = self.model_dump(
            mode="json",
            exclude={
                "status", "created_at", "confirmation_token", "undo_token",
                "step_results",
            },
        )
        payload = json.dumps(signed, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()
~~~

`WorkflowResult` mirrors the structured result envelope and narrows `status` to
`WorkflowStatus`. Status, timestamps, tokens, and execution results are not
signed; all operation parameters, conflict-policy inputs, editor identity,
fingerprints, and safety mode are signed. `WorkflowStore` is the only code that
may transition status or append step results.

- [ ] **Step 4: Implement HMAC tokens and the locked store**

Use URL-safe base64 JSON payloads signed with `hmac.new(secret, payload, sha256)`. The payload contains token kind, plan id, digest, issued-at, expiry, and random nonce. Keep consumed nonces in memory until expiry. `WorkflowStore` uses one `asyncio.Lock` and returns deep model copies so callers cannot mutate stored plans without `put`/`transition`.

- [ ] **Step 5: Run tests**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_workflow_store.py tests/test_workflow_tokens.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/workflows mcp-server/tests/test_workflow_store.py mcp-server/tests/test_workflow_tokens.py
git commit -m "feat: add workflow state and confirmation tokens"
~~~

---

### Task 7: Implement arbitrary-action planning and stale-state checks

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/planner.py`
- Create: `mcp-server/tests/test_workflow_planner.py`

- [ ] **Step 1: Write planner tests**

~~~python
import pytest

from unreal_mcp.workflows.models import ActionInvocation
from unreal_mcp.workflows.planner import WorkflowPlanner


@pytest.mark.asyncio
async def test_plan_orders_dependencies_and_collects_assets(fake_registry, fake_context):
    planner = WorkflowPlanner(fake_registry, fake_context)
    plan = await planner.plan([
        ActionInvocation(id="compile", domain="blueprint", action="compile_blueprint",
                         params={"asset_path": "/Game/BP_Player"}, depends_on=["create"]),
        ActionInvocation(id="create", domain="blueprint", action="create_blueprint",
                         params={"asset_path": "/Game/BP_Player"}),
    ])
    assert [step.id for step in plan.steps] == ["create", "compile"]
    assert "/Game/BP_Player" in plan.asset_fingerprints


@pytest.mark.asyncio
async def test_plan_rejects_cycle(fake_registry, fake_context):
    planner = WorkflowPlanner(fake_registry, fake_context)
    with pytest.raises(ValueError, match="dependency cycle"):
        await planner.plan([
            ActionInvocation(id="a", domain="asset", action="save_asset",
                             params={"asset_path": "/Game/A"}, depends_on=["b"]),
            ActionInvocation(id="b", domain="asset", action="save_asset",
                             params={"asset_path": "/Game/B"}, depends_on=["a"]),
        ])
~~~

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_workflow_planner.py -q`

Expected: FAIL because `WorkflowPlanner` is missing.

- [ ] **Step 3: Implement planner validation**

For each invocation:

1. Resolve the `ActionSpec`.
2. Validate params with `jsonschema.Draft202012Validator`.
3. Reject nested `workflow` calls.
4. Require unique step ids and existing dependency ids.
5. Topologically sort with deterministic lexical tie-breaking.
6. Extract asset paths from schema fields carrying `format: unreal-asset-path`.
7. Ask the editor-context provider for project/session/map and fingerprints.
8. Compute predicted change records and rollback availability.
9. Persist the plan as `awaiting_confirmation` and issue a ten-minute token.

Copy the returned token into `plan.confirmation_token` only after computing the
digest; the token itself is excluded from `digest()`. All subsequent apply paths
must receive that token explicitly rather than trusting only a plan id.

Return `CONFIRMATION_REQUIRED` details for non-undoable steps but allow explicit `allow_non_undoable=true` to enter the signed digest.

- [ ] **Step 4: Add stale-state verification**

Implement `WorkflowPlanner.verify_preconditions(plan)` to fetch current context and compare project id, editor session id, current map, and every fingerprint. Return all mismatches in one `PRECONDITION_FAILED` result; perform no writes.

- [ ] **Step 5: Run tests**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_workflow_planner.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/workflows/planner.py mcp-server/tests/test_workflow_planner.py
git commit -m "feat: plan and fingerprint MCP workflows"
~~~

---

### Task 8: Add Unreal editor fingerprints, scoped transactions, and undo

**Files:**
- Create: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py`
- Create: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_workflow.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/run_all.py`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h`
- Create: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/UnrealMCPython.Build.cs`

- [ ] **Step 1: Write in-editor tests first**

~~~python
class TestWorkflowActions(MCPTestCase):
    def test_editor_context_contains_stable_fields(self):
        result = self.call(
            "workflow_actions",
            "ue_get_editor_context",
            asset_paths=[],
        )
        self.assertSuccess(result)
        self.assertIn("project_id", result)
        self.assertIn("editor_session_id", result)
        self.assertIn("engine_version", result)
        self.assertIn("current_map", result)

    def test_transaction_can_begin_commit_and_undo(self):
        tx_id = "mcp_test_transaction"
        spawned = self.call(
            "actor_actions", "ue_spawn_from_class",
            class_path="/Script/Engine.Actor",
            location=[0.0, 0.0, 0.0],
        )
        self.assertSuccess(spawned)
        label = spawned["actor_label"]
        try:
            self.assertSuccess(self.call(
                "workflow_actions", "ue_begin_transaction",
                transaction_id=tx_id, description="MCP test transaction",
            ))
            self.assertSuccess(self.call(
                "actor_actions", "ue_set_location",
                actor_label=label, location=[100.0, 0.0, 0.0],
            ))
            self.assertSuccess(self.call(
                "workflow_actions", "ue_commit_transaction",
                transaction_id=tx_id,
            ))
            self.assertSuccess(self.call(
                "workflow_actions", "ue_undo_transaction",
                transaction_id=tx_id,
            ))
            restored = self.call(
                "actor_actions", "ue_get_transform", actor_label=label,
            )
            self.assertEqual(restored["location"], [0.0, 0.0, 0.0])
        finally:
            self.call("actor_actions", "ue_delete_by_label", actor_label=label)
~~~

- [ ] **Step 2: Add C++ declarations**

~~~cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString GetWorkflowEditorContext(const TArray<FString>& AssetPaths);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString BeginWorkflowTransaction(const FString& TransactionId, const FString& Description);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString CommitWorkflowTransaction(const FString& TransactionId);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString CancelWorkflowTransaction(const FString& TransactionId);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString RollbackWorkflowTransaction(const FString& TransactionId);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString UndoWorkflowTransaction(const FString& TransactionId);
~~~

- [ ] **Step 3: Implement the workflow helper**

Use one guarded `TUniquePtr<FScopedTransaction>` and transaction id in an anonymous namespace. Reject nested/mismatched transaction ids. For each asset path, query `IAssetRegistry::GetAssetPackageData` and return package GUID, disk size, file timestamp, and dirty state. Context also returns `FApp::GetProjectName()`, an editor-session UUID created when the module loads, `FEngineVersion::Current()`, and the current world package name.

`CancelWorkflowTransaction` calls `FScopedTransaction::Cancel()` before reset
and is used only when no successful write step has run; Unreal cancellation
discards/prevents undo recording and must not be treated as state restoration.
`RollbackWorkflowTransaction` closes the active transaction and immediately
calls `GEditor->UndoTransaction()` to restore transactional mutations.
`UndoWorkflowTransaction` rejects an active transaction and calls
`GEditor->UndoTransaction()` only after the Python server has validated
post-state fingerprints. Every helper reports the transaction index and whether
the undo call succeeded.

- [ ] **Step 4: Add Python wrappers**

~~~python
def ue_get_editor_context(asset_paths: list[str] = None) -> str:
    """Returns project, editor-session, map, engine, and asset fingerprints."""
    return unreal.MCPythonHelper.get_workflow_editor_context(asset_paths or [])


def ue_begin_transaction(transaction_id: str = None, description: str = None) -> str:
    """Begins one scoped MCP workflow transaction."""
    if not transaction_id or not description:
        return json.dumps({"success": False, "message": "transaction_id and description are required"})
    return unreal.MCPythonHelper.begin_workflow_transaction(transaction_id, description)
~~~

Implement matching commit, cancel, rollback, and undo wrappers with
required-parameter guards. Add an in-editor test that begins a transaction,
mutates an actor, calls rollback while the transaction is active, and verifies
the original transform; this distinguishes actual rollback from transaction
cancellation.

- [ ] **Step 5: Declare the direct Asset Registry dependency**

Add `"AssetRegistry"` to `PrivateDependencyModuleNames` in
`UnrealMCPython.Build.cs`. Do not add Enhanced Input or UMG as hard C++
dependencies; those remain guarded Python-side optional capabilities.

- [ ] **Step 6: Register the in-editor test module**

Add `UnrealMCPython.tests.test_workflow` to `run_all.py`. Keep this module outside the public catalog; the MCP workflow service calls it directly through `send_to_unreal`.

- [ ] **Step 7: Full-build the plugin with the editor closed**

Run:

~~~powershell
$taskUeRoot = $env:UE_ROOT
if (-not $taskUeRoot) { throw "Set UE_ROOT to the Unreal Engine installation root." }
$taskBuild = Join-Path $taskUeRoot "Engine\Build\BatchFiles\Build.bat"
& $taskBuild UnrealEditor Win64 Development "-project=$((Resolve-Path 'UnrealMCPSample.uproject').Path)" -waitmutex
~~~

Expected: UBT exits 0. Reopen the editor only after the build completes.

- [ ] **Step 8: Run the in-editor workflow test**

From the Unreal Python console:

~~~python
import unittest
from UnrealMCPython.tests.test_workflow import TestWorkflowActions
unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestWorkflowActions)
)
~~~

Expected: all workflow action tests pass and the editor remains alive.

- [ ] **Step 9: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_workflow.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/run_all.py Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp Plugins/UnrealMCPython/Source/UnrealMCPython/UnrealMCPython.Build.cs
git commit -m "feat: add Unreal workflow transactions and fingerprints"
~~~

---

### Task 9: Implement background workflow execution, progress, cancellation, rollback, and namespace routing

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/executor.py`
- Create: `mcp-server/src/unreal_mcp/workflows/handler.py`
- Modify: `mcp-server/src/unreal_mcp/special_action_specs.py`
- Modify: `mcp-server/src/unreal_mcp/dispatcher.py`
- Modify: `mcp-server/tests/test_coverage.py`
- Create: `mcp-server/tests/test_workflow_executor.py`
- Create: `mcp-server/tests/test_workflow_handler.py`

- [ ] **Step 1: Write executor state-transition tests**

~~~python
import asyncio
import pytest

from unreal_mcp.workflows.models import WorkflowStatus


@pytest.mark.asyncio
async def test_executor_rolls_back_completed_steps_on_failure(executor, plan):
    executor.backend.fail_on("compile")
    result = await executor.run(plan.id, plan.confirmation_token)
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert executor.backend.calls == [
        "begin", "create", "compile", "rollback_transaction", "rollback:create",
    ]


@pytest.mark.asyncio
async def test_cancel_is_observed_between_steps(executor, plan):
    task = asyncio.create_task(executor.run(plan.id, plan.confirmation_token))
    await executor.backend.first_step_started.wait()
    await executor.cancel(plan.id)
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert executor.backend.no_step_was_interrupted is True
~~~

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_workflow_executor.py tests/test_workflow_handler.py -q`

Expected: FAIL because executor/handler modules are missing.

- [ ] **Step 3: Implement executor**

`WorkflowExecutor.start(plan_id, confirmation_token)` creates one named
`asyncio.Task` and stores a cancellation event.
`run(plan_id, confirmation_token, progress=None)` atomically consumes the
explicit confirmation token, rechecks preconditions, begins the Unreal
transaction, executes steps in dependency order, records normalized change
records, and checks cancellation before and after each step. A missing,
mismatched, expired, or replayed token returns `CONFIRMATION_REQUIRED` (or
`CONFIRMATION_EXPIRED` for TTL expiry) before the backend receives `begin`.

On step failure:

1. Close and undo the active Unreal transaction for steps marked transaction-safe.
2. Execute explicit inverse actions or restore snapshots only for completed
   non-transactional steps, in reverse dependency order.
3. Re-fingerprint affected assets.
4. Return `failed_rolled_back` only if no residual change remains; otherwise return `failed_partial` with every residual.

Use the same rollback path for cancellation after any successful write. Call
`cancel_transaction` only when cancellation/precondition failure occurs before
the first successful write. Each `PlanStep` records exactly one primary
rollback mode (`transaction`, `explicit`, `snapshot`, or `none`) so the executor
cannot both undo and apply an inverse to the same mutation.

On success, commit the transaction, fingerprint post-state, run declared verifiers, and issue a single-use undo token.

- [ ] **Step 4: Implement task-aware workflow routing**

Add complete server-side specs for `workflow/plan`, `apply`, `get`, `cancel`,
`undo`, `plan_gameplay_foundation`, and `verify_gameplay_foundation` to
`SPECIAL_ACTION_SPECS`, then regenerate `_registry.py` and `_catalog.py`.
Add `workflow` to dispatcher `_SPECIAL_DOMAINS` before regeneration so the
standard loop cannot register a duplicate TCP-backed tool.
`workflow/list_actions` must render the generated workflow catalog, and
`util/describe_action` must be able to describe every workflow action. The
special-handler validator must treat these as branches of the single workflow
namespace handler. Do not allow generic `workflow/plan` to wrap another
workflow action.
Classify all workflow branches as server-local in `test_coverage.py` and map
each one to a concrete test name in `test_workflow_handler.py`; do not add them
to `KNOWN_UNTESTED`.

Register the namespace with FastMCP task support:

~~~python
from fastmcp.dependencies import Progress


@dispatcher_mcp.tool(name="workflow", task=True)
async def workflow(
    action: str,
    params: dict | None = None,
    progress: Progress = Progress(),
) -> dict:
    return await workflow_handler.handle(action, params or {}, progress)
~~~

For `apply`:

- Require both `plan_id` and `confirmation_token`.
- `wait_for_completion=true` awaits `executor.run(plan_id, confirmation_token, progress)` and forwards step totals/messages through `Progress`; task-capable clients use this mode.
- The default calls `executor.start(plan_id, confirmation_token)` and returns `running` with `workflow_id`; other clients poll `get`.
- `cancel` sets the cancellation event.
- `undo` validates the undo token and post-state before calling the internal Unreal undo action.

The workflow handler applies its own signed-token policy and therefore bypasses
the direct-action strict-mode block from Task 5. It still resolves every branch
through the generated workflow specs and validates params before routing.

- [ ] **Step 5: Run workflow tests**

Run:

~~~powershell
cd mcp-server
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_workflow_store.py tests/test_workflow_tokens.py tests/test_workflow_planner.py tests/test_workflow_executor.py tests/test_workflow_handler.py tests/test_dispatcher.py tests/test_coverage.py -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add mcp-server/src/unreal_mcp/workflows/executor.py mcp-server/src/unreal_mcp/workflows/handler.py mcp-server/src/unreal_mcp/special_action_specs.py mcp-server/src/unreal_mcp/dispatcher.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py mcp-server/tests/test_workflow_executor.py mcp-server/tests/test_workflow_handler.py mcp-server/tests/test_coverage.py
git commit -m "feat: execute cancellable transactional workflows"
~~~

---

### Task 10: Add compact Blueprint brief and filtered inspection

**Files:**
- Create: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint2.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h`
- Create: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp`

- [ ] **Step 1: Write in-editor inspection tests**

~~~python
def test_blueprint_brief_is_compact_and_stable(self):
    result = self.call(
        "blueprint_actions", "ue_get_blueprint_brief",
        asset_path=self._bp_path,
    )
    self.assertSuccess(result)
    self.assertEqual(result["asset_path"], self._bp_path)
    self.assertIn("parent_class", result)
    self.assertIn("compile_status", result)
    self.assertIn("counts", result)


def test_inspect_blueprint_paginates_nodes(self):
    first = self.call(
        "blueprint_actions", "ue_inspect_blueprint",
        asset_path=self._bp_path,
        queries=[{"op": "nodes", "graph": "EventGraph"}],
        limit=1,
    )
    self.assertSuccess(first)
    self.assertLessEqual(len(first["results"][0]["items"]), 1)
    if first["results"][0].get("next_cursor"):
        second = self.call(
            "blueprint_actions", "ue_inspect_blueprint",
            asset_path=self._bp_path,
            queries=[{"op": "nodes", "graph": "EventGraph"}],
            limit=1,
            cursor=first["results"][0]["next_cursor"],
        )
        self.assertSuccess(second)
~~~

- [ ] **Step 2: Add C++ helper declarations**

~~~cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString GetBlueprintBrief(UBlueprint* Blueprint);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString InspectBlueprint(UBlueprint* Blueprint, const FString& QueryJson);
~~~

- [ ] **Step 3: Implement compact serialization**

In `MCPythonHelper_Blueprint2.cpp`:

- Use `FBlueprintEditorUtils::GetAllGraphs` and Blueprint member arrays.
- Use graph/node/variable/member GUID strings as stable ids, SCS variable GUIDs
  for components, and never array indexes. When an old asset lacks a persisted
  GUID, return a deterministic qualified-name fallback marked `stable=false`.
- Serialize only requested queries: `overview`, `variables`,
  `variable_defaults`, `components`, `component_hierarchy`, `functions`,
  `macros`, `events`, `dispatchers`, `interfaces`, `nodes`, `pins`, and
  `connections`.
- Sort by stable id/name before pagination.
- Encode cursor as the last stable id and reject unknown/mismatched cursors.
- Include node class, title, position, typed pins, defaults, and linked node/pin ids only when requested.

- [ ] **Step 4: Add Python wrappers**

~~~python
def ue_get_blueprint_brief(asset_path: str = None) -> str:
    """Returns a compact Blueprint orientation summary with stable identifiers."""
    bp, err = _load_asset(asset_path, unreal.Blueprint)
    return err or unreal.MCPythonHelper.get_blueprint_brief(bp)


def ue_inspect_blueprint(
    asset_path: str = None,
    queries: list[dict] = None,
    limit: int = 100,
    cursor: str = "",
    compact: bool = True,
) -> str:
    """Runs filtered, paginated Blueprint inspection queries."""
    bp, err = _load_asset(asset_path, unreal.Blueprint)
    if err:
        return err
    spec = {"queries": queries or [{"op": "overview"}], "limit": limit,
            "cursor": cursor, "compact": compact}
    return unreal.MCPythonHelper.inspect_blueprint(bp, json.dumps(spec))
~~~

- [ ] **Step 5: Full-build and test**

Run the UBT command from Task 8 with the editor closed, reopen, run `TestBlueprintActions`, regenerate the catalog, and run offline coverage.

Expected: inspection tests pass; every new action appears in catalog and coverage.

- [ ] **Step 6: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint2.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: add compact Blueprint inspection"
~~~

---

### Task 11: Add Blueprint function, macro, event, dispatcher, and interface authoring

**Files:**
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp`

- [ ] **Step 1: Add table-driven in-editor tests**

Create tests that:

- create, rename, set typed inputs/outputs, and delete a function;
- edit, reorder, and remove individual function inputs/outputs by submitting the
  complete desired signature and verifying pin order and types;
- create and delete a macro;
- create and delete a custom event;
- add and remove an event dispatcher;
- add and remove a Blueprint interface, and verify every required interface
  function/event graph is implemented;
- compile after the batch and verify each member through `ue_inspect_blueprint`.

Use one mutation-spec shape:

~~~python
signature = {
    "inputs": [{"name": "Amount", "type": "real"}],
    "outputs": [{"name": "Applied", "type": "bool"}],
    "pure": False,
    "const": False,
    "access": "public",
    "category": "MCP|Tests",
}
~~~

- [ ] **Step 2: Add C++ JSON entry points**

~~~cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString MutateBlueprintMember(UBlueprint* Blueprint, const FString& Operation, const FString& SpecJson);
~~~

Supported operations are exactly:

`create_function`, `rename_function`, `set_function_signature`, `delete_function`, `create_macro`, `delete_macro`, `create_custom_event`, `delete_custom_event`, `add_dispatcher`, `remove_dispatcher`, `add_interface`, and `remove_interface`.

- [ ] **Step 3: Implement member mutation with stable UE editor APIs**

Use `FBlueprintEditorUtils::CreateNewGraph`, `AddFunctionGraph`, `AddMacroGraph`, `RenameGraph`, `RemoveGraph`, `AddMemberVariable`, `RemoveMemberVariable`, `ImplementNewInterface`, and `RemoveInterface`. Use `FScopedTransaction`/`Modify()`, mark the Blueprint structurally modified, and defer compilation to the caller. Return member ids/names and a structured change list; never save or compile inside these narrow helpers.
Creation specs use names; rename/edit/delete specs target the stable member or
graph GUID returned by inspection, with the current name accepted only as an
explicit compatibility fallback. Interface addition verifies and returns the
GUIDs of generated implementation graphs.

- [ ] **Step 4: Add public wrappers**

Add one `ue_*` wrapper per public action named:

`create_function`, `rename_function`, `set_function_signature`, `delete_function`, `create_macro`, `delete_macro`, `create_custom_event`, `delete_custom_event`, `add_event_dispatcher`, `remove_event_dispatcher`, `add_blueprint_interface`, and `remove_blueprint_interface`.

Each wrapper validates required fields, loads a Blueprint, and calls `mutate_blueprint_member` with an explicit operation and JSON spec.

- [ ] **Step 5: Full-build, run in-editor tests, regenerate, and run offline gates**

Expected: all members appear in inspection before deletion, disappear after deletion, and the Blueprint compiles without errors.

- [ ] **Step 6: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: author Blueprint members and interfaces"
~~~

---

### Task 12: Add reflected nodes, pin disconnects, typed variable defaults, and component reparenting

**Files:**
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp`

- [ ] **Step 1: Write in-editor tests for each operation family**

Test:

- reflected call node for `/Script/Engine.KismetSystemLibrary:PrintString`;
- branch, sequence, cast, variable get/set, arithmetic/comparison operator,
  reflected event, select/switch, reroute, comment, and make/break struct nodes;
- valid connect, explicit disconnect, and incompatible connect diagnostics;
- set arbitrary supported node properties by GUID while retaining existing
  position, delete, and auto-layout actions;
- primitive, enum, struct, object/class, soft reference, array, set, and map defaults;
- category, tooltip, visibility, instance editability, `ExposeOnSpawn`,
  `SaveGame`, cinematic exposure, and replication metadata;
- component add/remove/rename/reparent/reorder/transform/default property changes.

Assert inserted conversion nodes are listed in the connect response.

- [ ] **Step 2: Add C++ entry points**

~~~cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString AddReflectedBlueprintNode(UBlueprint* Blueprint, const FString& GraphName, const FString& SpecJson);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString MutateBlueprintNode(UBlueprint* Blueprint, const FString& GraphName,
    const FString& NodeId, const FString& Operation, const FString& SpecJson);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString DisconnectBlueprintPins(UBlueprint* Blueprint, const FString& GraphName,
    const FString& SourceNodeId, const FString& SourcePin,
    const FString& TargetNodeId, const FString& TargetPin);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString MutateBlueprintVariable(UBlueprint* Blueprint, const FString& Operation, const FString& SpecJson);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString ReparentBlueprintComponent(UBlueprint* Blueprint, const FString& ComponentId,
    const FString& ParentId, int32 SiblingIndex);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString RenameBlueprintComponent(UBlueprint* Blueprint, const FString& ComponentId,
    const FString& NewName);
~~~

- [ ] **Step 3: Implement reflection and type conversion**

Resolve reflected functions/classes by full object path, create K2 nodes through the graph schema/action APIs, call `AllocateDefaultPins`, and return the node GUID. Resolve every node mutation by GUID, not display name. Use `UEdGraphSchema_K2::TryCreateConnection` and compare the graph before/after to report conversion nodes. Extend the existing `ue_add_blueprint_node` implementation to the listed common node families; reserve `ue_add_reflected_node` for full Unreal object paths.

Centralize pin-type parsing and default-value import. Reject unsupported UE-version-specific types with `UE_VERSION_UNSUPPORTED` rather than coercing them. Node-property mutation uses an allowlist per node class and returns `INVALID_INPUT` for read-only or unknown properties. Variable mutations target the variable GUID from inspection. Component mutations target SCS variable GUIDs; reparenting with `sibling_index` performs ordering, and renaming preserves references and rejects collisions.

- [ ] **Step 4: Add public wrappers and metadata**

Add:

- `ue_add_reflected_node`
- `ue_set_blueprint_node_properties`
- `ue_disconnect_blueprint_pins`
- `ue_set_variable_default`
- `ue_set_variable_metadata`
- `ue_set_variable_replication`
- `ue_rename_blueprint_component`
- `ue_reparent_blueprint_component`

All are write/medium, previewable, undoable, and confirmation-required in strict mode.

- [ ] **Step 5: Full-build and run all Blueprint gates**

Run the UBT command, then in-editor `TestBlueprintActions`, then:

~~~powershell
cd mcp-server
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_dispatcher.py tests/test_coverage.py -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: add reflected Blueprint graph editing"
~~~

---

### Task 13: Add Blueprint health, compile diagnostics, and graph diff

**Files:**
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/UnrealMCPython.Build.cs`
- Create: `mcp-server/tests/test_blueprint_result_contract.py`

- [ ] **Step 1: Write broken-Blueprint tests**

Construct one test Blueprint with an intentionally incompatible/unresolved node and assert:

~~~python
health = self.call(
    "blueprint_actions", "ue_get_blueprint_health",
    asset_path=self._bp_path,
)
self.assertFalse(health["success"])
self.assertIn(health["status"], {"compile_error", "needs_attention"})
self.assertTrue(health["diagnostics"])
self.assertTrue(all("code" in item and "hint" in item for item in health["diagnostics"]))
~~~

Also snapshot a valid graph, add a node, and assert
`ue_diff_blueprint_graphs` reports exactly one added stable node id. Add a
large-diff case that requests compact output with `limit=1`, follows
`next_cursor`, and requests detailed records explicitly.

- [ ] **Step 2: Implement C++ health and snapshot entry points**

~~~cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString GetBlueprintHealth(UBlueprint* Blueprint);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString SnapshotBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString DiffBlueprintGraphSnapshots(const FString& BeforeJson, const FString& AfterJson);
~~~

Compile through `FKismetEditorUtilities::CompileBlueprint` with a results log. Return errors/warnings with node GUID, graph, message, severity, code, and recovery hint. Health also checks required pin connections, unresolved member references, missing interface implementations, duplicate names, and invalid CDO defaults. Diff results sort by stable node id, default to compact counts/ids, and accept `limit`, `cursor`, and `detailed` without embedding unbounded node payloads.
Add the `KismetCompiler` private module dependency needed by compiler results.
Do not depend on UE 5.8-only `BlueprintGraphEditor`; use the
`BlueprintGraph`/`Kismet`/`KismetCompiler` APIs available across 5.6-5.8 and
isolate any signature differences behind `ENGINE_MINOR_VERSION` guards.

- [ ] **Step 3: Add public wrappers**

Add `ue_get_blueprint_health` and `ue_diff_blueprint_graphs`. Mark health as a
write/medium operation because it compiles the Blueprint even though its name
starts with `get_`; diff is read/low. Enhance the existing
`ue_compile_blueprint` output without removing its old `success` and message fields.

- [ ] **Step 4: Add offline result-contract tests**

Feed representative success, warning, and compile-error dicts through the MCP response normalizer. Assert errors become `COMPILE_FAILED`, warnings become `needs_attention`, and node ids survive under `data.diagnostics`.

- [ ] **Step 5: Full-build and run tests**

Expected: valid Blueprint is `succeeded`; warning Blueprint is `needs_attention`; compiler error is not successful.

- [ ] **Step 6: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/blueprint_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_blueprint.py Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Blueprint2.cpp Plugins/UnrealMCPython/Source/UnrealMCPython/UnrealMCPython.Build.cs mcp-server/tests/test_blueprint_result_contract.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: add Blueprint health and graph diff"
~~~

---

### Task 14: Plan the universal gameplay foundation

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/gameplay_foundation.py`
- Create: `mcp-server/tests/test_gameplay_foundation_plan.py`
- Modify: `mcp-server/src/unreal_mcp/workflows/handler.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/game_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_game.py`
- Modify: `mcp-server/src/unreal_mcp/dispatchers/_catalog.py`
- Modify: `mcp-server/src/unreal_mcp/dispatchers/_registry.py`

- [ ] **Step 1: Write exact recipe tests**

~~~python
import pytest

from unreal_mcp.workflows.gameplay_foundation import GameplayFoundationSpec, build_foundation_operations


def test_default_recipe_contains_expected_assets_and_order():
    spec = GameplayFoundationSpec()
    operations = build_foundation_operations(spec)
    created_paths = set()
    for op in operations:
        if op.action in {"create_blueprint", "add_input_action"}:
            created_paths.add(op.params["asset_path"])
        elif op.action == "create_widget_blueprint":
            created_paths.add(f"{op.params['path'].rstrip('/')}/{op.params['name']}")
        elif op.action == "add_input_mapping":
            created_paths.add(op.params["mapping_context_path"])
    assert created_paths == {
        "/Game/Blueprints/Core/BP_GameMode",
        "/Game/Blueprints/Core/BP_GameState",
        "/Game/Blueprints/Core/BP_PlayerController",
        "/Game/Blueprints/Core/BP_PlayerCharacter",
        "/Game/UI/WBP_HUD",
        "/Game/Input/IA_Move",
        "/Game/Input/IA_Look",
        "/Game/Input/IA_Jump",
        "/Game/Input/IMC_Default",
    }
    assert any(op.action == "get_blueprint_health" for op in operations)


def test_project_default_step_is_absent_unless_requested():
    assert all(
        op.action != "set_project_default_game_mode"
        for op in build_foundation_operations(GameplayFoundationSpec())
    )
    requested = GameplayFoundationSpec(set_project_default_game_mode=True)
    assert any(
        op.action == "set_project_default_game_mode"
        for op in build_foundation_operations(requested)
    )


def test_world_override_uses_existing_set_game_mode_action():
    requested = GameplayFoundationSpec(set_world_override=True)
    assert any(op.action == "set_game_mode" for op in build_foundation_operations(requested))


@pytest.mark.parametrize("policy", ["fail", "reuse", "update", "rename"])
def test_all_conflict_policies_are_signed_recipe_inputs(policy):
    spec = GameplayFoundationSpec(conflict_policy=policy)
    assert spec.model_dump(mode="json")["conflict_policy"] == policy
~~~

In `test_game.py`, add failing focused tests for the exact gameplay primitives
used by this recipe: typed Blueprint class defaults; input mapping
modifiers/triggers; stable mapping inspection/removal; project/world GameMode
inspection; and project-default set/restore in `finally`. Include a compatibility
test that calls `ue_add_input_mapping` with only its original three arguments.

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp-server; uv run --extra dev pytest tests/test_gameplay_foundation_plan.py -q`

Expected: FAIL because recipe module is missing.
Also run the new focused `TestGameActions` methods in-editor; expected FAIL on
the missing class-default/project-setting/mapping APIs. If no editor is
available, record that gate as pending and do not complete Task 14 until the
red/green in-editor run has been performed.

- [ ] **Step 3: Define the recipe input contract**

~~~python
class GameplayFoundationSpec(BaseModel):
    core_path: str = "/Game/Blueprints/Core"
    ui_path: str = "/Game/UI"
    input_path: str = "/Game/Input"
    game_mode_name: str = "BP_GameMode"
    game_state_name: str = "BP_GameState"
    player_controller_name: str = "BP_PlayerController"
    player_character_name: str = "BP_PlayerCharacter"
    hud_name: str = "WBP_HUD"
    include_camera: bool = True
    include_gamepad: bool = False
    set_project_default_game_mode: bool = False
    set_world_override: bool = False
    run_pie_smoke_test: bool = False
    conflict_policy: Literal["fail", "reuse", "update", "rename"] = "fail"
~~~

Validate every path begins with `/Game/`, names contain no package separators, and `update` remains a signed confirmation input.

- [ ] **Step 4: Add missing game primitives, then expand to deterministic operations**

Before constructing recipe operations, implement and register:

- `ue_set_blueprint_class_default` for typed class-reference CDO properties;
- additive `modifiers=None, triggers=None` parameters on the existing
  `ue_add_input_mapping`;
- `ue_get_input_mapping_context` and stable mapping ids;
- `ue_remove_input_mapping(mapping_context_path=None, mapping_id=None)`;
- `ue_get_game_mode_settings`;
- `ue_set_project_default_game_mode(game_mode_class_path=None)` as a separate
  high-risk, snapshot-undoable action from the existing world override.

Regenerate the catalog/registry before invoking the generic planner so every
operation validates against the real new signatures. The project setter never
restarts the editor or enables a plugin.

Generate operations for:

1. Blueprint/widget and input asset existence checks.
2. Asset creation with parent classes.
3. Spring arm and camera component creation.
4. Move/look/jump input actions and keyboard/mouse mappings.
5. Character movement/look/jump graph nodes and connections.
6. Mapping-context installation in the local player flow.
7. HUD widget creation/add-to-viewport graph.
8. GameMode default class assignments.
9. Optional project/world defaults as separate high-risk steps.
10. Compile and health actions, a plan-level foundation verifier, and optional PIE smoke.

Use existing action signatures exactly: Blueprint and Input Action creation use
`asset_path`; `umg.create_widget_blueprint` uses `name`, `path`, and
`parent_class`; `game.add_input_mapping` uses `mapping_context_path`,
`action_path`, `key_name`, and the optional `modifiers`/`triggers` added in
Task 15. The repeated mapping operations are also the
creation path for `IMC_Default` when it does not yet exist. Use
`/Script/Engine.GameModeBase`, `/Script/Engine.GameStateBase`,
`/Script/Engine.PlayerController`, and `/Script/Engine.Character` as the four
Blueprint parent classes.

The default signed mapping list is deterministic:

- `IA_Move`: `W` with axis swizzle `YXZ`; `S` with swizzle `YXZ` plus negate;
  `A` with negate; `D` unchanged.
- `IA_Look`: `Mouse2D` unchanged.
- `IA_Jump`: `SpaceBar` unchanged.
- When `include_gamepad=true`, add `Gamepad_Left2D` to move,
  `Gamepad_Right2D` to look, and `Gamepad_FaceButton_Bottom` to jump.

Modifier specs use reflected class paths and property dictionaries, and the
planner rejects any modifier/trigger class not supported by the connected UE
version during preflight.

Every create step has a delete rollback only when the preflight proved the asset did not already exist. Every update step records the precise inverse from inspection.

Preflight resolves conflict policy deterministically:

- `fail` returns `CONFLICT` for any non-equivalent existing target.
- `reuse` skips only structurally equivalent targets and conflicts otherwise.
- `update` emits the narrow mutation plus an inverse captured from inspection.
- `rename` selects the first free `<RequestedName>_MCP<N>` path in ascending
  numeric order and records the resolved path in the signed plan.

Project default and current-world GameMode mutations are separate high-risk
steps: the new `game.set_project_default_game_mode` action changes project
settings, while existing `game.set_game_mode` with `game_mode_class_path` changes
only the current world override. Each captures a distinct inverse.
Both receive the generated class object path, for example
`/Game/Blueprints/Core/BP_GameMode.BP_GameMode_C`, not the Blueprint asset path.

- [ ] **Step 5: Wire `plan_gameplay_foundation`**

The handler builds recipe operations and passes them through the same generic
planner. Attach static foundation verification as a plan-level postcondition;
do not insert a nested `workflow.verify_gameplay_foundation` invocation into the
generic action list. Return predicted creates/reuses/updates/conflicts, affected
assets, risk summary, confirmation token, and the normalized recipe spec.

- [ ] **Step 6: Run tests and commit**

Run:

~~~powershell
cd mcp-server
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_gameplay_foundation_plan.py tests/test_workflow_planner.py tests/test_workflow_handler.py tests/test_coverage.py -q
~~~

Then run `TestGameActions` in-editor and confirm the restored project-default
value matches its pre-test snapshot.

Expected: PASS.

~~~powershell
git add mcp-server/src/unreal_mcp/workflows/gameplay_foundation.py mcp-server/src/unreal_mcp/workflows/handler.py mcp-server/tests/test_gameplay_foundation_plan.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/game_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_game.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: plan universal gameplay foundations"
~~~

---

### Task 15: Apply, verify, repair, and undo the gameplay foundation

**Files:**
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/game_actions.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_game.py`
- Create: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_gameplay_foundation.py`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/run_all.py`
- Modify: `mcp-server/src/unreal_mcp/workflows/gameplay_foundation.py`
- Create: `mcp-server/tests/test_gameplay_foundation_verify.py`
- Modify: `mcp-server/tests/test_e2e.py`

- [ ] **Step 1: Write gameplay-application integration tests**

Build on the focused game primitives completed in Task 14. Tests create
temporary assets under `/Game/__MCPTests/GameFoundation` and exercise those
actions through a signed workflow, asserting value types, keys, modifiers,
triggers, class references, project/world GameMode separation, recorded inverse
operations, and post-apply fingerprints. The project-setting case captures the
original value and restores it in `finally` even if an assertion fails.

- [ ] **Step 2: Write the in-editor foundation test**

The test calls workflow planning/application through the full TCP/MCP chain when available, or the exact internal action sequence in headless gate 3. It asserts all nine default assets exist, all four Blueprints and the widget compile, required components/nodes are present, and the verifier reports no drift.

Run the recipe twice. The second run must contain only `reuse`/`skip` changes. Mutate one class default and assert verification reports a conflict instead of overwriting it.

- [ ] **Step 3: Implement static verification**

`verify_gameplay_foundation` checks:

- asset paths and parent classes;
- Blueprint compile status and health;
- character camera/component hierarchy;
- IA value types and IMC mappings;
- reachable mapping-context installation;
- movement/look/jump data and execution wiring;
- reachable HUD create/add-to-viewport flow;
- GameMode default pawn/controller/game-state classes;
- optional project/world default settings.

Return deterministic drift records:

~~~json
{
  "asset_path": "/Game/Blueprints/Core/BP_GameMode",
  "code": "CLASS_DEFAULT_MISMATCH",
  "path": "DefaultPawnClass",
  "expected": "/Game/Blueprints/Core/BP_PlayerCharacter.BP_PlayerCharacter_C",
  "actual": null,
  "repairable": true
}
~~~

- [ ] **Step 4: Implement optional PIE smoke**

Use existing `util.start_pie`/`util.stop_pie` plus a new read-only
`game.get_pie_gameplay_state(mapping_context_path=None,
widget_class_path=None)` action that reports possessed pawn class, installed
mapping contexts, and matching HUD widget instances. Poll with a bounded
deadline; always stop PIE in `finally`. Assertions cover possession, character
spawn, input setup, and HUD creation. Timeout returns `TIMEOUT` and does not
leave PIE running. Add the action to `test_game.py`, metadata, generated
registry, and the in-editor coverage map.

- [ ] **Step 5: Add full E2E and undo**

Add one E2E test that:

1. Plans into a unique `/Game/__MCPTests/Foundation_<uuid>` root.
2. Applies using the confirmation token.
3. Polls until terminal status.
4. Verifies the foundation.
5. Applies the undo token.
6. Confirms created assets no longer exist.
7. Runs a final TCP liveness canary.

Any retained path after cleanup fails the test and is printed explicitly.

- [ ] **Step 6: Run all gates**

Offline:

~~~powershell
cd mcp-server
uv run python validate_tools.py
uv run --extra dev pytest -q
~~~

In editor:

~~~python
import runpy
runpy.run_module("UnrealMCPython.tests.run_all", run_name="__main__")
~~~

Live E2E:

`cd mcp-server; uv run --extra dev pytest tests/test_e2e.py -q`

Expected: all four gates pass; editor remains alive.

- [ ] **Step 7: Commit**

~~~powershell
git add Plugins/UnrealMCPython/Content/Python/UnrealMCPython/game_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_game.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_gameplay_foundation.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/run_all.py mcp-server/src/unreal_mcp/workflows/gameplay_foundation.py mcp-server/tests/test_gameplay_foundation_verify.py mcp-server/tests/test_e2e.py mcp-server/src/unreal_mcp/dispatchers/_catalog.py mcp-server/src/unreal_mcp/dispatchers/_registry.py
git commit -m "feat: build and verify gameplay foundations"
~~~

---

### Task 16: Add version matrix, generated docs, recovery guidance, and release verification

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `.github/workflows/e2e-selfhosted.yml`
- Modify: `README.md`
- Modify: `mcp-server/README.md`
- Modify: `CLAUDE.md`
- Create: `Docs/action-registry-v2.md`
- Create: `Docs/gameplay-foundation-workflow.md`
- Modify: `mcp-server/generate_catalog.py`
- Create: `mcp-server/tests/test_documentation_examples.py`

- [ ] **Step 1: Make docs generation testable**

Extend the generator with `--docs` to render `Docs/action-registry-v2.md` from `ACTION_SPECS`. Add a test that extracts every JSON example from both new docs and validates the action/params against the registry.

Run: `cd mcp-server; uv run --extra dev pytest tests/test_documentation_examples.py -q`

Expected before implementation: FAIL because `--docs` and docs are missing.

- [ ] **Step 2: Document strict and compatible modes**

Add exact MCP configuration examples with:

~~~json
{
  "mcpServers": {
    "unreal-mcpython": {
      "command": "uv",
      "args": ["--directory", "C:/absolute/path/to/unreal-mcp/mcp-server", "run", "src/unreal_mcp/main.py"],
      "env": {
        "UNREAL_MCP_SAFETY_MODE": "strict"
      }
    }
  }
}
~~~

Document the migration rule: omit the env key for legacy-compatible behavior.

- [ ] **Step 3: Document the canonical workflow**

`Docs/gameplay-foundation-workflow.md` must include:

- `util/search_actions` and `util/describe_action` examples;
- `workflow/plan_gameplay_foundation`;
- review of predicted changes and conflicts;
- `workflow/apply` with confirmation token;
- `workflow/get` polling;
- `workflow/cancel` and `workflow/undo`;
- `workflow/verify_gameplay_foundation`;
- recovery examples for stale tokens, compile failures, plugin requirements, timeouts, and partial rollback.

- [ ] **Step 4: Convert self-hosted E2E to a UE matrix**

Use matrix entries `5.6`, `5.7`, and `5.8` and repo variables `UE_ROOT_5_6`, `UE_ROOT_5_7`, `UE_ROOT_5_8`. Keep each job isolated and retain the four existing gates. Validate the selected root before launching the editor.

- [ ] **Step 5: Run final verification**

Run:

~~~powershell
cd mcp-server
uv lock --check
uv run python generate_catalog.py --check
uv run python generate_catalog.py --docs --check
uv run --extra dev pytest -q
~~~

Then run the full in-editor suite and E2E on each available local UE version. Record unavailable matrix versions in the handoff; do not claim them passing.

Expected: every available gate passes, docs are current, and `git status --short` is empty except intended documentation/workflow changes before commit.

- [ ] **Step 6: Commit**

~~~powershell
git add .github/workflows/test.yml .github/workflows/e2e-selfhosted.yml README.md mcp-server/README.md CLAUDE.md Docs/action-registry-v2.md Docs/gameplay-foundation-workflow.md mcp-server/generate_catalog.py mcp-server/tests/test_documentation_examples.py
git commit -m "docs: publish safe Blueprint gameplay workflows"
~~~

---

## Final acceptance checklist

- [ ] Existing namespace/action calls pass golden tests in `compatible` mode.
- [ ] Direct writes return `CONFIRMATION_REQUIRED` in `strict` mode.
- [ ] Every action has generated input schema, risk, effect, result kind, version, and plugin metadata.
- [ ] Discovery works through tools and `unreal://catalog`.
- [ ] Confirmation tokens expire after ten minutes and reject replay or stale editor state.
- [ ] Cancellation occurs only between atomic steps.
- [ ] Rollback reports complete versus partial results accurately.
- [ ] Blueprint inspection uses stable ids, filters, compact results, and pagination.
- [ ] Blueprint member, reflected-node, pin, variable, and component actions pass in-editor tests.
- [ ] Compile warnings produce `needs_attention`; errors are not successful.
- [ ] The default gameplay recipe is idempotent and never overwrites conflicting assets silently.
- [ ] Static verification and optional PIE smoke test pass.
- [ ] Undo removes newly created foundation assets and restores changed settings when fingerprints still match.
- [ ] Offline gates pass.
- [ ] In-editor and E2E gates pass on every actually available UE 5.6/5.7/5.8 worker.
- [ ] Generated docs and examples match the registry.
