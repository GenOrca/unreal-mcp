# Workflow Editor Exclusivity and Recovery Design

**Date:** 2026-07-27  
**Status:** Awaiting written-spec review  
**Parent design:** `2026-07-27-unreal-mcp-blueprint-gameplay-foundation-design.md`

## Problem

Task 8 introduced a guarded Unreal transaction that remains open across MCP
requests. Queue-index, transaction-GUID, stack-head, and expiry checks prevent
the helper from undoing the wrong transaction. They do not stop a human editor
action or another editor subsystem from nesting work into the active workflow
transaction between requests. A disconnected MCP process can also leave the
transaction open until the editor exits.

Asset fingerprints have a related limitation: `dirty=true` does not change
when an already-dirty package receives more unsaved edits. A workflow must not
claim that such a package still matches its planned state.

## Considered approaches

### One Unreal call for the entire workflow

Running every operation in one Python call prevents editor input between
steps. It also blocks the MCP server from observing cancellation, reporting
live progress, or applying normal per-step timeout handling while that call is
running. This conflicts with the Task 9 contract.

### Independent transaction per step

Short transactions avoid a long editor lock, but a foreign transaction can
appear between steps. Rollback then cannot cross that transaction safely and
must become partial. It also complicates the single undo-token contract.

### Modal editor guard with heartbeat watchdog

Keep the single scoped transaction from the approved plan. While it is active,
show an Unreal slow-task dialog that blocks ordinary editor interaction, expose
its Cancel button to the executor, and maintain a ticker-based watchdog. This
preserves per-step progress, cancellation, and one workflow undo entry. This is
the selected approach.

## Editor-side transaction lease

Beginning a workflow transaction creates one editor-side lease containing:

- the MCP transaction id, Unreal queue index, and Unreal transaction GUID;
- an `FScopedSlowTask` sized to the workflow step count;
- a monotonic last-heartbeat timestamp;
- an idle/atomic-step phase flag;
- whether at least one write step has succeeded;
- a 60-second idle timeout; and
- an `FTSTicker` callback that checks the lease once per second.

`FScopedSlowTask::MakeDialog(true)` is used only in interactive editor mode.
Unattended tests keep the same lease and watchdog without attempting to create
a visible dialog. The dialog's Cancel button is advisory: heartbeat responses
return `cancel_requested=true`, and the executor observes it only between
atomic steps.

The internal heartbeat action accepts the transaction id, completed and total
step counts, a compact status message, and the current `has_successful_write`
state. A valid heartbeat refreshes the deadline, advances the slow task by the
delta since the previous heartbeat, updates the message, and reports whether
the user requested cancellation.

Every registry action is invoked through one internal Unreal Python step
wrapper. The wrapper verifies the transaction id, marks the lease as executing
an atomic step, calls the real `ue_*` function, and restores the lease to idle
with a refreshed deadline in `finally` before control returns to the editor
event loop. The wrapper is not registered in the public action catalog.

All terminal helpers remove the ticker and destroy the slow-task dialog before
clearing transaction state. Commit, cancel, rollback, and undo retain the Task
8 queue-index/GUID/head/expiry checks.

`GetWorkflowEditorContext` also reports a compact `workflow_transaction`
object with the active transaction id, lease state, cancel flag, and the most
recent watchdog recovery record. This lets a restarted server explain whether
the editor rolled back automatically or requires manual recovery.

## Timeout and disconnect recovery

If no heartbeat arrives for 60 seconds, the editor owns recovery:

- with no successful write, it cancels the scoped transaction;
- after a successful write, it closes the transaction and undoes it only if
  the stored queue index and GUID are still the non-expired undo-stack head;
- if guarded undo is impossible, it leaves state untouched, emits an explicit
  error containing the transaction id, and stores a last-recovery record for
  inspection after reconnect; and
- in every case it removes the dialog and ticker so the editor is not left
  locked.

The timeout is an idle timeout rather than a per-step runtime limit. Unreal's
game-thread ticker cannot fire while one atomic Python action blocks the game
thread. The internal step wrapper restores the idle phase in `finally` before
the ticker can run again, so the 60-second deadline starts after the action
returns and a legitimate long action is not rolled back immediately on its
first subsequent editor tick.

## Server-side executor ownership

Task 9 uses one process-local async execution lock so two MCP workflows cannot
overlap. After confirmation and fresh precondition checks, the executor:

1. begins the editor transaction lease with the exact step total;
2. sends a heartbeat before and after every atomic step;
3. invokes each registry action through the internal atomic-step wrapper;
4. checks MCP cancellation and editor-dialog cancellation only between steps;
5. rolls back completed work on failure or cancellation;
6. commits only after every step and verifier succeeds; and
7. issues an undo token only when commit reports
   `transaction_recorded=true` and `undo_available=true`.

The editor lease protects against ordinary UI interaction; the async lock
protects against concurrent MCP workflows. Neither is presented as a general
lock for arbitrary third-party code that deliberately mutates the editor from
another thread.

## Dirty-asset policy

Discovery may inspect dirty assets, but the planner does not produce an
applicable plan when a pre-existing affected asset has `dirty=true`. Apply
rechecks the same rule before beginning the transaction lease. The error is
`PRECONDITION_FAILED` and instructs the caller to save or revert the asset and
create a new plan. There is no override in this release.

Assets created or dirtied by the running workflow are not rejected mid-run;
their initial fingerprints were captured before the transaction began.
Post-state fingerprints remain part of undo-token binding. The Unreal helper's
transaction-head/GUID check supplies an additional guard against intervening
transacted editor changes.

## Failure reporting

Timeout, guarded-undo refusal, and dirty-asset rejection use structured errors
and never silently downgrade to success. Workflow terminal state distinguishes
complete rollback from partial rollback. Residual fingerprints and failed
inverse operations are included in `failed_partial` results.

## Verification

Offline executor tests cover serialization, heartbeat ordering, dialog cancel,
timeout mapping, dirty-asset rejection, rollback ordering, and undo-token
eligibility. In-editor tests cover dialog-less unattended leases, heartbeat
refresh, user cancellation state, timeout before and after a write, pre-existing
transactions, and cleanup after every terminal path.
