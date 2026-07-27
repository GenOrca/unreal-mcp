"""Transactional workflow executor state-machine tests."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import Effect, Risk, ToolResult
from unreal_mcp.workflows.executor import WorkflowExecutor
from unreal_mcp.workflows.models import (
    ActionCall,
    ActionInvocation,
    AssetFingerprint,
    ChangeRecord,
    PlanStep,
    VerificationResult,
    WorkflowPlan,
    WorkflowStatus,
)
from unreal_mcp.workflows.store import WorkflowStore
from unreal_mcp.workflows.tokens import TokenService


def test_workflow_package_exports_executor_contracts():
    from unreal_mcp import workflows
    from unreal_mcp.workflows.executor import PlanVerifier, ProgressReporter

    assert workflows.WorkflowExecutor is WorkflowExecutor
    assert workflows.PlanVerifier is PlanVerifier
    assert workflows.ProgressReporter is ProgressReporter


class FakePlanner:
    def __init__(self):
        self.raise_error = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.result = ToolResult(
            success=True,
            status="succeeded",
            summary="Workflow preconditions still match.",
            data={},
            trace_id="preflight-trace",
        )

    async def verify_preconditions(self, _plan):
        self.entered.set()
        await self.release.wait()
        if self.raise_error:
            raise RuntimeError("preflight transport failed")
        return self.result


class FakeVerifier:
    def __init__(self):
        self.result = VerificationResult()
        self.calls = []
        self.raise_error = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def verify(self, plan, step_results):
        self.calls.append((plan.id, list(step_results)))
        self.entered.set()
        await self.release.wait()
        if self.raise_error:
            raise RuntimeError("verifier failed unexpectedly")
        return self.result


class FakeProgress:
    def __init__(self):
        self.calls = []
        self.raise_on = None
        self.block_on = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def set_total(self, total):
        self.calls.append(("total", total))

    async def set_message(self, message):
        self.calls.append(("message", message))
        if message == self.block_on:
            self.entered.set()
            await self.release.wait()
        if message == self.raise_on:
            raise RuntimeError("progress client disconnected")

    async def increment(self, amount=1):
        self.calls.append(("increment", amount))


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.fingerprints = {}
        self.fail_step = None
        self.raise_step = None
        self.raise_begin = False
        self.raise_commit = False
        self.block_commit = False
        self.raise_recovery = False
        self.block_recovery = False
        self.raise_inverse = False
        self.raise_fingerprints = False
        self.raise_post_commit_fingerprints = False
        self.block_post_commit_fingerprints = False
        self.raise_heartbeat_message = None
        self.block_heartbeat_message = None
        self.fail_inverse = False
        self.heartbeat_cancel_at = None
        self.heartbeat_response_at = {}
        self.commit_result = {
            "success": True,
            "transaction_recorded": True,
            "undo_available": True,
        }
        self.undo_result = {
            "success": True,
            "transaction_recorded": True,
            "undo_succeeded": True,
        }
        self.raise_undo = False
        self.step_started = asyncio.Event()
        self.release_step = asyncio.Event()
        self.release_step.set()
        self.no_step_was_interrupted = True
        self.active_leases = 0
        self.max_active_leases = 0
        self.first_begin = asyncio.Event()
        self.release_first = asyncio.Event()
        self.release_first.set()
        self.block_first_begin = False
        self.commit_entered = asyncio.Event()
        self.release_commit = asyncio.Event()
        self.release_commit.set()
        self.post_fingerprint_entered = asyncio.Event()
        self.release_post_fingerprint = asyncio.Event()
        self.release_post_fingerprint.set()
        self.recovery_entered = asyncio.Event()
        self.release_recovery = asyncio.Event()
        self.release_recovery.set()
        self.heartbeat_entered = asyncio.Event()
        self.release_heartbeat = asyncio.Event()
        self.release_heartbeat.set()

    async def get_identity(self):
        return {
            "project_id": "project-1",
            "editor_session_id": "session-1",
            "current_map": "/Game/TestMap",
        }

    async def get_fingerprints(self, asset_paths):
        if self.block_post_commit_fingerprints and self.active_leases == 0:
            self.post_fingerprint_entered.set()
            await self.release_post_fingerprint.wait()
        if self.raise_fingerprints or (
            self.raise_post_commit_fingerprints and self.active_leases == 0
        ):
            raise RuntimeError("fingerprint transport failed")
        return {
            path: self.fingerprints.get(
                path, AssetFingerprint(asset_path=path, exists=False)
            )
            for path in asset_paths
        }

    async def begin(self, transaction_id, _description, total_steps):
        self.calls.append(("begin", transaction_id, total_steps))
        if self.raise_begin:
            raise RuntimeError("Unreal is unavailable")
        self.active_leases += 1
        self.max_active_leases = max(
            self.max_active_leases, self.active_leases
        )
        self.first_begin.set()
        if self.block_first_begin:
            await self.release_first.wait()
            self.block_first_begin = False
        return {
            "success": True,
            "transaction_id": transaction_id,
            "transaction_index": 1,
        }

    async def heartbeat(
        self,
        _transaction_id,
        completed_steps,
        total_steps,
        message,
        has_successful_write,
    ):
        self.calls.append(
            (
                "heartbeat",
                completed_steps,
                total_steps,
                message,
                has_successful_write,
            )
        )
        if message == self.block_heartbeat_message:
            self.heartbeat_entered.set()
            await self.release_heartbeat.wait()
        if message == self.raise_heartbeat_message:
            raise RuntimeError("heartbeat transport failed")
        if message in self.heartbeat_response_at:
            response = dict(self.heartbeat_response_at[message])
            if response.get("timed_out"):
                self.active_leases -= 1
            return response
        return {
            "success": True,
            "cancel_requested": (
                completed_steps == self.heartbeat_cancel_at
            ),
        }

    async def execute_step(self, _transaction_id, invocation):
        self.calls.append(("step", invocation.id))
        self.step_started.set()
        waiting = not self.release_step.is_set()
        if waiting:
            await self.release_step.wait()
        self.no_step_was_interrupted &= not waiting or self.release_step.is_set()
        if invocation.id == self.raise_step:
            raise RuntimeError(f"transport failed during {invocation.id}")
        if invocation.id == self.fail_step:
            return {
                "success": False,
                "message": f"{invocation.id} failed",
            }
        return {
            "success": True,
            "changes": [
                {
                    "step_id": invocation.id,
                    "kind": "update",
                    "asset_path": invocation.params.get("asset_path"),
                    "details": {},
                }
            ],
        }

    async def execute_recovery(self, call):
        self.calls.append(
            ("inverse", call.domain, call.action, dict(call.params))
        )
        if self.raise_inverse:
            raise RuntimeError("inverse transport failed")
        if self.fail_inverse:
            return {"success": False, "message": "inverse failed"}
        return {"success": True}

    async def restore_snapshot(self, step):
        self.calls.append(("snapshot", step.id))
        return {"success": not self.fail_inverse}

    async def commit(self, transaction_id):
        self.calls.append(("commit", transaction_id))
        if self.raise_commit:
            raise RuntimeError("commit transport failed")
        self.commit_entered.set()
        if self.block_commit:
            await self.release_commit.wait()
        self.active_leases -= 1
        return dict(self.commit_result)

    async def request_cancel(self, transaction_id):
        self.calls.append(("request_cancel", transaction_id))
        return {"success": True, "cancel_requested": True}

    async def cancel_transaction(self, transaction_id):
        self.calls.append(("cancel_transaction", transaction_id))
        if self.raise_recovery:
            raise RuntimeError("cancel transport failed")
        self.active_leases -= 1
        return {"success": True}

    async def rollback_transaction(self, transaction_id):
        self.calls.append(("rollback_transaction", transaction_id))
        if self.raise_recovery:
            raise RuntimeError("rollback transport failed")
        self.recovery_entered.set()
        if self.block_recovery:
            await self.release_recovery.wait()
        self.active_leases -= 1
        return {
            "success": True,
            "transaction_recorded": True,
            "undo_succeeded": True,
        }

    async def undo_transaction(self, transaction_id):
        self.calls.append(("undo", transaction_id))
        if self.raise_undo:
            raise RuntimeError("undo transport failed")
        return dict(self.undo_result)


def transaction_step(step_id, *, depends_on=None, effect=Effect.WRITE):
    return PlanStep(
        invocation=ActionInvocation(
            id=step_id,
            domain="blueprint",
            action=(
                "create_blueprint"
                if step_id == "create"
                else "compile_blueprint"
            ),
            params={"asset_path": "/Game/BP"},
            depends_on=depends_on or [],
        ),
        rollback_mode="transaction" if effect is not Effect.READ else "none",
        effect=effect,
        risk=Risk.MEDIUM,
        asset_paths=["/Game/BP"],
    )


def make_plan(plan_id="plan-1", steps=None, *, asset_path="/Game/BP"):
    steps = steps or [
        transaction_step("create"),
        transaction_step("compile", depends_on=["create"]),
    ]
    fingerprint = AssetFingerprint(asset_path=asset_path, exists=False)
    return WorkflowPlan(
        id=plan_id,
        status=WorkflowStatus.AWAITING_CONFIRMATION,
        safety_mode=SafetyMode.COMPATIBLE,
        project_id="project-1",
        editor_session_id="session-1",
        current_map="/Game/TestMap",
        steps=steps,
        asset_fingerprints={asset_path: fingerprint},
        predicted_changes=[
            ChangeRecord(
                step_id=step.id,
                kind="create" if index == 0 else "update",
                asset_path=asset_path,
            )
            for index, step in enumerate(steps)
        ],
    )


async def make_runtime(plan=None, *, backend=None, tokens=None, store=None):
    plan = plan or make_plan()
    backend = backend or FakeBackend()
    tokens = tokens or TokenService(
        secret=b"x" * 32, ttl=timedelta(minutes=10)
    )
    store = store or WorkflowStore()
    plan.confirmation_token = tokens.issue_confirmation(plan.id, plan.digest())
    await store.put(plan)
    verifier = FakeVerifier()
    executor = WorkflowExecutor(
        FakePlanner(), backend, store, tokens, verifier=verifier
    )
    return SimpleNamespace(
        plan=plan,
        backend=backend,
        tokens=tokens,
        store=store,
        verifier=verifier,
        executor=executor,
    )


@pytest.fixture
async def runtime():
    return await make_runtime()


@pytest.mark.asyncio
async def test_invalid_confirmation_never_begins_transaction(runtime):
    result = await runtime.executor.run(runtime.plan.id, "invalid")
    assert result.status is WorkflowStatus.AWAITING_CONFIRMATION
    assert result.errors[0].code == "CONFIRMATION_REQUIRED"
    assert runtime.backend.calls == []


@pytest.mark.asyncio
async def test_direct_run_releases_its_cancellation_event(runtime):
    result = await runtime.executor.run(runtime.plan.id, "invalid")
    assert result.status is WorkflowStatus.AWAITING_CONFIRMATION
    assert await runtime.executor.cancel(runtime.plan.id) is False


@pytest.mark.asyncio
async def test_start_creates_exactly_one_named_task(runtime):
    runtime.backend.release_step.clear()
    first = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.step_started.wait()
    second = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert first is second
    assert first.get_name() == f"workflow:{runtime.plan.id}"
    runtime.backend.release_step.set()
    assert (await first).status is WorkflowStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_two_plans_never_overlap_editor_leases():
    backend = FakeBackend()
    backend.block_first_begin = True
    backend.release_first.clear()
    tokens = TokenService(secret=b"x" * 32, ttl=timedelta(minutes=10))
    store = WorkflowStore()
    first_runtime = await make_runtime(
        make_plan("plan-1"), backend=backend, tokens=tokens, store=store
    )
    second_plan = make_plan("plan-2")
    second_plan.confirmation_token = tokens.issue_confirmation(
        second_plan.id, second_plan.digest()
    )
    await store.put(second_plan)

    first = await first_runtime.executor.start(
        first_runtime.plan.id, first_runtime.plan.confirmation_token
    )
    await backend.first_begin.wait()
    second = await first_runtime.executor.start(
        second_plan.id, second_plan.confirmation_token
    )
    await asyncio.sleep(0)
    assert backend.max_active_leases == 1
    backend.release_first.set()
    results = await asyncio.gather(first, second)
    assert {result.status for result in results} == {WorkflowStatus.SUCCEEDED}
    assert backend.max_active_leases == 1


@pytest.mark.asyncio
async def test_task_cancellation_during_begin_waits_then_closes_lease(runtime):
    runtime.backend.block_first_begin = True
    runtime.backend.release_first.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.first_begin.wait()
    task.cancel()
    await asyncio.sleep(0)
    finished_during_begin = task.done()
    runtime.backend.release_first.set()
    result = await task
    assert not finished_during_begin
    assert result.status is WorkflowStatus.CANCELLED
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


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
async def test_progress_reports_totals_messages_and_increments(runtime):
    progress = FakeProgress()
    result = await runtime.executor.run(
        runtime.plan.id,
        runtime.plan.confirmation_token,
        progress=progress,
    )
    assert result.status is WorkflowStatus.SUCCEEDED
    assert progress.calls[0] == ("total", 2)
    assert ("message", "Starting create") in progress.calls
    assert ("message", "Completed compile") in progress.calls
    assert progress.calls.count(("increment", 1)) == 2


@pytest.mark.asyncio
async def test_progress_transport_failure_does_not_abandon_editor_lease(runtime):
    progress = FakeProgress()
    progress.raise_on = "Starting create"
    result = await runtime.executor.run(
        runtime.plan.id,
        runtime.plan.confirmation_token,
        progress=progress,
    )
    assert result.status is WorkflowStatus.SUCCEEDED
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_task_cancellation_during_progress_closes_active_lease(runtime):
    progress = FakeProgress()
    progress.block_on = "Starting create"
    progress.release.clear()
    task = asyncio.create_task(
        runtime.executor.run(
            runtime.plan.id,
            runtime.plan.confirmation_token,
            progress=progress,
        )
    )
    await progress.entered.wait()
    task.cancel()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_cancel_is_observed_only_after_atomic_step(runtime):
    runtime.backend.release_step.clear()
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
    assert ("rollback_transaction", runtime.plan.id) in runtime.backend.calls


@pytest.mark.asyncio
async def test_task_cancellation_waits_for_atomic_step_then_rolls_back(runtime):
    runtime.backend.release_step.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.step_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()

    runtime.backend.release_step.set()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert runtime.backend.no_step_was_interrupted
    assert ("rollback_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_task_cancellation_during_verification_rolls_back(runtime):
    runtime.verifier.release.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.verifier.entered.wait()
    task.cancel()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert ("rollback_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_task_cancellation_during_heartbeat_closes_active_lease(runtime):
    runtime.backend.block_heartbeat_message = "Starting create"
    runtime.backend.release_heartbeat.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.heartbeat_entered.wait()
    task.cancel()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_task_cancellation_during_commit_waits_for_commit_boundary(runtime):
    runtime.backend.block_commit = True
    runtime.backend.release_commit.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.commit_entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finished_during_commit = task.done()
    runtime.backend.release_commit.set()
    result = await task
    assert not finished_during_commit
    assert result.status is WorkflowStatus.SUCCEEDED
    assert runtime.backend.active_leases == 0


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


def mixed_failure_plan():
    create = PlanStep(
        invocation=ActionInvocation(
            id="create",
            domain="asset",
            action="save_asset",
            params={"asset_path": "/Game/New"},
        ),
        rollback_mode="explicit",
        rollback=ActionCall(
            domain="asset",
            action="delete_asset",
            params={"asset_path": "/Game/New"},
        ),
        effect=Effect.WRITE,
        risk=Risk.HIGH,
        asset_paths=["/Game/New"],
    )
    verify = transaction_step("verify", depends_on=["create"])
    verify.invocation.params = {"asset_path": "/Game/New"}
    verify.asset_paths = ["/Game/New"]
    return make_plan("mixed", [create, verify], asset_path="/Game/New")


@pytest.mark.asyncio
async def test_failure_rolls_back_transaction_then_explicit_inverses():
    runtime = await make_runtime(mixed_failure_plan())
    runtime.backend.fail_step = "verify"
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    recovery_calls = [
        call
        for call in runtime.backend.calls
        if call[0] in {"rollback_transaction", "inverse"}
    ]
    assert recovery_calls == [
        ("rollback_transaction", runtime.plan.id),
        (
            "inverse",
            "asset",
            "delete_asset",
            {"asset_path": "/Game/New"},
        ),
    ]


@pytest.mark.asyncio
async def test_failed_inverse_and_residuals_return_failed_partial():
    runtime = await make_runtime(mixed_failure_plan())
    runtime.backend.fail_step = "verify"
    runtime.backend.fail_inverse = True
    runtime.backend.fingerprints["/Game/New"] = AssetFingerprint(
        asset_path="/Game/New", exists=True, package_guid="residual"
    )
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_PARTIAL
    assert result.data["residual_assets"] == ["/Game/New"]
    assert result.errors[0].code == "ROLLBACK_FAILED"


@pytest.mark.asyncio
async def test_cancel_transaction_is_used_before_first_successful_write():
    read = transaction_step("read", effect=Effect.READ)
    runtime = await make_runtime(make_plan("read-fail", [read]))
    runtime.backend.fail_step = "read"
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls
    assert not any(
        call[0] == "rollback_transaction" for call in runtime.backend.calls
    )


@pytest.mark.asyncio
async def test_no_write_recovery_never_runs_explicit_inverse():
    first = PlanStep(
        invocation=ActionInvocation(
            id="read-one",
            domain="asset",
            action="get_asset_info",
            params={"asset_path": "/Game/BP"},
        ),
        rollback_mode="explicit",
        rollback=ActionCall(
            domain="asset",
            action="delete_asset",
            params={"asset_path": "/Game/BP"},
        ),
        effect=Effect.READ,
        risk=Risk.LOW,
        asset_paths=["/Game/BP"],
    )
    second = transaction_step(
        "read-two", depends_on=["read-one"], effect=Effect.READ
    )
    runtime = await make_runtime(make_plan("reads", [first, second]))
    runtime.backend.fail_step = "read-two"
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls
    assert not any(call[0] == "inverse" for call in runtime.backend.calls)


@pytest.mark.asyncio
async def test_transport_exception_is_structured_and_recovers_transaction(runtime):
    runtime.backend.raise_step = "create"
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls


@pytest.mark.asyncio
async def test_begin_transport_exception_is_structured_without_recovery_call(runtime):
    runtime.backend.raise_begin = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert not any(
        call[0] in {"cancel_transaction", "rollback_transaction"}
        for call in runtime.backend.calls
    )


@pytest.mark.asyncio
async def test_preflight_transport_exception_is_terminal_without_editor_recovery(runtime):
    runtime.executor.planner.raise_error = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert (await runtime.store.get(runtime.plan.id)).status is WorkflowStatus.FAILED_ROLLED_BACK
    assert runtime.backend.calls == []


@pytest.mark.asyncio
async def test_task_cancellation_during_preflight_is_terminal_without_editor_lease(runtime):
    runtime.executor.planner.release.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.executor.planner.entered.wait()
    task.cancel()
    result = await task
    assert result.status is WorkflowStatus.CANCELLED
    assert (await runtime.store.get(runtime.plan.id)).status is WorkflowStatus.CANCELLED
    assert runtime.backend.calls == []


@pytest.mark.asyncio
async def test_recovery_transport_exception_returns_failed_partial(runtime):
    runtime.backend.raise_step = "create"
    runtime.backend.raise_recovery = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_PARTIAL
    assert result.errors[0].code == "ROLLBACK_FAILED"
    assert result.data["failed_recoveries"][0]["mode"] == "transaction"


@pytest.mark.asyncio
async def test_task_cancellation_cannot_interrupt_rollback(runtime):
    runtime.backend.fail_step = "compile"
    runtime.backend.block_recovery = True
    runtime.backend.release_recovery.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.recovery_entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finished_during_recovery = task.done()
    runtime.backend.release_recovery.set()
    result = await task
    assert not finished_during_recovery
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_inverse_transport_exception_is_reported_as_failed_recovery():
    runtime = await make_runtime(mixed_failure_plan())
    runtime.backend.fail_step = "verify"
    runtime.backend.raise_inverse = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_PARTIAL
    assert any(
        item.get("mode") == "explicit"
        for item in result.data["failed_recoveries"]
    )


@pytest.mark.asyncio
async def test_refingerprint_exception_is_reported_as_failed_recovery(runtime):
    runtime.backend.fail_step = "create"
    runtime.backend.raise_fingerprints = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_PARTIAL
    assert any(
        item.get("mode") == "fingerprint"
        for item in result.data["failed_recoveries"]
    )


@pytest.mark.asyncio
async def test_heartbeat_transport_exception_recovers_active_lease(runtime):
    runtime.backend.raise_heartbeat_message = "Starting create"
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert ("cancel_transaction", runtime.plan.id) in runtime.backend.calls


@pytest.mark.asyncio
async def test_editor_timeout_before_write_does_not_cancel_transaction_twice(runtime):
    runtime.backend.heartbeat_response_at["Starting create"] = {
        "success": False,
        "timed_out": True,
        "recovery_succeeded": True,
        "recovery_outcome": "cancelled_no_write",
        "message": "lease expired",
    }
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "TIMEOUT"
    assert not any(call[0] == "cancel_transaction" for call in runtime.backend.calls)
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_editor_timeout_after_write_does_not_rollback_transaction_twice(runtime):
    runtime.backend.heartbeat_response_at["Completed create"] = {
        "success": False,
        "timed_out": True,
        "recovery_succeeded": True,
        "recovery_outcome": "rolled_back",
        "message": "lease expired and transaction rolled back",
    }
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "TIMEOUT"
    assert not any(call[0] == "rollback_transaction" for call in runtime.backend.calls)
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction_recorded", "undo_available", "expects_token"),
    [(True, True, True), (True, False, False), (False, False, False)],
)
async def test_undo_token_requires_recorded_available_transaction(
    transaction_recorded, undo_available, expects_token
):
    runtime = await make_runtime()
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
async def test_verifier_failure_rolls_back_before_commit(runtime):
    runtime.verifier.result = VerificationResult(
        success=False, summary="Static verification failed"
    )
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert ("rollback_transaction", runtime.plan.id) in runtime.backend.calls
    assert ("commit", runtime.plan.id) not in runtime.backend.calls


@pytest.mark.asyncio
async def test_verifier_exception_rolls_back_and_returns_terminal_result(runtime):
    runtime.verifier.raise_error = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "INTERNAL_ERROR"
    assert ("rollback_transaction", runtime.plan.id) in runtime.backend.calls
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_commit_transport_exception_rolls_back_unconfirmed_transaction(runtime):
    runtime.backend.raise_commit = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.FAILED_ROLLED_BACK
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert runtime.backend.calls[-1] == ("rollback_transaction", runtime.plan.id)
    assert runtime.backend.active_leases == 0


@pytest.mark.asyncio
async def test_post_commit_fingerprint_failure_is_committed_but_unreconciled(runtime):
    runtime.backend.raise_post_commit_fingerprints = True
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    stored = await runtime.store.get(runtime.plan.id)
    assert result.success is False
    assert result.status is WorkflowStatus.NEEDS_ATTENTION
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert stored.status is WorkflowStatus.NEEDS_ATTENTION
    assert not stored.undo_token
    assert not any(call[0] == "rollback_transaction" for call in runtime.backend.calls)


@pytest.mark.asyncio
async def test_task_cancellation_after_commit_records_unreconciled_state(runtime):
    runtime.backend.block_post_commit_fingerprints = True
    runtime.backend.release_post_fingerprint.clear()
    task = await runtime.executor.start(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    await runtime.backend.post_fingerprint_entered.wait()
    task.cancel()
    result = await task
    stored = await runtime.store.get(runtime.plan.id)
    assert result.status is WorkflowStatus.NEEDS_ATTENTION
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert stored.status is WorkflowStatus.NEEDS_ATTENTION
    assert runtime.backend.active_leases == 0
    assert not any(call[0] == "rollback_transaction" for call in runtime.backend.calls)


@pytest.mark.asyncio
async def test_verifier_warnings_produce_needs_attention(runtime):
    runtime.verifier.result = VerificationResult(
        warnings=[{"code": "COMPILER_WARNING", "message": "warning"}]
    )
    result = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    assert result.status is WorkflowStatus.NEEDS_ATTENTION
    assert result.warnings == runtime.verifier.result.warnings


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


@pytest.mark.asyncio
async def test_undo_fingerprint_transport_failure_keeps_unconsumed_token(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    token = applied.data["undo_token"]
    runtime.backend.raise_fingerprints = True
    result = await runtime.executor.undo(runtime.plan.id, token)
    assert result.errors[0].code == "UE_UNAVAILABLE"
    assert (await runtime.store.get(runtime.plan.id)).undo_token == token
    assert not any(call[0] == "undo" for call in runtime.backend.calls)


@pytest.mark.asyncio
async def test_successful_undo_clears_token_and_cannot_replay(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    token = applied.data["undo_token"]
    undone = await runtime.executor.undo(runtime.plan.id, token)
    assert undone.success is True
    assert ("undo", runtime.plan.id) in runtime.backend.calls
    assert (await runtime.store.get(runtime.plan.id)).undo_token == ""

    replayed = await runtime.executor.undo(runtime.plan.id, token)
    assert replayed.errors[0].code == "CONFIRMATION_REQUIRED"
    assert [call for call in runtime.backend.calls if call[0] == "undo"] == [
        ("undo", runtime.plan.id)
    ]


@pytest.mark.asyncio
async def test_guarded_undo_refusal_clears_consumed_token(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    token = applied.data["undo_token"]
    runtime.backend.undo_result = {
        "success": False,
        "message": "undo head changed",
    }
    refused = await runtime.executor.undo(runtime.plan.id, token)
    assert refused.errors[0].code == "ROLLBACK_FAILED"
    assert (await runtime.store.get(runtime.plan.id)).undo_token == ""

    replayed = await runtime.executor.undo(runtime.plan.id, token)
    assert replayed.errors[0].code == "CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_undo_transport_failure_is_structured_and_consumes_token(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    token = applied.data["undo_token"]
    runtime.backend.raise_undo = True
    failed = await runtime.executor.undo(runtime.plan.id, token)
    assert failed.errors[0].code == "UE_UNAVAILABLE"
    assert (await runtime.store.get(runtime.plan.id)).undo_token == ""


@pytest.mark.asyncio
async def test_undo_waits_for_concurrent_apply_to_release_execution_lock(runtime):
    applied = await runtime.executor.run(
        runtime.plan.id, runtime.plan.confirmation_token
    )
    undo_token = applied.data["undo_token"]

    second = make_plan("plan-2")
    second.confirmation_token = runtime.tokens.issue_confirmation(
        second.id, second.digest()
    )
    await runtime.store.put(second)
    runtime.backend.step_started.clear()
    runtime.backend.release_step.clear()
    apply_task = await runtime.executor.start(
        second.id, second.confirmation_token
    )
    await runtime.backend.step_started.wait()

    undo_task = asyncio.create_task(
        runtime.executor.undo(runtime.plan.id, undo_token)
    )
    await asyncio.sleep(0)
    undo_finished_during_apply = undo_task.done()
    undo_calls_during_apply = [
        call for call in runtime.backend.calls if call[0] == "undo"
    ]

    runtime.backend.release_step.set()
    assert (await apply_task).status is WorkflowStatus.SUCCEEDED
    assert (await undo_task).success is True
    assert not undo_finished_during_apply
    assert undo_calls_during_apply == []
    assert runtime.backend.max_active_leases == 1
