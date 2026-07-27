# Unreal MCP Blueprint-First Gameplay Foundation Design

**Date:** 2026-07-27  
**Status:** Approved design  
**Base project:** `GenOrca/unreal-mcp`  
**Target Unreal Engine versions:** 5.6, 5.7, and 5.8

## Summary

Extend GenOrca Unreal MCP without replacing its existing 21 namespace tools or breaking the `(action, params)` calling convention. The first release will make the server easier and safer for an LLM to operate, deepen Blueprint authoring, and add one high-level workflow that creates a universal playable game foundation.

The implementation will remain Python-first. Small C++ helpers will be added only where Unreal's Python API does not expose the required Blueprint graph operation. The design uses Flopperam's documented Blueprint workflow as a behavioral reference, but does not copy Flopperam code. GenOrca remains the implementation base because it has an explicit Apache-2.0 license, modular action files, a generated catalog, broad Unreal coverage, automated tests, and demonstrated UE 5.6-5.8 maintenance.

## Goals

- Preserve all existing namespace tools, action names, and direct-call behavior in compatibility mode.
- Give an LLM machine-readable action schemas, risk metadata, examples, discovery, and actionable errors.
- Add a safe `plan -> confirm -> apply -> verify -> undo` workflow for mutations.
- Add missing Blueprint inspection and authoring operations needed to build real gameplay classes.
- Add a high-level, idempotent workflow that creates a GameMode, GameState, PlayerController, PlayerCharacter, HUD widget, and Enhanced Input assets.
- Verify all new actions offline and in-editor across UE 5.6, 5.7, and 5.8.
- Establish extension points for later Inventory, Quest, Save/Load, GAS, AI, and other gameplay workflows.

## Non-goals for the first release

- Inventory, quests, saving, GAS, AI, networking architecture, or genre-specific combat.
- Niagara, landscape, foliage, PCG, MetaSound, or unrelated new Unreal domains.
- Replacing the current dispatcher with one MCP tool per action.
- A monolithic C++ Blueprint composer.
- Copying code from Flopperam's repository or depending on its hosted service.
- Automatic plugin enablement or invasive project restarts.
- Guaranteeing that every legacy direct mutation can be rolled back. Safe guarantees apply to the new workflow surface; legacy behavior remains available in compatibility mode.

## Constraints and compatibility

The existing MCP surface remains valid:

```text
domain(action: str, params: dict = {})
```

Existing actions continue to return their current top-level fields. New metadata may be added under a reserved `_meta` object, but existing fields will not be moved or renamed. New actions use the structured result contract defined below.

The server has two safety modes:

- `compatible`: legacy direct actions execute with their current behavior. New workflow actions are always safe.
- `strict`: write and destructive actions must be executed through an approved workflow plan.

Existing installations default to `compatible` during the migration period. New installation examples and documentation recommend `strict`. The mode is selected at server startup and is returned by the health/capabilities response.

## Chosen approach

Use a hybrid, incremental extension of GenOrca:

- Python owns discovery, schemas, planning, validation, session state, orchestration, response normalization, and verification.
- Unreal Python action modules own small editor operations that map cleanly to supported Unreal APIs.
- `UMCPythonHelper` receives narrow C++ functions only for graph operations that Unreal Python cannot perform reliably.
- The existing generated catalog remains the source for legacy clients and is derived from a richer registry rather than maintained separately.

Rejected alternatives:

- A parallel v3 tool surface would create duplicate concepts and make tool selection harder for an LLM.
- A C++-first declarative composer would be harder to extend, require more editor rebuilds, and multiply UE-version compatibility risk.
- Flopperam's open-source repository has useful Blueprint primitives, but its advanced 50+ tool server is hosted and explicitly separate from the published local code. The local repository also lacks tests and a detectable license file despite an MIT statement in its README.

## Architecture

```text
LLM / MCP client
    -> namespace dispatcher
    -> Action Registry v2
    -> input validation and safety policy
    -> workflow planner and session store
    -> TCP transport
    -> Unreal Python actions / narrow C++ helpers
    -> compiler and workflow verifier
    -> normalized structured result
```

### Action Registry v2

