# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
End-to-end tests: MCP server dispatcher -> real TCP -> C++ server -> ue_* -> back.

Unlike test_dispatcher.py (which mocks the TCP layer), these run the FULL chain
with NO mocks. They prove the actual scenario an MCP client triggers:
routing + socket round-trip + C++ dispatch + response unwrapping.

Requires a running Unreal editor with the UnrealMCPython TCP server on :12029.
If the port is not reachable, the whole module is skipped (so CI / offline runs
stay green; run locally with the editor open to exercise these).

Run:
    cd mcp-server && uv run --extra dev pytest tests/test_e2e.py -v
"""

import asyncio
import socket

import pytest

import unreal_mcp.dispatcher as disp
from unreal_mcp.dispatchers._catalog import CATALOG

HOST, PORT = "127.0.0.1", 12029

# Actions excluded from the exhaustive empty-param round-trip:
#   execute_python   — needs {code}; empty-param hits a dispatcher guard, not TCP
#   livecoding_compile — triggers a real C++ compile (slow, side-effecting)
#   start_pie/stop_pie — change editor PIE mode (no params to guard); would leave
#                        the editor in PIE during the sweep
_EXCLUDE = {
    ("util", "execute_python"),
    ("util", "livecoding_compile"),
    ("util", "start_pie"),
    ("util", "stop_pie"),
    # save_current_level can raise a modal Save-As dialog on an untitled level.
    ("level", "save_current_level"),
    ("level", "save_all_levels"),
    # vision returns an MCP Image (not a dict) — covered by a dedicated E2E test below.
    ("vision", "capture_viewport"),
}


def _editor_reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _editor_reachable(),
    reason=f"Unreal TCP server not reachable on {HOST}:{PORT} (open the editor to run E2E).",
)

# Editor-crash guard: if the editor was up when the module started but dies
# mid-suite, every remaining test must FAIL (not skip, and not "pass" via a
# connection-error dict that happens to carry a 'success' key). A green E2E run
# must mean the editor survived the whole sweep — otherwise a `pytest && ...`
# release chain would happily commit/PR on top of a crash.
_EDITOR_WAS_UP = _editor_reachable()
_CONNECTION_ERROR_MARKERS = ("Connection refused", "ConnectionReset", "Socket timeout",
                             "No response received", "[WinError")


@pytest.fixture(autouse=True)
def _fail_if_editor_crashed():
    if _EDITOR_WAS_UP and not _editor_reachable():
        pytest.fail(f"Unreal editor crashed during the E2E suite "
                    f"({HOST}:{PORT} no longer reachable). Investigate before merging.")
    yield


def _assert_not_connection_error(r, label):
    if isinstance(r, dict):
        msg = str(r.get("message", ""))
        assert not any(m in msg for m in _CONNECTION_ERROR_MARKERS), \
            f"{label}: editor connection lost mid-call: {msg}"


def run(coro):
    return asyncio.run(coro)


def test_list_actors_round_trip():
    """A read action proves unwrapping: 'actors' is an INNER field of the action result."""
    r = run(disp._dispatch("actor", "list_all_with_locations", {}))
    assert r.get("success") is True
    assert "actors" in r, f"inner field missing — response not unwrapped: {r}"
    assert isinstance(r["actors"], list)


def test_spawn_and_delete_round_trip():
    spawn = run(disp._dispatch("actor", "spawn_from_class",
                               {"class_path": "/Script/Engine.PointLight",
                                "location": [0, 0, 700]}))
    assert spawn.get("success") is True, spawn
    label = spawn.get("actor_label")
    assert label, f"actor_label missing — not unwrapped: {spawn}"
    # cleanup through the same chain
    deleted = run(disp._dispatch("actor", "delete_by_label", {"actor_label": label}))
    assert deleted.get("success") is True, deleted


def test_inner_action_failure_is_surfaced():
    """Action failure must come back as success=False (not buried in a result string)."""
    r = run(disp._dispatch("actor", "set_transform",
                           {"actor_label": "NoSuchActor_E2E_XYZ", "location": [0, 0, 0]}))
    assert r.get("success") is False
    assert "message" in r


def test_list_actions_offline_path_still_works():
    """list_actions must not touch TCP even when the editor is up."""
    r = run(disp._dispatch("material", "list_actions", {}))
    assert r["success"] is True
    assert r["domain"] == "material"


def test_execute_python_round_trip():
    """execute_python runs real Unreal Python through the chain."""
    r = run(disp.util.fn(action="execute_python",
                         params={"code": "print('e2e_marker_42')"}))
    # send_python_exec returns the raw wrapper; the printed marker is in 'result'.
    blob = r.get("result", "") + r.get("message", "")
    assert "e2e_marker_42" in blob, f"execute_python did not echo marker: {r}"


def test_vision_capture_returns_image():
    """vision capture_viewport returns an MCP Image (PNG) through the full chain."""
    from fastmcp import Image
    r = run(disp.vision.fn(action="capture_viewport", params={"width": 320, "height": 180}))
    assert isinstance(r, Image), f"expected an Image, got {type(r).__name__}: {r}"
    # the PNG bytes should carry a valid signature
    data = getattr(r, "data", b"")
    assert data[:4] == b"\x89PNG", "capture did not return a PNG"


def test_gltf_import_round_trip():
    """glTF import via the deferred-tick path: export the engine Cube to .glb, import it,
    then poll get_gltf_import_status until done. Each dispatch is its own game-thread task,
    so the editor ticks between calls and the Interchange async import can run + complete."""
    import time

    # 1. export /Engine/BasicShapes/Cube to a temp .glb (via execute_python)
    export_code = (
        "import unreal, os\n"
        "glb = os.path.join(unreal.Paths.project_saved_dir(), 'MCP_E2E_gltf.glb').replace(chr(92), '/')\n"
        "cube = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube')\n"
        "t = unreal.AssetExportTask(); t.object = cube; t.filename = glb\n"
        "t.automated = True; t.replace_identical = True; t.prompt = False\n"
        "ok = unreal.Exporter.run_asset_export_task(t)\n"
        "print('GLBPATH=' + glb if (ok and os.path.isfile(glb)) else 'GLBFAIL')\n"
    )
    r = run(disp.util.fn(action="execute_python", params={"code": export_code}))
    blob = (r.get("result", "") or "") + (r.get("message", "") or "")
    assert "GLBPATH=" in blob, f"glb export failed: {blob[:300]}"
    glb = blob.split("GLBPATH=", 1)[1].split()[0].strip().strip('"')

    dest = "/Game/Tests/MCP_E2E/glb"
    try:
        imp = run(disp._dispatch("asset", "import_gltf",
                                 {"file_path": glb, "destination_path": dest}))
        assert imp.get("success") and imp.get("pending"), f"schedule failed: {imp}"

        st = {}
        for _ in range(40):  # ~20s budget for the async Interchange import
            st = run(disp._dispatch("asset", "get_gltf_import_status",
                                    {"destination_path": dest}))
            _assert_not_connection_error(st, "get_gltf_import_status")
            if st.get("done"):
                break
            time.sleep(0.5)
        assert st.get("success") and st.get("done"), f"import did not complete: {st}"
        classes = [a["class"] for a in st["imported_assets"]]
        assert "StaticMesh" in classes, f"no StaticMesh among imported: {st}"
    finally:
        run(disp.util.fn(action="execute_python", params={
            "code": f"import unreal; unreal.EditorAssetLibrary.delete_directory('{dest}')"}))


# ── exhaustive: every catalog action survives the full chain ───────────────────

def _all_action_pairs():
    pairs = []
    for domain, actions in CATALOG.items():
        for action in actions:
            if (domain, action) in _EXCLUDE:
                continue
            pairs.append((domain, action))
    return pairs


@pytest.mark.parametrize("domain,action", _all_action_pairs())
def test_every_action_round_trips(domain, action):
    """
    Drive every action through the real chain with empty params and assert we get
    back an unwrapped dict containing 'success'. This proves routing + TCP +
    C++ dispatch + result unwrapping work for the action — independent of whether
    the action *succeeds* with no args (validation failures still return a dict).

    Empty params are safe: execute_action wraps any exception (incl. missing-arg
    TypeError) as {"success": false, ...}, and ue_* functions validate required
    params before doing work.
    """
    if domain == "util":
        r = run(disp.util.fn(action=action, params={}))
    elif domain == "vision":
        r = run(disp.vision.fn(action=action, params={}))
    else:
        r = run(disp._dispatch(domain, action, {}))
    assert isinstance(r, dict), f"{domain}.{action} returned non-dict: {r!r}"
    assert "success" in r, f"chain/unwrap failed for {domain}.{action}: {r!r}"
    _assert_not_connection_error(r, f"{domain}.{action}")


def test_zzz_editor_survived_suite():
    """Last test in the file: the editor must still be alive after the full sweep."""
    assert _editor_reachable(), "Unreal editor is no longer reachable after the E2E suite (it crashed mid-run)."
