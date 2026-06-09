import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

# A reliably-present engine AnimSequence we duplicate into /Game to edit safely.
_SRC_ANIM = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle"
_ANIM_NAME = "MCP_TestAnim"
_ANIM_PATH = f"{TEST_ROOT}/{_ANIM_NAME}"
# Engine skeletal mesh that ships with 7 sockets — used read-only for socket queries.
_TPP_MESH = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP"


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

    # ── skeletal mesh / socket queries (read-only engine assets) ─────────────────

    def test_get_skeletal_mesh_info(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("animation_actions", "ue_get_skeletal_mesh_info", asset_path=_TPP_MESH)
        self.assertSuccess(r)
        self.assertIsNotNone(r["skeleton"])
        self.assertGreater(r["num_sockets"], 0)

    def test_list_sockets(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("animation_actions", "ue_list_sockets", asset_path=_TPP_MESH)
        self.assertSuccess(r)
        self.assertEqual(r["num_sockets"], len(r["sockets"]))
        self.assertIn("bone", r["sockets"][0])

    def test_find_socket(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        listed = self.call("animation_actions", "ue_list_sockets", asset_path=_TPP_MESH)
        name = listed["sockets"][0]["name"]
        r = self.call("animation_actions", "ue_find_socket", asset_path=_TPP_MESH, socket_name=name)
        self.assertSuccess(r)
        self.assertEqual(r["name"], name)

    def test_find_socket_unknown(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("animation_actions", "ue_find_socket",
                      asset_path=_TPP_MESH, socket_name="NoSuchSocket_XYZ")
        self.assertFalse(r.get("success"))

    def test_get_skeleton_info(self):
        if not self._anim_path:
            self.skipTest("Test AnimSequence not available")
        skel_path = self.call("animation_actions", "ue_get_anim_sequence_info",
                              asset_path=self._anim_path)["skeleton"].split(".")[0]
        r = self.call("animation_actions", "ue_get_skeleton_info", asset_path=skel_path)
        self.assertSuccess(r)
        self.assertIn("curve_names", r)

    # ── bones + socket editing (C++ helper; needs the plugin built with these UFUNCTIONs) ──

    def test_list_bones(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("animation_actions", "ue_list_bones", asset_path=_TPP_MESH)
        self.assertSuccess(r)
        self.assertGreater(r["bone_count"], 0)
        self.assertIn("name", r["bones"][0])

    def test_add_and_remove_socket(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        dup = f"{TEST_ROOT}/MCP_TestSkelMesh"
        self.delete_asset(dup)
        mesh = unreal.EditorAssetLibrary.duplicate_asset(_TPP_MESH, dup)
        self.assertIsNotNone(mesh, "could not duplicate skeletal mesh")
        try:
            bone = self.call("animation_actions", "ue_list_bones", asset_path=dup)["bones"][0]["name"]
            r = self.call("animation_actions", "ue_add_socket", asset_path=dup,
                          socket_name="MCP_Socket", bone_name=bone, location=[0, 0, 10])
            self.assertSuccess(r)
            socks = self.call("animation_actions", "ue_list_sockets", asset_path=dup)
            self.assertIn("MCP_Socket", [s["name"] for s in socks["sockets"]])
            r = self.call("animation_actions", "ue_remove_socket", asset_path=dup, socket_name="MCP_Socket")
            self.assertSuccess(r)
            socks = self.call("animation_actions", "ue_list_sockets", asset_path=dup)
            self.assertNotIn("MCP_Socket", [s["name"] for s in socks["sockets"]])
        finally:
            self.delete_asset(dup)

    def test_add_socket_invalid_bone(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_TPP_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        dup = f"{TEST_ROOT}/MCP_TestSkelMesh2"
        self.delete_asset(dup)
        mesh = unreal.EditorAssetLibrary.duplicate_asset(_TPP_MESH, dup)
        self.assertIsNotNone(mesh)
        try:
            r = self.call("animation_actions", "ue_add_socket", asset_path=dup,
                          socket_name="MCP_Bad", bone_name="NoSuchBone_XYZ", location=[0, 0, 0])
            self.assertFalse(r.get("success"))
        finally:
            self.delete_asset(dup)
