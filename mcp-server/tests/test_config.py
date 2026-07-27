"""Tests for MCP server startup settings."""

import pytest

from unreal_mcp.config import SafetyMode, load_settings


def test_settings_default_compatible_and_accept_strict():
    assert load_settings({}).safety_mode is SafetyMode.COMPATIBLE
    assert (
        load_settings({"UNREAL_MCP_SAFETY_MODE": "strict"}).safety_mode
        is SafetyMode.STRICT
    )


def test_settings_reject_unknown_mode():
    with pytest.raises(ValueError, match="UNREAL_MCP_SAFETY_MODE"):
        load_settings({"UNREAL_MCP_SAFETY_MODE": "unsafe"})