`generate_catalog.py` will produce a richer generated registry from function signatures, type annotations, docstrings, and explicit per-action metadata. It will also render the current legacy `CATALOG` shape so existing code remains compatible.

Each `ActionSpec` contains:

```json
{
  "domain": "blueprint",
  "action": "create_function",
  "title": "Create Blueprint function",
  "description": "Create a function graph with a typed signature.",
  "input_schema": {},
  "output_schema": {},
  "effect": "write",
  "risk": "medium",
  "idempotent": false,
  "supports_preview": true,
  "supports_undo": true,
  "requires_confirmation": true,
  "ue_versions": ["5.6", "5.7", "5.8"],
  "required_plugins": [],
  "examples": [],
  "error_examples": []
}
```

Allowed effects are `read`, `write`, and `destructive`. Allowed risks are `low`, `medium`, and `high`. Registry generation fails when a new action lacks required metadata or has a schema that cannot be generated.

### Discovery surface

Existing `{ "action": "list_actions" }` responses gain additive schema and risk metadata. The `util` namespace gains:

- `search_actions`: search names, descriptions, effects, required plugins, and examples across domains.
- `describe_action`: return one complete `ActionSpec`.
- `get_capabilities`: report server/plugin versions, Unreal version, safety mode, loaded optional plugins, supported workflow features, and transport health.

The same catalog is exposed as an MCP resource for clients that support resources. Tool-based discovery remains authoritative so functionality does not depend on optional client support.

### Dispatcher pipeline

All new actions pass through one pipeline:

1. Resolve the action from the registry.
2. Validate input against the generated JSON Schema.
3. Check Unreal version, required plugin capabilities, safety mode, and risk policy.
4. Dispatch a read immediately or hand a mutation to the workflow layer.
5. Normalize the result without removing legacy fields.
6. Run declared postconditions and return verification details.

The dispatcher remains thin. Domain behavior stays in focused modules rather than accumulating in `dispatcher.py`.

### Workflow namespace

Add one namespace tool named `workflow`, following the same `(action, params)` convention. Its initial actions are:

- `plan`: validate a declarative request and produce an immutable plan.
- `apply`: execute a confirmed plan.
- `get`: return plan status and step results.
- `cancel`: request cancellation at the next safe step boundary.
- `undo`: revert a completed workflow when the recorded transaction is still valid.
- `plan_gameplay_foundation`: create the canonical gameplay-foundation plan from a compact spec.
- `verify_gameplay_foundation`: inspect an existing foundation and report drift or missing pieces.

Long-running workflows report MCP progress notifications where supported. Status polling remains available through `workflow/get` for all clients.

## Structured result contract

New actions and all workflow actions return:

```json
{
  "success": true,
  "status": "succeeded",
  "summary": "Created and verified the gameplay foundation.",
  "data": {},
  "changes": [],
  "warnings": [],
  "errors": [],
  "next_actions": [],
  "trace_id": "..."
}
```

Workflow statuses are:

- `planned`
- `awaiting_confirmation`
- `running`
- `cancelled`
- `succeeded`
- `needs_attention`
- `failed_rolled_back`
- `failed_partial`

Compiler warnings yield `needs_attention`, not unconditional success. The changes remain available for inspection and carry an undo token when rollback is still possible.

Large inspections use `limit`, `cursor`, field filters, and compact mode. Responses declare truncation and provide the next cursor. Raw Python tracebacks are omitted unless debug mode is enabled; normal results include a `trace_id` that maps to server logs.

## Error model

Errors use stable codes:

- `INVALID_INPUT`
- `UNKNOWN_ACTION`
- `CONFLICT`
- `PRECONDITION_FAILED`
- `CONFIRMATION_REQUIRED`
- `CONFIRMATION_EXPIRED`
- `PLUGIN_REQUIRED`
- `UE_VERSION_UNSUPPORTED`
- `UE_UNAVAILABLE`
- `TIMEOUT`
- `COMPILE_FAILED`
- `VERIFICATION_FAILED`
- `TRANSACTION_FAILED`
- `ROLLBACK_FAILED`
- `INTERNAL_ERROR`

Each error contains `code`, `message`, `path` when a parameter or asset is involved, `retryable`, `hint`, sanitized `details`, and `trace_id`. Hints must describe a concrete next action, such as enabling a named optional plugin, correcting an asset path, refreshing a stale plan, or inspecting compiler diagnostics.

