"""Safety policy and dispatcher preflight tests."""

import pytest

from unreal_mcp.config import SafetyMode
from unreal_mcp.policy import DispatchDecision, SafetyPolicy
from unreal_mcp.registry import ActionRegistry


def test_compatible_mode_allows_legacy_delete():
    spec = ActionRegistry().get("asset", "delete_asset")
    assert (
        SafetyPolicy(SafetyMode.COMPATIBLE).decide(spec)
        is DispatchDecision.EXECUTE
    )


def test_strict_mode_requires_plan_for_write():
    spec = ActionRegistry().get("blueprint", "create_blueprint")
    assert (
        SafetyPolicy(SafetyMode.STRICT).decide(spec)
        is DispatchDecision.PLAN_REQUIRED
    )


def test_strict_mode_allows_read():
    spec = ActionRegistry().get("asset", "get_asset_info")
    assert SafetyPolicy(SafetyMode.STRICT).decide(spec) is DispatchDecision.EXECUTE


@pytest.mark.asyncio
async def test_strict_dispatch_returns_workflow_operation_without_tcp(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    calls = []

    async def record(*args):
        calls.append(args)
        return {"success": True}

    monkeypatch.setattr(dispatcher, "send_to_unreal", record)
    monkeypatch.setattr(dispatcher, "_policy", SafetyPolicy(SafetyMode.STRICT))
    result = await dispatcher._dispatch(
        "blueprint",
        "create_blueprint",
        {"asset_path": "/Game/BP_Test"},
    )
    assert result["errors"][0]["code"] == "CONFIRMATION_REQUIRED"
    assert result["errors"][0]["details"]["operation"] == {
        "id": "step-1",
        "domain": "blueprint",
        "action": "create_blueprint",
        "params": {"asset_path": "/Game/BP_Test"},
        "depends_on": [],
    }
    assert calls == []


@pytest.mark.asyncio
async def test_compatible_dispatch_preserves_backend_result(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    backend = {"success": False, "message": "legacy failure", "custom": 42}

    async def send(*args):
        return backend

    monkeypatch.setattr(dispatcher, "send_to_unreal", send)
    monkeypatch.setattr(
        dispatcher, "_policy", SafetyPolicy(SafetyMode.COMPATIBLE)
    )
    result = await dispatcher._dispatch(
        "blueprint", "create_blueprint", {"asset_path": "/Game/BP_Test"}
    )
    assert result is backend


@pytest.mark.asyncio
async def test_local_invalid_input_returns_stable_code(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    monkeypatch.setattr(
        dispatcher, "_policy", SafetyPolicy(SafetyMode.COMPATIBLE)
    )
    result = await dispatcher.util(action="execute_python", params={})
    assert result["errors"][0]["code"] == "INVALID_INPUT"
    assert result["errors"][0]["path"] == "params.code"


@pytest.mark.asyncio
async def test_known_missing_plugin_is_rejected_before_tcp(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    calls = []

    async def send(*args):
        calls.append(args)
        return {"success": True}

    monkeypatch.setattr(dispatcher, "send_to_unreal", send)
    monkeypatch.setattr(
        dispatcher,
        "_runtime_capabilities",
        {"ue_version": "5.6.0", "plugins": {"EnhancedInput": False}},
    )
    result = await dispatcher._dispatch(
        "game", "add_input_action", {"asset_path": "/Game/Input/IA_Test"}
    )
    assert result["errors"][0]["code"] == "PLUGIN_REQUIRED"
    assert calls == []


@pytest.mark.asyncio
async def test_known_unsupported_engine_version_is_rejected(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    monkeypatch.setattr(
        dispatcher,
        "_runtime_capabilities",
        {"ue_version": "5.5.4", "plugins": {}},
    )
    result = await dispatcher._dispatch(
        "asset", "get_asset_info", {"asset_path": "/Game/Test"}
    )
    assert result["errors"][0]["code"] == "UE_VERSION_UNSUPPORTED"


@pytest.mark.asyncio
async def test_local_exception_is_structured_and_hides_traceback(monkeypatch):
    import unreal_mcp.dispatcher as dispatcher

    async def explode(*args):
        raise RuntimeError("secret local failure")

    monkeypatch.setattr(dispatcher, "send_python_exec", explode)
    monkeypatch.setattr(
        dispatcher, "_policy", SafetyPolicy(SafetyMode.COMPATIBLE)
    )
    result = await dispatcher.util(
        action="execute_python", params={"code": "print('x')"}
    )
    assert result["errors"][0]["code"] == "INTERNAL_ERROR"
    serialized = str(result).lower()
    assert "traceback" not in serialized
    assert result["trace_id"] == result["errors"][0]["trace_id"]
