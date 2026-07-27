# Workflow Executor and Editor Lease Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Task 9 as a safe, cancellable workflow runtime that owns one Unreal editor transaction lease, survives MCP disconnects, rejects dirty pre-existing assets, reports FastMCP task progress, and issues undo tokens only for a verified Unreal undo entry.

**Architecture:** Keep the approved single Unreal transaction open across workflow steps, guarded by a modal `FScopedSlowTask` and an `FTSTicker` idle watchdog. Route every planned action through one internal Unreal Python atomic-step wrapper; on the server, a process-local `asyncio.Lock` serializes workflows while a testable backend, executor, and namespace handler separate TCP transport, state transitions, and public policy.

**Tech Stack:** Python 3.11+, FastMCP 3.2.4 (`fastmcp[tasks]`), Pydantic 2, pytest/pytest-asyncio, Unreal Engine 5.7 editor C++, Unreal Python, UBT.

---

## Scope boundary

This plan implements the generic workflow runtime and registers all seven initial workflow namespace branches. `plan_gameplay_foundation` and `verify_gameplay_foundation` are routed through injectable handler hooks and return a structured capability error until Tasks 14-15 install those hooks. Blueprint authoring and the gameplay-foundation recipe remain outside this plan.

The implementation preserves the existing namespace shape `(action, params)`, the Task 8 transaction GUID/queue/head checks, and the generated Action Registry v2. Internal Unreal helpers in `workflow_actions.py` remain absent from the public action catalog.

## File responsibility map

### Unreal plugin