## Safety and transaction model

### Planning

`workflow/plan` and `workflow/plan_gameplay_foundation` perform read-only inspection and return:

- ordered operations and dependencies;
- affected assets and project settings;
- predicted creates, updates, skips, and deletes;
- preconditions and postconditions;
- risk summary and warnings;
- estimated step count;
- a single-use `confirmation_token`.

The token is a digest of the normalized plan, project identity, editor session identity, current map, relevant asset fingerprints, and server safety mode. It expires after ten minutes. Applying a stale, reused, mismatched, or modified token fails without performing writes.

### Applying

Before the first write, `workflow/apply` rechecks all fingerprints and preconditions. It then opens a scoped Unreal editor transaction and executes topologically sorted steps. Asset operations that are not fully covered by the editor transaction record a pre-state snapshot sufficient for workflow-level restoration.

Cancellation is cooperative. It is checked before and after each atomic step, never while an asset is half-mutated.

After execution, declared postconditions run before the workflow is considered complete. A failure triggers rollback in reverse dependency order. Results distinguish a complete rollback from a partial rollback and list every residual change.

### Undo

A successful workflow returns a single-use `undo_token` bound to its transaction and asset post-state. Undo is rejected if the affected assets have changed since the workflow completed. When Unreal's transaction history has diverged, workflow snapshots are used only for operations explicitly marked snapshot-safe; otherwise the response explains which changes require manual recovery.

## Blueprint 2.0 scope

Current Blueprint actions stay available. The first release adds the following capability groups.

### Compact inspection

- Blueprint brief: parent class, interfaces, components, variables, graphs, compile state, and counts.
- Filtered inspection of functions, macros, custom events, dispatchers, nodes, pins, connections, variable defaults, and component hierarchy.
- Stable object identifiers suitable for later mutation calls.
- Graph health and compile diagnostics.
- Before/after graph diff with compact summaries and optional detailed pages.

### Graph and member authoring

- Create, rename, edit, and delete functions.
- Add, edit, reorder, and remove typed function inputs and outputs.
- Create and delete macro graphs.
- Create and remove custom events and event dispatchers.
- Add and remove Blueprint interfaces and implement required event/function graphs.
- Create nodes from reflected Unreal functions, properties, classes, enums, and structs instead of relying only on a fixed node list.
- Create common control-flow, cast, variable, operator, make/break, select/switch, reroute, comment, and event nodes.
- Connect and disconnect pins with type diagnostics and an explicit report when Unreal inserts an automatic conversion.
- Set node properties and positions, delete nodes, and auto-layout a selected graph or the whole Blueprint.

### Variables and components

- Set variable defaults for primitive, struct, enum, object/class reference, soft reference, array, set, and map types supported by the target UE version.
- Set category, tooltip, visibility, instance-editability, `ExposeOnSpawn`, `SaveGame`, cinematic exposure, and replication settings.
- Add, remove, rename, reparent, and reorder Blueprint components.
- Set component transforms and class defaults through typed property conversion.

### Compile and health

Compilation returns compiler status, warnings, errors, affected graphs, and stable references to failing nodes. A health report checks disconnected required pins, unresolved members, missing interface implementations, duplicate member names, stale node references, and invalid class defaults.

## Gameplay foundation workflow

`workflow/plan_gameplay_foundation` accepts a compact specification with configurable root paths and names. Default paths are:

```text
/Game/Blueprints/Core/BP_GameMode
/Game/Blueprints/Core/BP_GameState
/Game/Blueprints/Core/BP_PlayerController
/Game/Blueprints/Core/BP_PlayerCharacter
/Game/UI/WBP_HUD
/Game/Input/IA_Move
/Game/Input/IA_Look
/Game/Input/IA_Jump
/Game/Input/IMC_Default
```

The default workflow:

