# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server that lets an LLM drive the Unreal Editor. Two halves:

- **`mcp-server/`** — Python FastMCP server (the MCP side, talks to the LLM over stdio).
- **`Plugins/UnrealMCPython/`** — a UE plugin: a C++ TCP server (port `12029`) plus
  Python "action" modules that actually call the Unreal API.

Request path: `LLM → FastMCP dispatcher → TCP :12029 → C++ server → ue_* Python function → back`.

## Architecture (the non-obvious parts)

**Namespace dispatcher, not one-tool-per-action.** The MCP surface is **10 domain tools**
(`actor`, `asset`, `behavior_tree`, `blueprint`, `editor`, `game`, `level`, `material`,
`umg`, `util`), each taking `(action, params)`. This keeps the tool-list context cost fixed
no matter how many actions exist. `action="list_actions"` returns a domain's catalog.
See `mcp-server/src/unreal_mcp/dispatcher.py`.

**The catalog is generated, never hand-written.** `dispatchers/_catalog.py` is produced by
`generate_catalog.py`, which AST-extracts param names, defaults, and the docstring first line
from every `ue_*` function in `Plugins/.../UnrealMCPython/*_actions.py`. The dispatcher passes
`params` straight through as `ue_<action>(**params)`, so catalog param names **must** equal the
real signatures — generation guarantees this. Never edit `_catalog.py` by hand.

**Responses are double-wrapped.** The C++ server runs `print(execute_action(...))` and puts the
captured stdout (the action's JSON string) into a `result` field, with an outer `success` that
means "Python ran", not "action succeeded". `core._unwrap_result()` unwraps it so callers get the
real action dict. `execute_python` / `livecoding_compile` use separate TCP message types and are
intentionally not unwrapped.

## Commands

```bash
# All run from mcp-server/
cd mcp-server

# Regenerate the catalog after adding/changing a ue_* function
uv run python generate_catalog.py

# Gate 1 — catalog vs signatures drift guard
uv run python validate_tools.py

# Gate 2 — offline tests (routing, unwrap, coverage). E2E auto-skips with no editor.
uv run --extra dev pytest

# Single test / by name
uv run --extra dev pytest tests/test_dispatcher.py -k routing
```

In-editor tests (need the editor open) run from the Unreal Python console or via
`util execute_python`:

```python
import runpy; runpy.run_module("UnrealMCPython.tests.run_all", run_name="__main__")
```

## Four test gates (each catches a different failure)

| Gate | Command | Verifies | Editor |
|------|---------|----------|--------|
| 1 Drift | `validate_tools.py` | catalog param names == `ue_*` signatures | no |
| 2 Routing | `pytest tests/test_dispatcher.py` `test_core.py` | dispatcher routing + result unwrapping | no |
| 3 In-editor | `tests/run_all.py` in UE | `ue_*` actually work against Unreal | yes |
| 4 E2E | `pytest tests/test_e2e.py` | full chain incl. TCP + unwrap (skips if `:12029` closed) | yes |

`test_coverage.py` enforces that **every** catalog action has an in-editor test
(or is listed in `KNOWN_UNTESTED`, which should stay empty).

## Adding an action to an existing domain

1. Prototype fast with `util execute_python` (arbitrary Unreal Python, seconds-scale).
2. Add a `ue_<name>(...)` function to `Plugins/.../UnrealMCPython/<domain>_actions.py`.
   It must `return json.dumps({...})` and validate its own required params.
3. Add an in-editor test in `Plugins/.../UnrealMCPython/tests/test_<domain>.py`
   (the coverage gate fails without one).
4. `uv run python generate_catalog.py` — the action now appears in the dispatcher.
5. Run gates: `uv run python validate_tools.py` and `uv run --extra dev pytest`,
   then the in-editor suite (and E2E if the editor is up).
6. Commit.

```python
# Plugins/.../UnrealMCPython/<domain>_actions.py
def ue_my_action(asset_path: str = None, value: float = 1.0) -> str:
    """One-line summary becomes the catalog doc."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        # ... call the Unreal API ...
        return json.dumps({"success": True, "result_field": ...})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
```

```python
# Plugins/.../UnrealMCPython/tests/test_<domain>.py
def test_my_action(self):
    r = self.call("<domain>_actions", "ue_my_action", asset_path=self._asset, value=2.0)
    self.assertSuccess(r)
```

## Adding a new domain

1. Create `Plugins/.../UnrealMCPython/<domain>_actions.py` with `ue_*` functions.
2. Create `Plugins/.../UnrealMCPython/tests/test_<domain>.py` and add the module to
   `tests/run_all.py`.
3. Add `"<domain>"` to `DOMAINS` in `generate_catalog.py` (the module is derived as
   `UnrealMCPython.<domain>_actions`). The dispatcher auto-registers every catalog
   domain except `util` — no `dispatcher.py` edit needed.
4. `uv run python generate_catalog.py`, then run the gates.

Special routing (separate TCP message types, e.g. `execute_python`) lives in the hand-written
`util` handler in `dispatcher.py` — follow that pattern only if an action is not a plain
`ue_*` call.

## Adding C++ helpers (UFUNCTIONs in MCPythonHelper)

Some APIs aren't exposed to Python (e.g. reference-skeleton bones, read-only
`SkeletalMeshSocket.socket_name`, Blueprint/AnimBP graph internals). Add a
`UFUNCTION(BlueprintCallable, Category="Editor|MCPython")` to
`Source/UnrealMCPython/Public/MCPythonHelper.h` + impl in the `.cpp` (return a JSON
string via `SerializeJsonObj`), then call it from a Python `ue_*` wrapper.

**Build cycle — this matters:**
- Editing an existing function *body* → `util livecoding_compile` hot-patches the
  running editor. Fast.
- **Adding a new UFUNCTION** (new reflection) → Live Coding compiles but does NOT
  register it. You must do a full UBT build with the editor **closed**:
  1. Close the editor completely (verify no `UnrealEditor.exe` remains).
  2. `"<UE>/Engine/Build/BatchFiles/Build.bat" UnrealEditor Win64 Development -project="<repo>/UnrealMCPSample.uproject" -waitmutex`
     (this is a plugin-only project — there is no project-level target).
  3. Reopen the editor; the new UFUNCTION is now callable from Python.

## Conventions

- `ue_*` functions take keyword args matching catalog param names and return a JSON string.
- Required params are validated inside the function (return `success: False`), not via signature
  defaults — defaults are usually `None` meaning "required".
- Destructive editor-session actions (e.g. `create_level`/`load_level` switch/replace the open
  level) are tested via guard paths only in-editor; the happy path can reset the TCP server.
