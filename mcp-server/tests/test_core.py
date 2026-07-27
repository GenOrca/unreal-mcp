# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Unit tests for the TCP response unwrapping (offline, no Unreal)."""

import asyncio
import threading

import pytest

import unreal_mcp.core as core
from unreal_mcp.core import _unwrap_result


class _DelayedSocket:
    def __init__(self, release):
        self._release = release
        self._responses = [
            b'{"success":true,"result":"{\\"success\\":true}"}',
            b"",
        ]

    def __enter__(self):
        self._release.wait(timeout=1)
        return self

    def __exit__(self, *args):
        return False

    def sendall(self, _value):
        return None

    def recv(self, _size):
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_send_to_unreal_does_not_block_the_event_loop(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(
        core.socket,
        "create_connection",
        lambda *_args, **_kwargs: _DelayedSocket(release),
    )
    timer = threading.Timer(0.3, release.set)
    timer.start()
    loop = asyncio.get_running_loop()
    started = loop.time()
    call = asyncio.create_task(core.send_to_unreal("module", "action", {}))
    try:
        await asyncio.sleep(0.01)
        elapsed = loop.time() - started
        release.set()
        assert await call == {"success": True}
        assert elapsed < 0.1
    finally:
        release.set()
        timer.cancel()


def test_unwraps_action_dict_from_result_string():
    wire = {
        "success": True,  # python-exec success, NOT action success
        "message": "Python command executed successfully.",
        "result": '{"success": true, "actor_label": "PointLight_2"}',
    }
    out = _unwrap_result(wire)
    assert out == {"success": True, "actor_label": "PointLight_2"}


def test_unwrapped_inner_failure_is_surfaced():
    """Action failure (inner success=False) must survive unwrapping as data."""
    wire = {
        "success": True,  # python ran fine...
        "result": '{"success": false, "message": "Actor not found"}',
    }
    out = _unwrap_result(wire)
    assert out["success"] is False
    assert out["message"] == "Actor not found"


def test_unwraps_list_result():
    wire = {"success": True, "result": '[1, 2, 3]'}
    assert _unwrap_result(wire) == [1, 2, 3]


def test_non_json_result_returns_original():
    wire = {"success": True, "result": "not json at all"}
    assert _unwrap_result(wire) == wire


def test_missing_result_returns_original():
    wire = {"success": True, "message": "ok"}
    assert _unwrap_result(wire) == wire


def test_non_dict_passthrough():
    assert _unwrap_result("raw") == "raw"