1. Creates the five Blueprint/widget assets with the correct parent classes.
2. Adds a spring arm and camera to the player character when requested by the spec.
3. Creates Axis2D move/look actions, a boolean jump action, and the default mapping context.
4. Adds keyboard/mouse mappings; gamepad mappings are optional in the first release.
5. Authors movement, look, and jump Blueprint logic.
6. Adds the mapping context for the local player.
7. Creates the HUD widget from the player controller and adds it to the viewport.
8. Assigns the pawn, controller, and game-state classes in the GameMode defaults.
9. Optionally proposes project default GameMode and current-world override changes as separate high-risk plan steps.
10. Compiles and statically verifies every generated asset.
11. Optionally runs a PIE smoke test that verifies possession, input setup, character spawn, and HUD creation.

The workflow is idempotent. A repeated run skips structurally equivalent assets. If an existing asset differs, the plan reports a conflict rather than overwriting it. The caller can explicitly choose `fail`, `reuse`, `update`, or `rename` conflict policy; `fail` is the default for non-equivalent assets.

## Verification

The foundation verifier checks:

- expected assets exist at the resolved paths;
- parent classes and GameMode class defaults are correct;
- all Blueprints compile without errors;
- required components and graph nodes exist;
- input action value types and mappings match the requested spec;
- mapping context installation is reachable from the local player flow;
- movement, look, and jump graphs have valid execution and data connections;
- HUD creation and viewport insertion are reachable;
- optional project/world settings point at the generated GameMode;
- optional PIE smoke assertions pass.

Verification reports drift without mutating assets. Repair is a new plan and therefore requires a new confirmation token.

## Testing strategy

### Offline gates

- Registry generation and stale-catalog checks.
- JSON Schema generation and validation tests.
- Metadata completeness tests for every action.
- Golden snapshots for all existing domain tool schemas and representative legacy responses.
- Dispatcher, safety-mode, confirmation-token, expiration, replay, and stale-fingerprint tests.
- Workflow dependency sorting, cancellation, rollback, partial-failure, and pagination tests against a fake Unreal executor.
- Structured error and response contract tests.
- Documentation examples executed against schema validation.

### In-editor gates

- One focused test for every new Blueprint operation.
- Tests for each supported variable type, member type, node family, and component mutation.
- Compile and health-report tests with both valid and intentionally broken Blueprints.
- Transaction and workflow undo tests.
- Conflict and idempotency tests using pre-existing assets.
- A complete foundation E2E test in a unique temporary `/Game/__MCPTests/...` path.
- Optional PIE smoke test for possession, input setup, spawn, and HUD creation.
- Final editor-liveness canary so an editor crash cannot produce a green run.

### Version matrix

Offline tests run on normal CI. In-editor tests run on self-hosted Unreal workers for UE 5.6, 5.7, and 5.8. Optional-plugin actions skip only when their documented dependency is unavailable. The gameplay foundation requires Enhanced Input and UMG; absence produces `PLUGIN_REQUIRED` during planning rather than failing mid-apply.

Test-created assets are placed only under unique test directories and are removed through a verified cleanup workflow after the test. A failed cleanup is reported as a test failure with the retained paths.

## Documentation and LLM guidance

- Update the root README with strict-mode configuration and the gameplay-foundation example.
- Generate a complete action reference from `ActionSpec` rather than hand-maintaining parameter lists.
- Add short workflow guidance: inspect before editing, plan before applying, compile once per authoring batch, and verify after applying.
- Add recovery examples for validation, stale plan, compile, conflict, plugin, timeout, and partial rollback errors.
- Expose the same guidance through MCP prompts/resources when supported, while keeping tool descriptions sufficient for clients that ignore them.

## Delivery boundaries

This design is one vertical slice with four dependent implementation stages:

1. Registry, discovery, structured errors, and compatibility tests.
2. Workflow planning, confirmation, transactions, progress, cancellation, and undo.
3. Blueprint 2.0 inspection and authoring primitives.
4. Gameplay-foundation planning, application, verification, documentation, and the UE version matrix.

Each stage must pass its offline and applicable in-editor gates before the next stage is considered complete. The detailed implementation plan will split these stages into small test-driven tasks.

## References

- GenOrca Unreal MCP: https://github.com/GenOrca/unreal-mcp
- Flopperam Unreal Engine MCP behavioral reference: https://github.com/flopperam/unreal-engine-mcp
- Model Context Protocol specification, 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25
- Unreal Engine Python API: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/

