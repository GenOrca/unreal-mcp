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


class FakePlanner:
    def __init__(self):
        self.result = ToolResult(
            success=True,
            status="succeeded",
            summary="Workflow preconditions still match.",
            data={},
            trace_id="preflight-trace",
        )

    async def verify_preconditions(self, _plan):
        return self.result


class FakeVerifier:
    def __init__(self):
        self.result = VerificationResult()
        self.calls = []

    async def verify(self, plan, step_results):
        self.calls.append((plan.id, list(step_results)))
        return self.result


class FakeProgress:
    def __init__(self):
        self.calls = []

    async def set_total(self, total):
        self.calls.append(("total", total))

    async def set_message(self, message):
        self.calls.append(("message", message))

    async def increment(self, amount=1):
        self.calls.append(("increment", amount))


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.fingerprints = {}
        self.fail_step = None
        self.fail_inverse = False
        self.heartbeat_cancel_at = None
        self.commit_result = {
            "success": True,
            "transaction_recorded": True,
            "undo_available": True,
        }
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

    async def get_identity(self):
        return {
            "project_id": "project-1",
            "editor_session_id": "session-1",
            "current_map": "/Game/TestMap",
        }

    async def get_fingerprints(self, asset_paths):
        return {
            path: self.fingerprints.get(
                path, AssetFingerprint(asset_path=path, exists=False)
            )
            for path in asset_paths
        }

    async def begin(self, transaction_id, _description, total_steps):
        self.calls.append(("begin", transaction_id, total_steps))
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
        if self.fail_inverse:
            return {"success": False, "message": "inverse failed"}
        return {"success": True}

    async def restore_snapshot(self, step):
        self.calls.append(("snapshot", step.id))
        return {"success": not self.fail_inverse}

    async def commit(self, transaction_id):
        self.calls.append(("commit", transaction_id))
        self.active_leases -= 1
        return dict(self.commit_result)

    async def request_cancel(self, transaction_id):
        self.calls.append(("request_cancel", transaction_id))
        return {"success": True, "cancel_requested": True}

    async def cancel_transaction(self, transaction_id):
        self.calls.append(("cancel_transaction", transaction_id))
        self.active_leases -= 1
        return {"success": True}

    async def rollback_transaction(self, transaction_id):
        self.calls.append(("rollback_transaction", transaction_id))
        self.active_leases -= 1
        return {
            "success": True,
            "transaction_recorded": True,
            "undo_succeeded": True,
        }

    async def undo_transaction(self, transaction_id):
        self.calls.append(("undo", transaction_id))
        return {
            "success": True,
            "transaction_recorded": True,
            "undo_succeeded": True,
        }


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
