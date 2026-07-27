"""Tests for registry contracts and stable structured errors."""

import pytest

from unreal_mcp.contracts import ActionSpec, Effect, ResultKind, Risk
from unreal_mcp.errors import error_result


def test_action_spec_rejects_destructive_without_confirmation():
    with pytest.raises(ValueError):
        ActionSpec(
            domain="asset",
            action="delete_asset",
            title="Delete asset",
            description="Delete one asset.",
            result_kind=ResultKind.JSON,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            effect=Effect.DESTRUCTIVE,
            risk=Risk.HIGH,
            idempotent=False,
            supports_preview=True,
            supports_undo=False,
            requires_confirmation=False,
            ue_versions=["5.6", "5.7", "5.8"],
        )


def test_error_result_is_actionable_and_sanitized():
    result = error_result(
        code="INVALID_INPUT",
        message="asset_path is required",
        path="params.asset_path",
        retryable=True,
        hint="Call describe_action for blueprint.create_blueprint.",
        details={"traceback": "secret stack", "received": None},
    )
    assert result.success is False
    assert result.errors[0].code == "INVALID_INPUT"
    assert result.errors[0].details == {"received": None}
    assert "secret stack" not in result.model_dump_json()