- `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h` — reflected lease, heartbeat, atomic-step, and deterministic test-control entry points.
- `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp` — transaction lease state, slow-task dialog, ticker watchdog, guarded timeout recovery, and compact context serialization.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py` — internal TCP wrappers and the only atomic registry-action trampoline.
- `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_workflow.py` — in-editor lease/recovery coverage.
- `mcp-server/tests/test_workflow_actions_wrappers.py` — offline wrapper contract coverage.

### MCP server

- `mcp-server/src/unreal_mcp/core.py` — move blocking socket I/O into `asyncio.to_thread` so cancellation requests remain serviceable while Unreal executes one atomic action.
- `mcp-server/src/unreal_mcp/workflows/models.py` — runtime transaction, post-state, residual-state, and verifier contracts.
- `mcp-server/src/unreal_mcp/workflows/store.py` — lock-protected runtime updates.
- `mcp-server/src/unreal_mcp/workflows/tokens.py` — typed token failure reasons for stable confirmation/expiry mapping.
- `mcp-server/src/unreal_mcp/workflows/planner.py` — dirty pre-existing asset rejection during planning and apply preflight.
- `mcp-server/src/unreal_mcp/workflows/backend.py` — concrete Unreal TCP context/lease/step backend plus a protocol used by executor tests.
- `mcp-server/src/unreal_mcp/workflows/executor.py` — task ownership, serialization, heartbeat/progress, cooperative cancellation, rollback, residual checks, and undo.
- `mcp-server/src/unreal_mcp/workflows/handler.py` — schema-validating workflow namespace routing and signed-token policy.
- `mcp-server/src/unreal_mcp/special_action_specs.py` — seven complete server-local workflow action contracts.
- `mcp-server/src/unreal_mcp/dispatcher.py` — one task-enabled FastMCP `workflow` tool.
- `mcp-server/generate_catalog.py` — support a special-only `workflow` domain with no public plugin action module.
- `mcp-server/tests/test_core.py` — non-blocking event-loop transport test.
- `mcp-server/tests/test_workflow_planner.py` — dirty-package planning/apply tests.
- `mcp-server/tests/test_workflow_backend.py` — exact TCP call-shape tests.
- `mcp-server/tests/test_workflow_executor.py` — executor state-machine tests.
- `mcp-server/tests/test_workflow_handler.py` — all workflow namespace branches and FastMCP task/progress tests.
- `mcp-server/tests/test_dispatcher.py`, `mcp-server/tests/test_fastmcp_v3.py`, `mcp-server/tests/test_coverage.py` — namespace registration, catalog, and named coverage gates.
- `mcp-server/src/unreal_mcp/dispatchers/_catalog.py`, `mcp-server/src/unreal_mcp/dispatchers/_registry.py` — regenerated outputs.

---

### Task 1: Add the Unreal editor transaction lease and atomic-step wrapper

**Files:**
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h:355`
- Modify: `Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp:1`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py:1`
- Modify: `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_workflow.py:1`
- Modify: `mcp-server/tests/test_workflow_actions_wrappers.py:1`

- [ ] **Step 1: Write failing offline wrapper tests**

Extend the fake `MCPythonHelper` with calls named `heartbeat_workflow_transaction`, `begin_workflow_atomic_step`, `end_workflow_atomic_step`, and `request_workflow_cancellation`. Add these tests:

```python
def test_begin_forwards_lease_configuration(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(module.ue_begin_transaction(
        transaction_id="tx", description="Build", total_steps=3,
        show_dialog=False, idle_timeout_seconds=2.5,
    ))
    assert result["success"] is True
    assert calls == [("begin", "tx", "Build", 3, False, 2.5)]


def test_heartbeat_forwards_progress_and_write_state(monkeypatch):
    module, calls = _load(monkeypatch)
    result = json.loads(module.ue_heartbeat_transaction(
        transaction_id="tx", completed_steps=2, total_steps=3,
        message="Compiled", has_successful_write=True,
    ))
    assert result["success"] is True
    assert calls == [("heartbeat", "tx", 2, 3, "Compiled", True)]


def test_execute_step_always_leaves_atomic_phase(monkeypatch):
    module, calls = _load(monkeypatch, action_result={
        "success": False, "message": "compile failed"
    })
    result = json.loads(module.ue_execute_step(
        transaction_id="tx",
        action_module="UnrealMCPython.blueprint_actions",
        action_name="ue_compile_blueprint",
        params={"asset_path": "/Game/BP"},
    ))
    assert result["success"] is False
    assert calls == [
        ("atomic_begin", "tx"),
        ("action", "UnrealMCPython.blueprint_actions",
         "ue_compile_blueprint", {"asset_path": "/Game/BP"}),
        ("atomic_end", "tx"),
    ]


@pytest.mark.parametrize("module_name", [
    "UnrealMCPython.workflow_actions", "os", "UnrealMCPython../actor_actions"
])
def test_execute_step_rejects_internal_or_unsafe_modules(monkeypatch, module_name):
    module, calls = _load(monkeypatch)
    result = json.loads(module.ue_execute_step(
        transaction_id="tx", action_module=module_name,
        action_name="ue_anything", params={},
    ))
    assert result["success"] is False
    assert calls == []
```

- [ ] **Step 2: Run the offline tests and confirm the red state**

Run:

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_workflow_actions_wrappers.py -q
```

Expected: failures show the new wrapper parameters and helper methods are absent.

- [ ] **Step 3: Declare the exact reflected C++ lease API**

Replace the old two-parameter begin declaration and add these declarations:

```cpp
UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString BeginWorkflowTransaction(
    const FString& TransactionId,
    const FString& Description,
    int32 TotalSteps = 1,
    bool bShowDialog = true,
    float IdleTimeoutSeconds = 60.0f);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString HeartbeatWorkflowTransaction(
    const FString& TransactionId,
    int32 CompletedSteps,
    int32 TotalSteps,
    const FString& Message,
    bool bHasSuccessfulWrite);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString BeginWorkflowAtomicStep(const FString& TransactionId);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString EndWorkflowAtomicStep(const FString& TransactionId);

UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
static FString RequestWorkflowCancellation(const FString& TransactionId);
```

Keep the existing commit, cancel, rollback, and undo signatures unchanged.

- [ ] **Step 4: Implement lease state and one cleanup path in C++**

Add the UE 5.7 headers and state:

```cpp
#include "Containers/Ticker.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/DateTime.h"
#include "Misc/ScopedSlowTask.h"

enum class EWorkflowLeasePhase : uint8 { Idle, Atomic };

struct FWorkflowLease
{
    int32 TotalSteps = 1;
    int32 CompletedSteps = 0;
    double LastHeartbeatSeconds = 0.0;
    double IdleTimeoutSeconds = 60.0;
    EWorkflowLeasePhase Phase = EWorkflowLeasePhase::Idle;
    bool bHasSuccessfulWrite = false;
    bool bCancelRequested = false;
    TUniquePtr<FScopedSlowTask> SlowTask;
    FTSTicker::FDelegateHandle TickerHandle;
};

TUniquePtr<FWorkflowLease> GWorkflowLease;
TSharedPtr<FJsonObject> GLastWorkflowRecovery;
```

`BeginWorkflowTransaction` must validate `TotalSteps > 0` and `IdleTimeoutSeconds > 0`, create the existing `FScopedTransaction`, then create `FWorkflowLease`, set `LastHeartbeatSeconds = FPlatformTime::Seconds()`, and register:

```cpp
GWorkflowLease->TickerHandle = FTSTicker::GetCoreTicker().AddTicker(
    TEXT("UnrealMCP.WorkflowLease"), 1.0f,
    [](float) { return TickWorkflowLease(); });
```

When `bShowDialog && !FApp::IsUnattended()`, construct `FScopedSlowTask` with `TotalSteps`, call `MakeDialog(true)`, and never show the dialog for unattended execution. Use one `ClearWorkflowLease(bool bRemoveTicker)` helper from commit, cancel, rollback, timeout, and every begin failure after lease allocation. When called by the ticker itself, reset the weak handle and pass `false`; all other terminal paths call `FTSTicker::RemoveTicker` before destroying the slow task.

`HeartbeatWorkflowTransaction` must reject a wrong id, atomic phase, a changed total, decreasing progress, or progress above total. Before refreshing the lease, it compares the monotonic clock with the idle deadline and calls the same timeout recovery path as the ticker when already expired. Otherwise it calls `EnterProgressFrame(CompletedSteps - PreviousCompleted, FText::FromString(Message))` only for a positive delta, calls `TickProgress()`, ORs `bHasSuccessfulWrite`, refreshes `LastHeartbeatSeconds`, and returns:

```json
{
  "success": true,
  "transaction_id": "tx",
  "lease_phase": "idle",
  "completed_steps": 2,
  "total_steps": 3,
  "cancel_requested": false,
  "has_successful_write": true
}
```

`BeginWorkflowAtomicStep` accepts only idle; `EndWorkflowAtomicStep` accepts only atomic, restores idle in all valid calls, and refreshes the deadline. Both return the same compact lease fields.

- [ ] **Step 5: Implement deterministic timeout recovery**

Both the ticker and an already-expired heartbeat call one `RecoverExpiredWorkflowLease()` function. If phase is atomic, the ticker returns `true` without recovery. Otherwise:

```cpp
if (!GWorkflowLease->bHasSuccessfulWrite)
{
    GActiveWorkflowTransaction->Cancel();
    Outcome = TEXT("cancelled_no_write");
}
else
{
    GActiveWorkflowTransaction.Reset();
    const bool bRecorded = IsCurrentWorkflowTransaction(Index, Guid);
    const bool bUndone = bRecorded && GEditor->UndoTransaction();
    Outcome = bUndone
        ? TEXT("rolled_back")
        : TEXT("manual_recovery_required");
}
```

Record `transaction_id`, `outcome`, `success`, `transaction_index`, `message`, and `recovered_at` in `GLastWorkflowRecovery`; clear the active transaction identifiers and release UI/ticker state in every branch. A guarded-undo refusal must log `Error` with the transaction id and keep the recovery record available.

Extend `GetWorkflowEditorContext` with:

```json
"workflow_transaction": {
  "active": true,
  "transaction_id": "tx",
  "phase": "idle",
  "completed_steps": 1,
  "total_steps": 3,
  "cancel_requested": false,
  "has_successful_write": true,
  "watchdog_registered": true,
  "last_recovery": null
}
```

When inactive, keep the object and set `active=false`, `phase="none"`, and `last_recovery` to the most recent record.

- [ ] **Step 6: Implement the internal Python wrappers**

Use these signatures:

```python
def ue_begin_transaction(
    transaction_id: str = None,
    description: str = None,
    total_steps: int = 1,
    show_dialog: bool = True,
    idle_timeout_seconds: float = 60.0,
) -> str: ...

def ue_heartbeat_transaction(
    transaction_id: str = None,
    completed_steps: int = 0,
    total_steps: int = 1,
    message: str = "",
    has_successful_write: bool = False,
) -> str: ...

def ue_execute_step(
    transaction_id: str = None,
    action_module: str = None,
    action_name: str = None,
    params: dict = None,
) -> str:
    if not transaction_id or not re.fullmatch(
        r"UnrealMCPython\.[a-z0-9_]+_actions", action_module or ""
    ) or action_module == "UnrealMCPython.workflow_actions":
        return _error("valid transaction_id and public action module are required")
    if not re.fullmatch(r"ue_[a-z0-9_]+", action_name or ""):
        return _error("action_name must be a ue_* function")
    entered = json.loads(
        unreal.MCPythonHelper.begin_workflow_atomic_step(transaction_id)
    )
    if not entered.get("success"):
        return json.dumps(entered)
    try:
        result = mcp_unreal_actions.execute_action(
            action_module, action_name, params or {}
        )
    finally:
        ended = json.loads(
            unreal.MCPythonHelper.end_workflow_atomic_step(transaction_id)
        )
    return result if ended.get("success") else json.dumps(ended)
```

Add `ue_request_cancel` as an id-validating wrapper around `RequestWorkflowCancellation`. This is a production recovery/cancellation primitive for a connected executor, and it stays internal because `workflow_actions.py` is not scanned as a catalog domain.

- [ ] **Step 7: Add in-editor lease tests**

Add tests named:

```python
def test_lease_heartbeat_reports_progress_and_cancel(self): ...
def test_atomic_step_finally_restores_idle_phase(self): ...
def test_timeout_without_write_cancels_and_unlocks(self): ...
def test_timeout_after_write_rolls_back_and_unlocks(self): ...
def test_every_terminal_path_removes_watchdog(self): ...
```

Each test begins with `show_dialog=False`. The cancel test calls `ue_request_cancel` then asserts the next heartbeat returns `cancel_requested=true`. Timeout tests begin with `idle_timeout_seconds=0.01`, sleep for 0.02 seconds, and call heartbeat; heartbeat must detect expiry before refreshing the deadline and execute the same recovery function used by the ticker. The no-write timeout asserts `last_recovery.outcome == "cancelled_no_write"`. The write timeout mutates a temporary actor inside the transaction, first sends `has_successful_write=true`, waits for expiry, calls heartbeat again, and asserts the actor transform is restored and `last_recovery.outcome == "rolled_back"`. Every `finally` block calls cancel only if context still reports `active=true`.

- [ ] **Step 8: Run offline wrapper tests**

Run:

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_workflow_actions_wrappers.py -q
```

Expected: all wrapper tests pass.

- [ ] **Step 9: Build and run in-editor workflow tests**

Close Unreal Editor, then run from the repository root:

```powershell
$taskUeRoot = 'C:\Program Files\Epic Games\UE_5.7'
$taskBuild = Join-Path $taskUeRoot 'Engine\Build\BatchFiles\Build.bat'
& $taskBuild UnrealEditor Win64 Development "-project=$((Resolve-Path 'UnrealMCPSample.uproject').Path)" -waitmutex
```

Expected: UBT exits 0. Reopen the editor and run:

```python
import unittest
from UnrealMCPython.tests.test_workflow import TestWorkflowActions
unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(TestWorkflowActions)
)
```

Expected: all workflow tests pass, no dialog remains, and `workflow_transaction.active` is false after the suite.

- [ ] **Step 10: Commit the editor lease**

```powershell
git add Plugins/UnrealMCPython/Source/UnrealMCPython/Public/MCPythonHelper.h Plugins/UnrealMCPython/Source/UnrealMCPython/Private/MCPythonHelper_Workflow.cpp Plugins/UnrealMCPython/Content/Python/UnrealMCPython/workflow_actions.py Plugins/UnrealMCPython/Content/Python/UnrealMCPython/tests/test_workflow.py mcp-server/tests/test_workflow_actions_wrappers.py
git commit -m "feat: guard workflow transactions with editor leases"
```

---

### Task 2: Add non-blocking transport, typed runtime state, backend, and dirty-asset policy

**Files:**
- Modify: `mcp-server/src/unreal_mcp/core.py:59`
- Modify: `mcp-server/src/unreal_mcp/workflows/models.py:1`
- Modify: `mcp-server/src/unreal_mcp/workflows/store.py:1`
- Modify: `mcp-server/src/unreal_mcp/workflows/tokens.py:1`
- Modify: `mcp-server/src/unreal_mcp/workflows/planner.py:41`
- Create: `mcp-server/src/unreal_mcp/workflows/backend.py`
- Modify: `mcp-server/tests/test_core.py:1`
- Modify: `mcp-server/tests/test_workflow_store.py:1`
- Modify: `mcp-server/tests/test_workflow_tokens.py:1`
- Modify: `mcp-server/tests/test_workflow_planner.py:1`
- Create: `mcp-server/tests/test_workflow_backend.py`

- [ ] **Step 1: Write failing transport and backend tests**

Add:

```python
@pytest.mark.asyncio
async def test_send_to_unreal_does_not_block_the_event_loop(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(core, "_send_to_unreal_sync", lambda *args: (
        entered.set(), release.wait(1), {"success": True}
    )[-1])
    call = asyncio.create_task(core.send_to_unreal("M", "F", {}))
    assert await asyncio.to_thread(entered.wait, 1)
    await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
    release.set()
    assert (await call)["success"] is True
```

In `test_workflow_backend.py`, inject an async recorder and assert:

```python
await backend.begin("tx", "Build", 4)
await backend.heartbeat("tx", 1, 4, "Created", True)
await backend.execute_step("tx", invocation)
await backend.commit("tx")
assert calls == [
    ("UnrealMCPython.workflow_actions", "ue_begin_transaction",
     {"transaction_id": "tx", "description": "Build", "total_steps": 4}),
    ("UnrealMCPython.workflow_actions", "ue_heartbeat_transaction",
     {"transaction_id": "tx", "completed_steps": 1, "total_steps": 4,
      "message": "Created", "has_successful_write": True}),
    ("UnrealMCPython.workflow_actions", "ue_execute_step",
     {"transaction_id": "tx", "action_module": "UnrealMCPython.actor_actions",
      "action_name": "ue_set_location", "params": {"actor_label": "Cube",
      "location": [0, 0, 100]}}),
    ("UnrealMCPython.workflow_actions", "ue_commit_transaction",
     {"transaction_id": "tx"}),
]
```

- [ ] **Step 2: Write failing dirty-asset tests**

Add:

```python
@pytest.mark.asyncio
async def test_plan_rejects_preexisting_dirty_asset(planner):
    planner.context.fingerprints["/Game/BP_Player"] = AssetFingerprint(
        asset_path="/Game/BP_Player", exists=True, dirty=True
    )
    with pytest.raises(WorkflowPlanningError) as caught:
        await planner.plan([ActionInvocation(
            id="compile", domain="blueprint", action="compile_blueprint",
            params={"asset_path": "/Game/BP_Player"},
        )], allow_non_undoable=True)
    assert caught.value.result.errors[0].code == "PRECONDITION_FAILED"
    assert caught.value.result.errors[0].details["dirty_assets"] == [
        "/Game/BP_Player"
    ]


@pytest.mark.asyncio
async def test_apply_preflight_rejects_asset_dirtied_after_plan(planner):
    plan = await planner.plan([ActionInvocation(
        id="create", domain="blueprint", action="create_blueprint",
        params={"asset_path": "/Game/BP_Player"},
    )])
    planner.context.fingerprints["/Game/BP_Player"] = AssetFingerprint(
        asset_path="/Game/BP_Player", exists=True, dirty=True
    )
    result = await planner.verify_preconditions(plan)
    assert result.errors[0].code == "PRECONDITION_FAILED"
    assert result.errors[0].details["dirty_assets"] == ["/Game/BP_Player"]
```

- [ ] **Step 3: Run the focused tests and confirm failures**

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_core.py tests/test_workflow_backend.py tests/test_workflow_planner.py tests/test_workflow_store.py tests/test_workflow_tokens.py -q
```

Expected: collection fails for `backend.py`; dirty policy and `_send_to_unreal_sync` assertions fail.

- [ ] **Step 4: Move socket I/O to a worker thread**

Move the current body of `send_to_unreal` verbatim into synchronous `_send_to_unreal_sync(action_module, action_name, params)`. Replace the public function with:

```python
async def send_to_unreal(action_module: str, action_name: str, params: dict) -> dict:
    return await asyncio.to_thread(
        _send_to_unreal_sync, action_module, action_name, params
    )
```

Add `import asyncio`; retain exception types and `_unwrap_result` behavior.

- [ ] **Step 5: Add typed runtime state and atomic store updates**

Add to `WorkflowPlan`:

```python
transaction_id: str | None = None
post_state_fingerprints: dict[str, AssetFingerprint] = Field(default_factory=dict)
residual_fingerprints: dict[str, AssetFingerprint] = Field(default_factory=dict)
```

Exclude all three from `digest()` because they are execution state. Add:

```python
class VerificationResult(BaseModel):
    success: bool = True
    summary: str = "Verification passed."
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
```

Implement one lock-held store method:

```python
async def update_runtime(
    self,
    plan_id: str,
    *,
    status: WorkflowStatus | None = None,
    transaction_id: str | None = None,
    undo_token: str | None = None,
    post_state_fingerprints: dict[str, AssetFingerprint] | None = None,
    residual_fingerprints: dict[str, AssetFingerprint] | None = None,
    step_result: dict[str, Any] | None = None,
) -> WorkflowPlan:
```

The method changes only arguments that are not `None`, appends `step_result` once, and returns a deep copy. Runtime clearing uses empty string/dicts where required; no caller needs to clear a token back to `None` in this release.

- [ ] **Step 6: Give token errors stable reasons**

Add `TokenErrorReason(StrEnum)` values `INVALID`, `EXPIRED`, `BINDING`, and `USED`, plus:

```python
class TokenValidationError(ValueError):
    def __init__(self, reason: TokenErrorReason, message: str):
        self.reason = reason
        super().__init__(message)
```

Replace `_consume` validation `ValueError`s with this subclass. Keep `_b64decode` as a low-level `ValueError`, catch it in `_consume`, and re-raise `TokenValidationError(INVALID, str(exc))`. Existing `pytest.raises(ValueError)` tests remain valid; add assertions for expiry and replay reasons.

- [ ] **Step 7: Enforce dirty-package policy in planner and apply preflight**

After model-validating fingerprints in `plan`, compute:

```python
dirty_assets = sorted(
    path for path, fp in fingerprints.items() if fp.exists and fp.dirty
)
```

Raise `WorkflowPlanningError(error_result(...))` with code `PRECONDITION_FAILED`, path `operations`, retryable true, hint `Save or revert the listed assets, then create a new plan.`, and details `{"dirty_assets": dirty_assets}`.

At the start of `verify_preconditions`, validate current fingerprints and return the same error shape with path `plan_id` before ordinary mismatch comparison. There is no override flag.

- [ ] **Step 8: Implement the concrete backend**

Define:

```python
class WorkflowBackend(Protocol):
    async def get_identity(self) -> dict[str, Any]: ...
    async def get_fingerprints(self, asset_paths: list[str]) -> dict[str, AssetFingerprint]: ...
    async def begin(self, transaction_id: str, description: str, total_steps: int) -> dict: ...
    async def heartbeat(self, transaction_id: str, completed_steps: int,
                        total_steps: int, message: str,
                        has_successful_write: bool) -> dict: ...
    async def execute_step(self, transaction_id: str,
                           invocation: ActionInvocation) -> dict: ...
    async def execute_recovery(self, call: ActionCall) -> dict: ...
    async def restore_snapshot(self, step: PlanStep) -> dict: ...
    async def commit(self, transaction_id: str) -> dict: ...
    async def cancel_transaction(self, transaction_id: str) -> dict: ...
    async def rollback_transaction(self, transaction_id: str) -> dict: ...
    async def undo_transaction(self, transaction_id: str) -> dict: ...
```

`UnrealWorkflowBackend(sender=send_to_unreal)` routes lease calls to `UnrealMCPython.workflow_actions`; `execute_step` routes to `ue_execute_step`; `execute_recovery` routes the declared inverse directly to its public action module after the primary lease has ended. `restore_snapshot` requires `step.pre_state_snapshot["restore"]` to validate as `ActionCall` and delegates to `execute_recovery`; otherwise it returns `{"success": false, "message": "snapshot has no restore action"}`.

`get_identity` and `get_fingerprints` call `ue_get_editor_context`; identity returns only `project_id`, `editor_session_id`, and `current_map`, while fingerprints model-validate the requested keys.

- [ ] **Step 9: Run focused tests and commit**

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_core.py tests/test_workflow_backend.py tests/test_workflow_planner.py tests/test_workflow_store.py tests/test_workflow_tokens.py -q
git add src/unreal_mcp/core.py src/unreal_mcp/workflows/models.py src/unreal_mcp/workflows/store.py src/unreal_mcp/workflows/tokens.py src/unreal_mcp/workflows/planner.py src/unreal_mcp/workflows/backend.py tests/test_core.py tests/test_workflow_backend.py tests/test_workflow_planner.py tests/test_workflow_store.py tests/test_workflow_tokens.py
git commit -m "feat: add workflow runtime backend and dirty guards"
```

Expected: focused tests pass.

---

### Task 3: Specify the workflow executor state machine with failing tests

**Files:**
- Create: `mcp-server/tests/test_workflow_executor.py`

- [ ] **Step 1: Build deterministic executor fixtures**

Create `FakeBackend` with a `calls` list, response queues, `step_started`/`release_step` events, and fingerprints. Its methods append tuples matching the protocol. Create two plans: an undoable two-step transaction plan and a mixed plan whose second completed step has an explicit inverse.

Use a fixed `TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))`, shared `WorkflowStore`, real `WorkflowPlanner.verify_preconditions`, and an injected verifier returning `VerificationResult()`.

- [ ] **Step 2: Add confirmation and process-lock tests**

```python
@pytest.mark.asyncio
async def test_invalid_confirmation_never_begins_transaction(runtime):
    result = await runtime.executor.run(runtime.plan.id, "invalid")
    assert result.status is WorkflowStatus.AWAITING_CONFIRMATION
    assert result.errors[0].code == "CONFIRMATION_REQUIRED"
    assert runtime.backend.calls == []


