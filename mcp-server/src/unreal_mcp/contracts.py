"""Shared public contracts for action metadata and tool results."""

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
