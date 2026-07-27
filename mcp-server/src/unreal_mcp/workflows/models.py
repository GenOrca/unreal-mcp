"""Shared workflow plan, step, state, and result contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from unreal_mcp.config import SafetyMode
from unreal_mcp.contracts import Effect, ErrorDetail, Risk


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


class VerificationResult(BaseModel):
    success: bool = True
    summary: str = "Verification passed."
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class WorkflowPlan(BaseModel):
    id: str
    status: WorkflowStatus
    safety_mode: SafetyMode
    project_id: str
    editor_session_id: str
    current_map: str
    allow_non_undoable: bool = False
    steps: list[PlanStep] = Field(default_factory=list)
    asset_fingerprints: dict[str, AssetFingerprint] = Field(default_factory=dict)
    predicted_changes: list[ChangeRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confirmation_token: str | None = None
    undo_token: str | None = None
    transaction_id: str | None = None
    post_state_fingerprints: dict[str, AssetFingerprint] = Field(
        default_factory=dict
    )
    residual_fingerprints: dict[str, AssetFingerprint] = Field(
        default_factory=dict
    )
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
                "status",
                "created_at",
                "confirmation_token",
                "undo_token",
                "transaction_id",
                "post_state_fingerprints",
                "residual_fingerprints",
                "step_results",
            },
        )
        payload = json.dumps(signed, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()


class WorkflowResult(BaseModel):
    success: bool
    status: WorkflowStatus
    summary: str
    plan_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    changes: list[ChangeRecord] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str
