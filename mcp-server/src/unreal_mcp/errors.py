"""Stable structured error construction with detail sanitization."""

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