@pytest.mark.asyncio
async def test_start_creates_exactly_one_named_task(runtime):
    first = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    second = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert first is second
    assert first.get_name() == f"workflow:{runtime.plan.id}"
    await first


@pytest.mark.asyncio
async def test_two_plans_never_overlap_editor_leases(two_runtimes):
    first = await two_runtimes.executor.start(
        two_runtimes.first.id, two_runtimes.first.confirmation_token
    )
    await two_runtimes.backend.first_begin.wait()
    second = await two_runtimes.executor.start(
        two_runtimes.second.id, two_runtimes.second.confirmation_token
    )
    await asyncio.sleep(0)
    assert two_runtimes.backend.max_active_leases == 1
    two_runtimes.backend.release_first.set()
    await asyncio.gather(first, second)
    assert two_runtimes.backend.max_active_leases == 1
```

- [ ] **Step 3: Add heartbeat, progress, and cancellation tests**

```python
@pytest.mark.asyncio
async def test_heartbeat_wraps_every_atomic_step(runtime):
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.SUCCEEDED
    assert runtime.backend.calls[:7] == [
        ("begin", runtime.plan.id, 2),
        ("heartbeat", 0, 2, "Starting create", False),
        ("step", "create"),
        ("heartbeat", 1, 2, "Completed create", True),
        ("heartbeat", 1, 2, "Starting compile", True),
        ("step", "compile"),
        ("heartbeat", 2, 2, "Completed compile", True),
    ]


