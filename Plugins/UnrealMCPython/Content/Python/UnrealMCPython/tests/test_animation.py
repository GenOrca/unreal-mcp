import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

# A reliably-present engine AnimSequence we duplicate into /Game to edit safely.
_SRC_ANIM = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle"
_ANIM_NAME = "MCP_TestAnim"
_ANIM_PATH = f"{TEST_ROOT}/{_ANIM_NAME}"


class TestAnimationActions(MCPTestCase):

    def setUp(self):
        self._anim_path = None
        self.ensure_test_dir()
        self.delete_asset(_ANIM_PATH)
        if unreal.EditorAssetLibrary.does_asset_exist(_SRC_ANIM):
            seq = unreal.EditorAssetLibrary.duplicate_asset(_SRC_ANIM, _ANIM_PATH)
            if seq:
                self._anim_path = _ANIM_PATH

    def tearDown(self):
        if self._anim_path:
            self.delete_asset(self._anim_path)

    def _skip_if_no_anim(self):
        if not self._anim_path:
            self.skipTest("Test AnimSequence not available (engine source missing)")

    # ── introspection ───────────────────────────────────────────────────────────

    def test_get_anim_sequence_info(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_get_anim_sequence_info", asset_path=self._anim_path)
        self.assertSuccess(r)
        self.assertGreater(r["num_frames"], 0)
        self.assertGreater(r["length_seconds"], 0)
        self.assertIsNotNone(r["skeleton"])

    def test_list_notify_tracks(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_list_notify_tracks", asset_path=self._anim_path)
        self.assertSuccess(r)
        self.assertIsInstance(r["tracks"], list)

    def test_list_notifies(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_list_notifies", asset_path=self._anim_path)
        self.assertSuccess(r)
        self.assertIsInstance(r["notifies"], list)

    def test_list_curves(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_list_curves", asset_path=self._anim_path)
        self.assertSuccess(r)
        self.assertIsInstance(r["curves"], list)

    def test_list_sync_markers(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_list_sync_markers", asset_path=self._anim_path)
        self.assertSuccess(r)
        self.assertIsInstance(r["sync_markers"], list)

    # ── notify tracks ────────────────────────────────────────────────────────────

    def test_add_and_remove_notify_track(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_add_notify_track",
                      asset_path=self._anim_path, track_name="MCP_Track")
        self.assertSuccess(r)
        self.assertIn("MCP_Track", r["tracks"])
        r = self.call("animation_actions", "ue_remove_notify_track",
                      asset_path=self._anim_path, track_name="MCP_Track")
        self.assertSuccess(r)
        self.assertNotIn("MCP_Track", r["tracks"])

    def test_remove_notify_track_unknown(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_remove_notify_track",
                      asset_path=self._anim_path, track_name="NoSuchTrack_XYZ")
        self.assertFalse(r.get("success"))

    # ── sync markers ─────────────────────────────────────────────────────────────

    def test_add_sync_marker(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_add_sync_marker",
                      asset_path=self._anim_path, track_name="MCP_SyncTrack",
                      marker_name="MCP_Marker", time_seconds=0.5)
        self.assertSuccess(r)
        markers = self.call("animation_actions", "ue_list_sync_markers", asset_path=self._anim_path)
        names = [m["name"] for m in markers["sync_markers"]]
        self.assertIn("MCP_Marker", names)

    # ── curves ───────────────────────────────────────────────────────────────────

    def test_add_and_remove_float_curve(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_add_float_curve",
                      asset_path=self._anim_path, curve_name="MCP_Curve",
                      time_seconds=0.0, value=1.0)
        self.assertSuccess(r)
        self.assertIn("MCP_Curve", r["curves"])
        r = self.call("animation_actions", "ue_remove_curve",
                      asset_path=self._anim_path, curve_name="MCP_Curve")
        self.assertSuccess(r)
        self.assertNotIn("MCP_Curve", r["curves"])

    def test_remove_curve_unknown(self):
        self._skip_if_no_anim()
        r = self.call("animation_actions", "ue_remove_curve",
                      asset_path=self._anim_path, curve_name="NoSuchCurve_XYZ")
        self.assertFalse(r.get("success"))
