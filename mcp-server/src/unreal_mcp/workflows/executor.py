"""Serialized background workflow execution, recovery, and guarded undo."""

import asyncio
from hashlib import sha256
import json
from typing import Any, Protocol
from uuid import uuid4

from unreal_mcp.contracts import Effect, ErrorCode
from unreal_mcp.errors import error_result
from unreal_mcp.workflows.models import (
    AssetFingerprint,
    ChangeRecord,
    VerificationResult,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)
from unreal_mcp.workflows.tokens import (
    TokenErrorReason,
    TokenValidationError,
)


class ProgressReporter(Protocol):
    async def set_total(self, total: int) -> None: ...

    async def set_message(self, message: str | None) -> None: ...

    async def increment(self, amount: int = 1) -> None: ...


class PlanVerifier(Protocol):
    async def verify(
        self, plan: WorkflowPlan, step_results: list[dict[str, Any]]
    ) -> VerificationResult: ...


class _NoopProgress:
    async def set_total(self, _total: int) -> None:
        return None

    async def set_message(self, _message: str | None) -> None:
        return None

    async def increment(self, _amount: int = 1) -> None:
        return None


class _PassingVerifier:
    async def verify(
        self, _plan: WorkflowPlan, _step_results: list[dict[str, Any]]
    ) -> VerificationResult:
        return VerificationResult()