@pytest.mark.asyncio
async def test_cancel_is_observed_only_after_atomic_step(runtime):
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.step_started.wait()
    await runtime.executor.cancel(runtime.plan.id)
    assert not task.done()
    runtime.backend.release_step.set()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert runtime.backend.no_step_was_interrupted
    assert ("rollback", runtime.plan.id) in runtime.backend.calls


@pytest.mark.asyncio
async def test_editor_dialog_cancel_is_observed_between_steps(runtime):
    runtime.backend.heartbeat_cancel_at = 1
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.CANCELLED
    assert [call for call in runtime.backend.calls if call[0] == "step"] == [
        ("step", "create")
    ]
```

Use `FakeProgress` with async `set_total`, `set_message`, and `increment`; assert `set_total(2)`, two increments, and step messages when `progress` is passed.

- [ ] **Step 4: Add rollback and residual-state tests**

```python
@pytest.mark.asyncio
async def test_failure_rolls_back_transaction_then_explicit_inverses(runtime):
    runtime.backend.fail_step = "verify"
    result = await runtime.executor.run(
        runtime.mixed_plan.id, runtime.mixed_plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert runtime.backend.rollback_calls == [
        ("rollback_transaction", runtime.mixed_plan.id),
        ("inverse", "asset", "delete_asset", {"asset_path": "/Game/New"}),
    ]


@pytest.mark.asyncio
async def test_failed_inverse_and_residuals_return_failed_partial(runtime):
    runtime.backend.fail_step = "verify"
    runtime.backend.fail_inverse = True
    runtime.backend.fingerprints["/Game/New"] = AssetFingerprint(
        asset_path="/Game/New", exists=True, dirty=False
    )
    result = await runtime.executor.run(
        runtime.mixed_plan.id, runtime.mixed_plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_PARTIAL
    assert result.data["residual_assets"] == ["/Game/New"]
    assert result.errors[0].code == "ROLLBACK_FAILED"


@pytest.mark.asyncio
async def test_cancel_transaction_is_used_only_before_first_write(runtime):
    runtime.backend.fail_step = "read"
    result = await runtime.executor.run(
        runtime.read_first_plan.id, runtime.read_first_plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert ("cancel_transaction", runtime.read_first_plan.id) in runtime.backend.calls
    assert not any(call[0] == "rollback" for call in runtime.backend.calls)
```

- [ ] **Step 5: Add verifier, commit, and undo eligibility tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction_recorded", "undo_available", "expects_token"),
    [(True, True, True), (True, False, False), (False, False, False)],
)
async def test_undo_token_requires_recorded_available_transaction(
    runtime, transaction_recorded, undo_available, expects_token
):
    runtime.backend.commit_result = {
        "success": True,
        "transaction_recorded": transaction_recorded,
        "undo_available": undo_available,
    }
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    stored = await runtime.store.get(runtime.plan.id)
    assert bool(stored.undo_token) is expects_token
    assert bool(result.data.get("undo_token")) is expects_token


@pytest.mark.asyncio
async def test_undo_rechecks_post_state_before_consuming_token(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    token = applied.data["undo_token"]
    runtime.backend.fingerprints["/Game/BP"] = AssetFingerprint(
        asset_path="/Game/BP", exists=True, package_guid="changed"
    )
    rejected = await runtime.executor.undo(runtime.plan.id, token)
    assert rejected.errors[0].code == "PRECONDITION_FAILED"
    assert not any(call[0] == "undo" for call in runtime.backend.calls)
```

Also assert verifier failure occurs before commit and enters the normal rollback path; verifier warnings produce `NEEDS_ATTENTION` after commit.

- [ ] **Step 6: Run and confirm the executor module is missing**

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_workflow_executor.py -q
```

Expected: collection fails because `unreal_mcp.workflows.executor` does not exist.

- [ ] **Step 7: Commit the executable state-machine specification**

```powershell
git add tests/test_workflow_executor.py
git commit -m "test: specify transactional workflow execution"
```

---

### Task 4: Implement the workflow executor

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/executor.py`
- Modify: `mcp-server/src/unreal_mcp/workflows/__init__.py:1`

- [ ] **Step 1: Define executor protocols and ownership state**

Use:

```python
class ProgressReporter(Protocol):
    async def set_total(self, total: int) -> None: ...
    async def set_message(self, message: str | None) -> None: ...
    async def increment(self, amount: int = 1) -> None: ...


class PlanVerifier(Protocol):
    async def verify(
        self, plan: WorkflowPlan, step_results: list[dict[str, Any]]
    ) -> VerificationResult: ...


class WorkflowExecutor:
    def __init__(self, planner, backend, store, tokens, verifier=None):
        self.planner = planner
        self.backend = backend
        self.store = store
        self.tokens = tokens
        self.verifier = verifier or PassingVerifier()
        self._execution_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[WorkflowResult]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
```

`start` creates exactly one task while holding `_task_lock`, names it `workflow:{plan_id}`, stores the event before scheduling, and adds a done callback that removes only the same completed task/event pair.

- [ ] **Step 2: Implement confirmation and preflight ordering**

Inside `_execution_lock`, `run` performs this order:

1. load plan and require `AWAITING_CONFIRMATION`;
2. consume the supplied confirmation token against `plan.digest()`;
3. map `TokenErrorReason.EXPIRED` to `CONFIRMATION_EXPIRED`, all other token failures to `CONFIRMATION_REQUIRED`;
4. run `planner.verify_preconditions(plan)`;
5. check the cancellation event before opening Unreal;
6. set status `RUNNING`, set `transaction_id=plan.id`, then call `backend.begin(plan.id, f"Unreal MCP workflow {plan.id}", len(plan.steps))`.

No backend call occurs before successful token consumption and fresh preconditions. A begin failure returns `TRANSACTION_FAILED` and stores `FAILED_ROLLED_BACK`.

- [ ] **Step 3: Implement step boundaries, heartbeat, and progress**

For each already-topologically-sorted `PlanStep`:

```python
await progress.set_message(f"Starting {step.id}")
heartbeat = await backend.heartbeat(
    plan.id, completed, total, f"Starting {step.id}", has_successful_write
)
if cancel_event.is_set() or heartbeat.get("cancel_requested"):
    return await self._cancel_or_rollback(...)

response = await backend.execute_step(plan.id, step.invocation)
if not response.get("success", False):
    return await self._fail_and_recover(...)

has_successful_write |= step.effect is not Effect.READ
completed += 1
await store.update_runtime(plan.id, step_result={
    "step_id": step.id, "success": True, "response": response
})
heartbeat = await backend.heartbeat(
    plan.id, completed, total, f"Completed {step.id}", has_successful_write
)
await progress.increment()
if cancel_event.is_set() or heartbeat.get("cancel_requested"):
    return await self._cancel_or_rollback(...)
```

When `progress is None`, use a no-op reporter. Normalized changes come from `response["changes"]` when valid; otherwise select `plan.predicted_changes` for that step.

- [ ] **Step 4: Implement recovery and residual classification**

`_recover` receives completed steps and `has_successful_write`. If false, call only `cancel_transaction`. If true, call `rollback_transaction`, then traverse completed nontransactional steps in reverse order:

- `explicit` calls `backend.execute_recovery(step.rollback)`;
- `snapshot` calls `backend.restore_snapshot(step)`;
- `transaction` and `none` make no second rollback call.

Re-fingerprint all initial affected paths, compare complete `AssetFingerprint.model_dump(mode="json")` values against the signed pre-state, and store only mismatches in `residual_fingerprints`. Return `FAILED_ROLLED_BACK` when transaction recovery succeeded, all explicit/snapshot calls succeeded, and residuals are empty. Otherwise return `FAILED_PARTIAL` with `ROLLBACK_FAILED`, `failed_recoveries`, and sorted `residual_assets`. Cancellation uses `CANCELLED` only when recovery is complete; an incomplete cancellation returns `FAILED_PARTIAL`.

- [ ] **Step 5: Implement verification, commit, post-state binding, and undo**

After all steps, call the verifier before commit. Verifier failure uses normal recovery. On verifier success, commit and require `commit["success"]`.

Fingerprint all affected paths and compute:

```python
post_state_digest = sha256(json.dumps(
    {path: fp.model_dump(mode="json") for path, fp in sorted(post.items())},
    sort_keys=True, separators=(",", ":")
).encode()).hexdigest()
```

Issue/store an undo token only if both `transaction_recorded is True` and `undo_available is True`. Status is `NEEDS_ATTENTION` when verifier warnings are nonempty, otherwise `SUCCEEDED`.

`undo(plan_id, token)` permits `SUCCEEDED` or `NEEDS_ATTENTION`, re-fingerprints and compares against stored `post_state_fingerprints`, then consumes the token against the same digest and calls `backend.undo_transaction(plan.transaction_id or plan.id)`. Return `PRECONDITION_FAILED` before token consumption on drift, `CONFIRMATION_REQUIRED` for invalid/replayed tokens, and `ROLLBACK_FAILED` for guarded Unreal undo refusal.

- [ ] **Step 6: Run executor tests and repair only test-proven gaps**

```powershell
cd mcp-server
uv run --extra dev pytest tests/test_workflow_executor.py -q
```

Expected: all executor tests pass with no pending asyncio tasks or unhandled task exceptions.

- [ ] **Step 7: Commit executor implementation**

```powershell
git add src/unreal_mcp/workflows/executor.py src/unreal_mcp/workflows/__init__.py
git commit -m "feat: execute cancellable transactional workflows"
```

---

### Task 5: Add workflow namespace schemas, handler, and FastMCP task routing

**Files:**
- Create: `mcp-server/src/unreal_mcp/workflows/handler.py`
- Modify: `mcp-server/src/unreal_mcp/special_action_specs.py:1`
- Modify: `mcp-server/generate_catalog.py:39`
- Modify: `mcp-server/src/unreal_mcp/dispatcher.py:1`
- Create: `mcp-server/tests/test_workflow_handler.py`
- Modify: `mcp-server/tests/test_dispatcher.py:1`
- Modify: `mcp-server/tests/test_fastmcp_v3.py:1`
- Modify: `mcp-server/tests/test_coverage.py:26`
- Regenerate: `mcp-server/src/unreal_mcp/dispatchers/_catalog.py`
- Regenerate: `mcp-server/src/unreal_mcp/dispatchers/_registry.py`

- [ ] **Step 1: Write failing handler branch tests**

Create tests with fake planner/executor and assert these exact branches:

```python
async def test_workflow_plan_routes_valid_operations(): ...
async def test_workflow_apply_starts_background_by_default(): ...
async def test_workflow_apply_waits_and_forwards_progress(): ...
async def test_workflow_get_returns_stored_runtime_state(): ...
async def test_workflow_cancel_sets_executor_event(): ...
async def test_workflow_undo_routes_signed_token(): ...
async def test_workflow_plan_gameplay_foundation_uses_installed_hook(): ...
async def test_workflow_verify_gameplay_foundation_uses_installed_hook(): ...
async def test_workflow_rejects_unknown_or_schema_invalid_action(): ...
async def test_workflow_plan_rejects_nested_workflow_operation(): ...
```

For background apply, assert `executor.start(plan_id, token)` is called and the response has `status="running"`, `data.workflow_id=plan_id`. For wait mode, pass `FakeProgress` and assert `executor.run(plan_id, token, progress)` receives the same object.

- [ ] **Step 2: Add the special-only workflow domain to generation**

Append `workflow` to `DOMAINS`. Add all seven entries to `EXTRA_ACTIONS` with exact parameter strings:

```python
"workflow": {
    "plan": {"params": "operations, allow_non_undoable=False", ...},
    "apply": {"params": "plan_id, confirmation_token, wait_for_completion=False", ...},
    "get": {"params": "plan_id", ...},
    "cancel": {"params": "plan_id", ...},
    "undo": {"params": "plan_id, undo_token", ...},
    "plan_gameplay_foundation": {"params": "spec={}", ...},
    "verify_gameplay_foundation": {"params": "spec={}", ...},
}
```

Change `_load_action_module` to return `({}, {})` when the file does not exist and the domain exists in `SPECIAL_ACTION_SPECS`; otherwise retain the missing-file failure. This makes workflow server-local without exposing the internal plugin wrappers.

- [ ] **Step 3: Add complete workflow ActionSpecs**

All seven specs use `result_kind="json"`, UE versions `5.6`, `5.7`, `5.8`, no plugin requirement, and the common permissive structured-result output schema. Use these safety values:

| Action | Effect | Risk | Idempotent | Preview | Undo | Confirmation |
|---|---|---:|---:|---:|---:|---:|
| `plan` | read | low | true | true | false | false |
| `apply` | write | high | false | false | true | true |
| `get` | read | low | true | false | false | false |
| `cancel` | write | medium | true | false | false | false |
| `undo` | destructive | high | false | false | false | true |
| `plan_gameplay_foundation` | read | low | true | true | false | false |
| `verify_gameplay_foundation` | read | low | true | false | false | false |

The `plan.operations.items` schema requires `id`, `domain`, `action`, permits object `params` and string-array `depends_on`, and sets `additionalProperties=false` at both levels. `apply` requires `plan_id` and `confirmation_token`; `get`/`cancel` require `plan_id`; `undo` requires both strings. Foundation branches accept only an object `spec` defaulting to `{}`.

- [ ] **Step 4: Implement the handler**

Use:

```python
class WorkflowHandler:
    def __init__(self, registry, planner, executor, store,
                 gameplay_planner=None, gameplay_verifier=None): ...

    async def handle(
        self, action: str, params: dict[str, Any], progress=None
    ) -> dict[str, Any]: ...
```

`handle` checks `action` in the generated workflow catalog, validates params with `Draft202012Validator`, and never runs `SafetyPolicy` because confirmation/undo policy is owned by planner/executor. Map exceptions to sanitized structured errors; `WorkflowPlanningError` returns its embedded result. `plan` model-validates operations as `ActionInvocation`; `apply` enforces the background/wait split; `get` returns the stored plan; `cancel` calls executor; `undo` calls executor.

Foundation hooks receive `params["spec"]`. When a hook is absent, return `UE_VERSION_UNSUPPORTED` with details `{"capability": "gameplay_foundation_v1"}` and hint `Complete the Blueprint authoring stage before using this workflow branch.` Tasks 14-15 replace this interim capability response by injecting the implementations.

- [ ] **Step 5: Compose one process-local service in dispatcher**

Instantiate one `UnrealWorkflowBackend`, `WorkflowStore`, ten-minute `TokenService`, `WorkflowPlanner`, `WorkflowExecutor`, and `WorkflowHandler` after `_registry` and `_settings`. Share the exact store and token service across planner/executor.

Add `workflow` to `_SPECIAL_DOMAINS` and register:

```python
from fastmcp.dependencies import Progress

@dispatcher_mcp.tool(name="workflow", description=_desc("workflow"), task=True)
async def workflow(
    action: Annotated[str, Field(description="Workflow action name.")],
    params: Annotated[dict, Field(description="Workflow action parameters.")] | None = None,
    progress: Progress = Progress(),
) -> dict:
    if action == "list_actions":
        return {"success": True, "domain": "workflow",
                "actions": CATALOG["workflow"]}
    return await _workflow_handler.handle(action, params or {}, progress)
```

The standard domain loop must not register a second workflow tool.

- [ ] **Step 6: Add FastMCP and named coverage assertions**

Assert the listed workflow `FunctionTool.task_config.mode == "optional"` and that its public parameters contain only `action` and `params` (FastMCP dependency injection excludes `progress`). Add every workflow action to `SERVER_LOCAL_TESTS["workflow"]`, pointing to the matching named function in `test_workflow_handler.py`; add none to `KNOWN_UNTESTED`.

Update dispatcher route parameterization to exclude `workflow` alongside util/vision. Assert `workflow(action="list_actions")` never calls Unreal.

- [ ] **Step 7: Generate catalog and run focused tests**

```powershell
cd mcp-server
uv run python generate_catalog.py
uv run python validate_tools.py
uv run --extra dev pytest tests/test_workflow_handler.py tests/test_workflow_executor.py tests/test_dispatcher.py tests/test_fastmcp_v3.py tests/test_discovery.py tests/test_registry_generation.py tests/test_coverage.py -q
```

Expected: generation reports 263 actions across 22 domains (256 existing plus 7 workflow actions), validation passes, and all focused tests pass.

- [ ] **Step 8: Commit namespace routing**

```powershell
git add generate_catalog.py src/unreal_mcp/special_action_specs.py src/unreal_mcp/workflows/handler.py src/unreal_mcp/dispatcher.py src/unreal_mcp/dispatchers/_catalog.py src/unreal_mcp/dispatchers/_registry.py tests/test_workflow_handler.py tests/test_dispatcher.py tests/test_fastmcp_v3.py tests/test_coverage.py
git commit -m "feat: expose task-aware workflow namespace"
```

---

### Task 6: Run end-to-end failure, cancellation, recovery, and undo gates

**Files:**
- Modify if a gate exposes a defect: only the Task 9 files listed above
- Review: `Docs/superpowers/specs/2026-07-27-workflow-editor-exclusivity-design.md`

- [ ] **Step 1: Run the complete offline suite**

```powershell
cd mcp-server
uv run python generate_catalog.py --check
uv run python validate_tools.py
uv run --extra dev pytest -q
```

Expected: catalog/registry are in sync at 263 actions across 22 domains; the complete offline suite passes.

- [ ] **Step 2: Run static source and formatting checks already available in the repository**

```powershell
cd mcp-server
uv run python -m compileall -q src tests
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 3: Rebuild Unreal Editor from a closed-editor state**

```powershell
cd ..
$taskUeRoot = 'C:\Program Files\Epic Games\UE_5.7'
$taskBuild = Join-Path $taskUeRoot 'Engine\Build\BatchFiles\Build.bat'
& $taskBuild UnrealEditor Win64 Development "-project=$((Resolve-Path 'UnrealMCPSample.uproject').Path)" -waitmutex
```

Expected: UBT exits 0 without hot-reload-only artifacts.

- [ ] **Step 4: Run in-editor workflow lease tests and liveness canary**

Run `TestWorkflowActions` as in Task 1, then execute:

```python
import json, unreal
context = json.loads(unreal.MCPythonHelper.get_workflow_editor_context([]))
assert context["success"]
assert context["workflow_transaction"]["active"] is False
assert context["workflow_transaction"]["watchdog_registered"] is False
```

Expected: all tests and the liveness assertions pass.

- [ ] **Step 5: Run a live MCP smoke workflow**

With the editor TCP server running, execute the existing E2E selection plus a temporary, undoable actor transform workflow test that:

1. calls `workflow.plan` for `actor.set_transform`;
2. calls `workflow.apply` with `wait_for_completion=true`;
3. asserts terminal success and an undo token only when Unreal reports an undo entry;
4. calls `workflow.undo`;
5. asserts the original transform fingerprint/state is restored;
6. reads `workflow.get` and the editor context after completion.

Run:

```powershell
cd mcp-server
$env:RUN_UNREAL_E2E='1'
uv run --extra dev pytest tests/test_e2e.py -q
```

Expected: live tests pass and no editor lease remains active.

- [ ] **Step 6: Perform spec-coverage review**

Check the approved design line by line and record evidence in the final handoff for:

- one open transaction and one process-local execution lock;
- modal input guard, advisory cancel, atomic phase, and 60-second idle watchdog;
- timeout recovery before/after a successful write;
- dirty pre-existing assets rejected at plan and apply;
- heartbeat before/after every step;
- cancel checked only between actions;
- guarded transaction rollback before explicit/snapshot recovery;
- residual fingerprint classification;
- undo token eligibility requiring both commit flags;
- task-enabled FastMCP workflow namespace and polling fallback.

- [ ] **Step 7: Commit any test-proven corrections, then verify clean state**

If the gates required corrections, commit each coherent correction with a `fix: workflow ...` message. Then run:

```powershell
git status --short
git log --oneline -8
```

Expected: no uncommitted Task 9 files remain; the log contains the editor lease, runtime backend, executable tests, executor, and namespace commits.

---

## Plan self-review record

### Spec coverage

- Editor UI exclusivity, advisory cancellation, watchdog cleanup, timeout rollback, and recovery context are covered by Task 1.
- The process-local execution lock, async transport responsiveness, heartbeat ordering, safe-boundary cancellation, rollback ordering, residual fingerprints, verifier ordering, and undo binding are covered by Tasks 2-4.
- Dirty-package rejection at both planning and apply is covered by Task 2.
- All seven workflow namespace actions, strict-mode bypass through signed policy, generated discovery, task support, progress, background apply, polling, and named coverage are covered by Task 5.
- UBT, in-editor, offline, live E2E, liveness, and clean-state evidence are covered by Task 6.

### Type consistency

- `transaction_id` is the plan id end-to-end and is stored on `WorkflowPlan` for undo.
- `completed_steps`, `total_steps`, and FastMCP progress totals are integers.
- All backend methods return decoded dictionaries; fingerprints are model-validated `AssetFingerprint` objects at planner/executor boundaries.
- Confirmation and undo tokens share one `TokenService`; the planner, executor, handler, and store use the same process-local instances.
- Internal Python function names match reflected C++ snake-case bindings generated by Unreal.

### External API confirmation

- FastMCP 3.2.4 documents `@mcp.tool(task=True)` with `progress: Progress = Progress()` and async `set_total`, `set_message`, and `increment`; the installed 3.2.4 package reports task mode `optional`.
- UE 5.7 headers confirm `FSlowTask::MakeDialog(bool, bool)`, `EnterProgressFrame(float, const FText&)`, `TickProgress()`, `ShouldCancel()`, `FTSTicker::GetCoreTicker().AddTicker(...)`, and static `FTSTicker::RemoveTicker(handle)`.