class WorkflowExecutor:
    def __init__(
        self,
        planner,
        backend,
        store,
        tokens,
        *,
        verifier: PlanVerifier | None = None,
    ):
        self.planner = planner
        self.backend = backend
        self.store = store
        self.tokens = tokens
        self.verifier = verifier or _PassingVerifier()
        self._execution_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[WorkflowResult]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def start(
        self, plan_id: str, confirmation_token: str
    ) -> asyncio.Task[WorkflowResult]:
        async with self._task_lock:
            existing = self._tasks.get(plan_id)
            if existing is not None and not existing.done():
                return existing
            cancel_event = asyncio.Event()
            self._cancel_events[plan_id] = cancel_event
            task = asyncio.create_task(
                self.run(
                    plan_id,
                    confirmation_token,
                    cancel_event=cancel_event,
                ),
                name=f"workflow:{plan_id}",
            )
            self._tasks[plan_id] = task
            task.add_done_callback(
                lambda completed, workflow_id=plan_id: self._task_finished(
                    workflow_id, completed
                )
            )
            return task

    def _task_finished(
        self, plan_id: str, task: asyncio.Task[WorkflowResult]
    ) -> None:
        if self._tasks.get(plan_id) is task:
            self._tasks.pop(plan_id, None)
            self._cancel_events.pop(plan_id, None)

    async def cancel(self, plan_id: str) -> bool:
        event = self._cancel_events.get(plan_id)
        if event is None:
            return False
        event.set()
        return True

    async def run(
        self,
        plan_id: str,
        confirmation_token: str,
        progress: ProgressReporter | None = None,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> WorkflowResult:
        owns_event = cancel_event is None
        event = cancel_event or self._cancel_events.setdefault(
            plan_id, asyncio.Event()
        )
        try:
            return await self._run(
                plan_id,
                confirmation_token,
                progress,
                cancel_event=event,
            )
        finally:
            if owns_event and self._cancel_events.get(plan_id) is event:
                self._cancel_events.pop(plan_id, None)

    async def _run(
        self,
        plan_id: str,
        confirmation_token: str,
        progress: ProgressReporter | None,
        *,
        cancel_event: asyncio.Event,
    ) -> WorkflowResult:
        reporter = progress or _NoopProgress()
        event = cancel_event
        async with self._execution_lock:
            try:
                plan = await self.store.get(plan_id)
            except KeyError as exc:
                return self._error_result(
                    plan_id,
                    WorkflowStatus.FAILED_ROLLED_BACK,
                    ErrorCode.INVALID_INPUT,
                    str(exc),
                    "Use a workflow_id returned by workflow.plan.",
                )

            if plan.status is not WorkflowStatus.AWAITING_CONFIRMATION:
                return self._error_result(
                    plan_id,
                    plan.status,
                    ErrorCode.CONFLICT,
                    f"Workflow is already {plan.status.value}",
                    "Call workflow.get and create a new plan if another run is needed.",
                )

            try:
                self.tokens.consume_confirmation(
                    confirmation_token, plan.id, plan.digest()
                )
            except (TokenValidationError, ValueError) as exc:
                reason = getattr(exc, "reason", TokenErrorReason.INVALID)
                code = (
                    ErrorCode.CONFIRMATION_EXPIRED
                    if reason is TokenErrorReason.EXPIRED
                    else ErrorCode.CONFIRMATION_REQUIRED
                )
                return self._error_result(
                    plan.id,
                    WorkflowStatus.AWAITING_CONFIRMATION,
                    code,
                    str(exc),
                    "Create a fresh workflow plan and use its confirmation token.",
                )

            try:
                preflight = await self.planner.verify_preconditions(plan)
            except asyncio.CancelledError:
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.CANCELLED
                )
                return WorkflowResult(
                    success=False,
                    status=WorkflowStatus.CANCELLED,
                    summary="Workflow was cancelled during preflight.",
                    plan_id=plan.id,
                    trace_id=uuid4().hex,
                )
            except Exception as exc:
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.FAILED_ROLLED_BACK
                )
                return self._error_result(
                    plan.id,
                    WorkflowStatus.FAILED_ROLLED_BACK,
                    ErrorCode.UE_UNAVAILABLE,
                    str(exc),
                    "Reconnect to Unreal Editor and create a fresh plan.",
                )
            if not preflight.success:
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.FAILED_ROLLED_BACK
                )
                return WorkflowResult(
                    success=False,
                    status=WorkflowStatus.FAILED_ROLLED_BACK,
                    summary=preflight.summary,
                    plan_id=plan.id,
                    errors=preflight.errors,
                    trace_id=preflight.trace_id,
                )

            if event.is_set():
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.CANCELLED
                )
                return WorkflowResult(
                    success=False,
                    status=WorkflowStatus.CANCELLED,
                    summary="Workflow was cancelled before execution.",
                    plan_id=plan.id,
                    trace_id=uuid4().hex,
                )

            total_steps = len(plan.steps)
            if await self._report_progress(reporter.set_total(total_steps)):
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.CANCELLED
                )
                return WorkflowResult(
                    success=False,
                    status=WorkflowStatus.CANCELLED,
                    summary="Workflow was cancelled before execution.",
                    plan_id=plan.id,
                    trace_id=uuid4().hex,
                )
            await self.store.update_runtime(
                plan.id,
                status=WorkflowStatus.RUNNING,
                transaction_id=plan.id,
            )
            try:
                begin, begin_cancelled = await self._begin_boundary(
                    plan.id,
                    f"Unreal MCP workflow {plan.id}",
                    total_steps,
                )
            except Exception as exc:
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.FAILED_ROLLED_BACK
                )
                return self._error_result(
                    plan.id,
                    WorkflowStatus.FAILED_ROLLED_BACK,
                    ErrorCode.UE_UNAVAILABLE,
                    str(exc),
                    "Reconnect to Unreal Editor and create a fresh plan.",
                )
            if not begin.get("success", False):
                await self.store.update_runtime(
                    plan.id, status=WorkflowStatus.FAILED_ROLLED_BACK
                )
                return self._error_result(
                    plan.id,
                    WorkflowStatus.FAILED_ROLLED_BACK,
                    ErrorCode.TRANSACTION_FAILED,
                    begin.get("message", "Unreal could not begin the workflow transaction."),
                    "Inspect workflow.get and the Unreal workflow editor context.",
                )
            if begin_cancelled:
                return await self._recover_after_task_cancellation(
                    plan, [], [], False
                )

            completed_steps = []
            changes: list[ChangeRecord] = []
            has_successful_write = False

            for step in plan.steps:
                start_message = f"Starting {step.id}"
                if await self._report_progress(
                    reporter.set_message(start_message)
                ):
                    return await self._recover_after_task_cancellation(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                    )
                heartbeat, heartbeat_error_code = await self._heartbeat(
                    plan.id,
                    len(completed_steps),
                    total_steps,
                    start_message,
                    has_successful_write,
                )
                if heartbeat.get("task_cancelled", False):
                    return await self._recover_after_task_cancellation(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                    )
                if not heartbeat.get("success", False):
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=False,
                        failure_message=heartbeat.get(
                            "message", "Workflow lease heartbeat failed."
                        ),
                        failure_code=heartbeat_error_code,
                        completed_transaction_recovery=(
                            self._timeout_recovery(heartbeat)
                        ),
                    )
                if event.is_set() or heartbeat.get("cancel_requested", False):
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=True,
                    )

                try:
                    response, task_cancelled = (
                        await self._execute_atomic_step(
                            plan.id, step.invocation
                        )
                    )
                except Exception as exc:
                    response = {
                        "success": False,
                        "message": str(exc),
                    }
                    await self.store.update_runtime(
                        plan.id,
                        step_result={
                            "step_id": step.id,
                            "success": False,
                            "response": response,
                        },
                    )
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=False,
                        failure_message=str(exc),
                        failure_code=ErrorCode.UE_UNAVAILABLE,
                    )
                if task_cancelled:
                    event.set()
                if not response.get("success", False):
                    await self.store.update_runtime(
                        plan.id,
                        step_result={
                            "step_id": step.id,
                            "success": False,
                            "response": response,
                        },
                    )
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=False,
                        failure_message=response.get(
                            "message", f"Workflow step '{step.id}' failed."
                        ),
                        failure_code=ErrorCode.INTERNAL_ERROR,
                    )

                has_successful_write |= step.effect is not Effect.READ
                completed_steps.append(step)
                step_result = {
                    "step_id": step.id,
                    "success": True,
                    "response": response,
                }
                stored = await self.store.update_runtime(
                    plan.id, step_result=step_result
                )
                changes.extend(self._step_changes(plan, step.id, response))

                completed_message = f"Completed {step.id}"
                heartbeat, heartbeat_error_code = await self._heartbeat(
                    plan.id,
                    len(completed_steps),
                    total_steps,
                    completed_message,
                    has_successful_write,
                )
                progress_cancelled = await self._report_progress(
                    reporter.set_message(completed_message)
                )
                progress_cancelled |= await self._report_progress(
                    reporter.increment()
                )
                if progress_cancelled:
                    return await self._recover_after_task_cancellation(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                    )
                if heartbeat.get("task_cancelled", False):
                    return await self._recover_after_task_cancellation(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                    )
                if not heartbeat.get("success", False):
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=False,
                        failure_message=heartbeat.get(
                            "message", "Workflow lease heartbeat failed."
                        ),
                        failure_code=heartbeat_error_code,
                        completed_transaction_recovery=(
                            self._timeout_recovery(heartbeat)
                        ),
                    )
                if event.is_set() or heartbeat.get("cancel_requested", False):
                    return await self._recover(
                        plan,
                        completed_steps,
                        changes,
                        has_successful_write,
                        cancelled=True,
                    )

            try:
                verification = await self.verifier.verify(
                    plan, list(stored.step_results if plan.steps else [])
                )
            except asyncio.CancelledError:
                return await self._recover_after_task_cancellation(
                    plan,
                    completed_steps,
                    changes,
                    has_successful_write,
                )
            except Exception as exc:
                return await self._recover(
                    plan,
                    completed_steps,
                    changes,
                    has_successful_write,
                    cancelled=False,
                    failure_message=str(exc),
                    failure_code=ErrorCode.INTERNAL_ERROR,
                )
            if not verification.success:
                return await self._recover(
                    plan,
                    completed_steps,
                    changes,
                    has_successful_write,
                    cancelled=False,
                    failure_message=verification.summary,
                    failure_code=ErrorCode.VERIFICATION_FAILED,
                )

            try:
                commit, _commit_cancelled = await self._commit_boundary(
                    plan.id
                )
            except Exception as exc:
                return await self._recover(
                    plan,
                    completed_steps,
                    changes,
                    has_successful_write,
                    cancelled=False,
                    failure_message=str(exc),
                    failure_code=ErrorCode.UE_UNAVAILABLE,
                )
            if not commit.get("success", False):
                return await self._recover(
                    plan,
                    completed_steps,
                    changes,
                    has_successful_write,
                    cancelled=False,
                    failure_message=commit.get(
                        "message", "Unreal could not commit the workflow transaction."
                    ),
                    failure_code=ErrorCode.TRANSACTION_FAILED,
                )

            try:
                post_state = await self.backend.get_fingerprints(
                    sorted(plan.asset_fingerprints)
                )
            except asyncio.CancelledError:
                return await self._committed_unreconciled(
                    plan,
                    changes,
                    verification,
                    commit,
                    "Post-state capture was cancelled.",
                )
            except Exception as exc:
                return await self._committed_unreconciled(
                    plan,
                    changes,
                    verification,
                    commit,
                    str(exc),
                )
            undo_token = None
            if (
                commit.get("transaction_recorded") is True
                and commit.get("undo_available") is True
            ):
                undo_token = self.tokens.issue_undo(
                    plan.id, self._fingerprint_digest(post_state)
                )
            status = (
                WorkflowStatus.NEEDS_ATTENTION
                if verification.warnings
                else WorkflowStatus.SUCCEEDED
            )
            await self.store.update_runtime(
                plan.id,
                status=status,
                undo_token=undo_token,
                post_state_fingerprints=post_state,
                residual_fingerprints={},
            )
            data = {
                "workflow_id": plan.id,
                "transaction_recorded": bool(
                    commit.get("transaction_recorded")
                ),
                "undo_available": bool(commit.get("undo_available")),
            }
            if undo_token:
                data["undo_token"] = undo_token
            return WorkflowResult(
                success=True,
                status=status,
                summary=(
                    "Workflow completed with warnings."
                    if verification.warnings
                    else "Workflow completed successfully."
                ),
                plan_id=plan.id,
                data=data,
                changes=changes,
                warnings=verification.warnings,
                trace_id=uuid4().hex,
            )

    async def _heartbeat(
        self,
        transaction_id: str,
        completed_steps: int,
        total_steps: int,
        message: str,
        has_successful_write: bool,
    ) -> tuple[dict[str, Any], ErrorCode]:
        try:
            response = await self.backend.heartbeat(
                transaction_id,
                completed_steps,
                total_steps,
                message,
                has_successful_write,
            )
            return response, ErrorCode.TIMEOUT
        except asyncio.CancelledError:
            return (
                {
                    "success": False,
                    "task_cancelled": True,
                    "message": "Workflow task was cancelled.",
                },
                ErrorCode.INTERNAL_ERROR,
            )
        except Exception as exc:
            return (
                {"success": False, "message": str(exc)},
                ErrorCode.UE_UNAVAILABLE,
            )

    async def _execute_atomic_step(
        self, transaction_id: str, invocation
    ) -> tuple[dict[str, Any], bool]:
        return await self._await_boundary(
            self.backend.execute_step(transaction_id, invocation),
            task_name=f"workflow-step:{transaction_id}:{invocation.id}",
        )

    async def _begin_boundary(
        self, transaction_id: str, description: str, total_steps: int
    ) -> tuple[dict[str, Any], bool]:
        return await self._await_boundary(
            self.backend.begin(transaction_id, description, total_steps),
            task_name=f"workflow-begin:{transaction_id}",
        )

    async def _commit_boundary(
        self, transaction_id: str
    ) -> tuple[dict[str, Any], bool]:
        return await self._await_boundary(
            self.backend.commit(transaction_id),
            task_name=f"workflow-commit:{transaction_id}",
        )

    @staticmethod
    async def _await_boundary(awaitable, *, task_name: str):
        boundary_task = asyncio.create_task(awaitable, name=task_name)
        cancellation_requested = False
        while True:
            try:
                response = await asyncio.shield(boundary_task)
                return response, cancellation_requested
            except asyncio.CancelledError:
                cancellation_requested = True

    @staticmethod
    async def _report_progress(awaitable) -> bool:
        try:
            await awaitable
            return False
        except asyncio.CancelledError:
            return True
        except Exception:
            return False

    async def _recover(
        self,
        plan: WorkflowPlan,
        completed_steps: list,
        changes: list[ChangeRecord],
        has_successful_write: bool,
        *,
        cancelled: bool,
        failure_message: str = "Workflow was cancelled.",
        failure_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        completed_transaction_recovery: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        recovery_task = asyncio.create_task(
            self._recover_impl(
                plan,
                completed_steps,
                changes,
                has_successful_write,
                cancelled=cancelled,
                failure_message=failure_message,
                failure_code=failure_code,
                completed_transaction_recovery=(
                    completed_transaction_recovery
                ),
            ),
            name=f"workflow-recovery:{plan.id}",
        )
        while True:
            try:
                return await asyncio.shield(recovery_task)
            except asyncio.CancelledError:
                continue

    async def _recover_impl(
        self,
        plan: WorkflowPlan,
        completed_steps: list,
        changes: list[ChangeRecord],
        has_successful_write: bool,
        *,
        cancelled: bool,
        failure_message: str,
        failure_code: ErrorCode,
        completed_transaction_recovery: dict[str, Any] | None,
    ) -> WorkflowResult:
        failed_recoveries = []
        transaction_recovery = completed_transaction_recovery
        if transaction_recovery is None:
            try:
                if has_successful_write:
                    transaction_recovery = (
                        await self.backend.rollback_transaction(plan.id)
                    )
                else:
                    transaction_recovery = (
                        await self.backend.cancel_transaction(plan.id)
                    )
            except Exception as exc:
                transaction_recovery = {
                    "success": False,
                    "message": str(exc),
                }
        if not transaction_recovery.get("success", False):
            failed_recoveries.append(
                {
                    "mode": "transaction",
                    "message": transaction_recovery.get(
                        "message", "transaction recovery failed"
                    ),
                }
            )

        if has_successful_write:
            for step in reversed(completed_steps):
                response = None
                try:
                    if step.rollback_mode == "explicit":
                        response = await self.backend.execute_recovery(
                            step.rollback
                        )
                    elif step.rollback_mode == "snapshot":
                        response = await self.backend.restore_snapshot(step)
                except Exception as exc:
                    response = {"success": False, "message": str(exc)}
                if response is not None and not response.get("success", False):
                    failed_recoveries.append(
                        {
                            "step_id": step.id,
                            "mode": step.rollback_mode,
                            "message": response.get(
                                "message", "step recovery failed"
                            ),
                        }
                    )

        try:
            current = await self.backend.get_fingerprints(
                sorted(plan.asset_fingerprints)
            )
        except Exception as exc:
            current = None
            failed_recoveries.append(
                {
                    "mode": "fingerprint",
                    "message": str(exc),
                }
            )
        residuals = (
            {
                path: AssetFingerprint.model_validate(current[path])
                for path, expected in plan.asset_fingerprints.items()
                if AssetFingerprint.model_validate(current[path]).model_dump(
                    mode="json"
                )
                != expected.model_dump(mode="json")
            }
            if current is not None
            else {}
        )
        recovery_complete = not failed_recoveries and not residuals
        if cancelled and recovery_complete:
            status = WorkflowStatus.CANCELLED
        elif recovery_complete:
            status = WorkflowStatus.FAILED_ROLLED_BACK
        else:
            status = WorkflowStatus.FAILED_PARTIAL
        await self.store.update_runtime(
            plan.id,
            status=status,
            residual_fingerprints=residuals,
        )

        if status is WorkflowStatus.FAILED_PARTIAL:
            code = ErrorCode.ROLLBACK_FAILED
            message = "Workflow recovery was incomplete."
            hint = "Inspect residual_assets and failed_recoveries before editing."
        else:
            code = failure_code
            message = failure_message
            hint = (
                "Create a fresh plan before retrying."
                if not cancelled
                else "Inspect workflow.get before creating another plan."
            )
        tool_error = error_result(
            code=code,
            message=message,
            path="plan_id",
            hint=hint,
            details={
                "failed_recoveries": failed_recoveries,
                "residual_assets": sorted(residuals),
            },
        )
        return WorkflowResult(
            success=False,
            status=status,
            summary=message,
            plan_id=plan.id,
            data={
                "failed_recoveries": failed_recoveries,
                "residual_assets": sorted(residuals),
            },
            changes=changes,
            errors=[] if cancelled and recovery_complete else tool_error.errors,
            trace_id=tool_error.trace_id,
        )

    async def _committed_unreconciled(
        self,
        plan: WorkflowPlan,
        changes: list[ChangeRecord],
        verification: VerificationResult,
        commit: dict[str, Any],
        message: str,
    ) -> WorkflowResult:
        await self.store.update_runtime(
            plan.id,
            status=WorkflowStatus.NEEDS_ATTENTION,
            undo_token="",
            post_state_fingerprints={},
        )
        failure = error_result(
            code=ErrorCode.UE_UNAVAILABLE,
            message=message,
            path="plan_id",
            hint=(
                "The transaction was committed. Reconnect to Unreal and "
                "inspect the affected assets before continuing."
            ),
            details={"committed": True},
        )
        return WorkflowResult(
            success=False,
            status=WorkflowStatus.NEEDS_ATTENTION,
            summary=(
                "Workflow committed, but its post-state could not be captured."
            ),
            plan_id=plan.id,
            data={
                "workflow_id": plan.id,
                "committed": True,
                "transaction_recorded": bool(
                    commit.get("transaction_recorded")
                ),
                "undo_available": False,
            },
            changes=changes,
            warnings=verification.warnings,
            errors=failure.errors,
            trace_id=failure.trace_id,
        )

    @staticmethod
    def _timeout_recovery(response: dict[str, Any]) -> dict[str, Any] | None:
        if response.get("timed_out") is not True:
            return None
        return {
            "success": response.get("recovery_succeeded") is True,
            "message": response.get(
                "message", "Unreal workflow lease timed out."
            ),
            "outcome": response.get("recovery_outcome"),
        }

    async def _recover_after_task_cancellation(
        self,
        plan: WorkflowPlan,
        completed_steps: list,
        changes: list[ChangeRecord],
        has_successful_write: bool,
    ) -> WorkflowResult:
        return await self._recover(
            plan,
            completed_steps,
            changes,
            has_successful_write,
            cancelled=True,
        )

    async def undo(self, plan_id: str, undo_token: str) -> WorkflowResult:
        async with self._execution_lock:
            return await self._undo_locked(plan_id, undo_token)

    async def _undo_locked(
        self, plan_id: str, undo_token: str
    ) -> WorkflowResult:
        try:
            plan = await self.store.get(plan_id)
        except KeyError as exc:
            return self._error_result(
                plan_id,
                WorkflowStatus.FAILED_ROLLED_BACK,
                ErrorCode.INVALID_INPUT,
                str(exc),
                "Use a workflow_id returned by workflow.get.",
            )
        if plan.status not in {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.NEEDS_ATTENTION,
        } or not plan.undo_token:
            return self._error_result(
                plan.id,
                plan.status,
                ErrorCode.CONFIRMATION_REQUIRED,
                "Workflow has no available undo token.",
                "Apply a new undoable workflow before requesting undo.",
            )
        try:
            current = await self.backend.get_fingerprints(
                sorted(plan.post_state_fingerprints)
            )
        except Exception as exc:
            return self._error_result(
                plan.id,
                plan.status,
                ErrorCode.UE_UNAVAILABLE,
                str(exc),
                "Reconnect to Unreal Editor and retry the unused undo token.",
            )
        mismatches = [
            path
            for path, expected in plan.post_state_fingerprints.items()
            if AssetFingerprint.model_validate(current[path]).model_dump(
                mode="json"
            )
            != expected.model_dump(mode="json")
        ]
        if mismatches:
            return self._error_result(
                plan.id,
                plan.status,
                ErrorCode.PRECONDITION_FAILED,
                "Workflow post-state changed after apply.",
                "Create a new plan against the current editor state.",
                details={"mismatched_assets": sorted(mismatches)},
            )
        digest = self._fingerprint_digest(plan.post_state_fingerprints)
        try:
            self.tokens.consume_undo(undo_token, plan.id, digest)
        except (TokenValidationError, ValueError) as exc:
            code = (
                ErrorCode.CONFIRMATION_EXPIRED
                if getattr(exc, "reason", None) is TokenErrorReason.EXPIRED
                else ErrorCode.CONFIRMATION_REQUIRED
            )
            return self._error_result(
                plan.id,
                plan.status,
                code,
                str(exc),
                "Use the unused undo token returned by workflow.apply.",
            )
        await self.store.update_runtime(plan.id, undo_token="")
        try:
            response = await self.backend.undo_transaction(
                plan.transaction_id or plan.id
            )
        except Exception as exc:
            return self._error_result(
                plan.id,
                plan.status,
                ErrorCode.UE_UNAVAILABLE,
                str(exc),
                (
                    "The undo result is unknown. Inspect the Unreal undo "
                    "stack before continuing."
                ),
            )
        if not response.get("success", False):
            return self._error_result(
                plan.id,
                plan.status,
                ErrorCode.ROLLBACK_FAILED,
                response.get("message", "Unreal guarded undo was refused."),
                "Inspect the Unreal undo stack and workflow editor context.",
            )
        await self.store.update_runtime(
            plan.id,
            step_result={
                "step_id": "undo",
                "success": True,
                "response": response,
            },
        )
        return WorkflowResult(
            success=True,
            status=plan.status,
            summary="Workflow transaction was undone.",
            plan_id=plan.id,
            data={"undone": True},
            trace_id=uuid4().hex,
        )

    @staticmethod
    def _step_changes(
        plan: WorkflowPlan, step_id: str, response: dict[str, Any]
    ) -> list[ChangeRecord]:
        raw_changes = response.get("changes")
        if isinstance(raw_changes, list):
            try:
                return [ChangeRecord.model_validate(item) for item in raw_changes]
            except (TypeError, ValueError):
                pass
        return [
            change.model_copy(deep=True)
            for change in plan.predicted_changes
            if change.step_id == step_id
        ]

    @staticmethod
    def _fingerprint_digest(
        fingerprints: dict[str, AssetFingerprint]
    ) -> str:
        payload = {
            path: AssetFingerprint.model_validate(fingerprint).model_dump(
                mode="json"
            )
            for path, fingerprint in sorted(fingerprints.items())
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _error_result(
        plan_id: str,
        status: WorkflowStatus,
        code: ErrorCode,
        message: str,
        hint: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        result = error_result(
            code=code,
            message=message,
            path="plan_id",
            hint=hint,
            details=details,
        )
        return WorkflowResult(
            success=False,
            status=status,
            summary=result.summary,
            plan_id=plan_id,
            errors=result.errors,
            trace_id=result.trace_id,
        )
