import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_SEQ_NAME = "MCP_TestSequence"
_SEQ_PATH = f"{TEST_ROOT}/{_SEQ_NAME}"
_CAM_CLASS = "/Script/CinematicCamera.CineCameraActor"


class TestLevelSequenceActions(MCPTestCase):

    def setUp(self):
        self._seq_path = None
        self.ensure_test_dir()
        self.delete_asset(_SEQ_PATH)
        r = self.call("level_sequence_actions", "ue_create_level_sequence",
                      asset_path=_SEQ_PATH, fps=30.0, duration_seconds=5.0)
        if r.get("success"):
            self._seq_path = _SEQ_PATH

    def tearDown(self):
        if self._seq_path:
            self.delete_asset(self._seq_path)

    def _skip_if_no_seq(self):
        if not self._seq_path:
            self.skipTest("Level Sequence not created in setUp")

    def _add_camera(self):
        r = self.call("level_sequence_actions", "ue_add_spawnable_from_class",
                      asset_path=self._seq_path, class_path=_CAM_CLASS)
        self.assertSuccess(r)
        return r["binding_name"]

    # ── create / info ───────────────────────────────────────────────────────────

    def test_create_level_sequence(self):
        self.assertIsNotNone(self._seq_path, "Sequence was not created in setUp")

    def test_get_sequence_info(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_get_sequence_info", asset_path=self._seq_path)
        self.assertSuccess(r)
        self.assertEqual(r["fps"], 30.0)
        self.assertAlmostEqual(r["playback_end_seconds"], 5.0, places=2)
        self.assertIsInstance(r["bindings"], list)

    def test_set_playback_range(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_set_playback_range",
                      asset_path=self._seq_path, start_seconds=1.0, end_seconds=8.0)
        self.assertSuccess(r)
        info = self.call("level_sequence_actions", "ue_get_sequence_info", asset_path=self._seq_path)
        self.assertAlmostEqual(info["playback_end_seconds"], 8.0, places=2)

    # ── bindings ─────────────────────────────────────────────────────────────────

    def test_add_spawnable_from_class(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        info = self.call("level_sequence_actions", "ue_get_sequence_info", asset_path=self._seq_path)
        names = [b["name"] for b in info["bindings"]]
        self.assertIn(name, names)

    def test_add_possessable(self):
        self._skip_if_no_seq()
        spawn = self.call("actor_actions", "ue_spawn_from_class",
                          class_path="/Script/Engine.PointLight", location=[0, 0, 400])
        self.assertSuccess(spawn)
        label = spawn["actor_label"]
        try:
            r = self.call("level_sequence_actions", "ue_add_possessable",
                          asset_path=self._seq_path, actor_label=label)
            self.assertSuccess(r)
        finally:
            self.delete_actor_by_label(label)

    def test_remove_binding(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        r = self.call("level_sequence_actions", "ue_remove_binding",
                      asset_path=self._seq_path, binding_name=name)
        self.assertSuccess(r)
        self.assertNotIn(name, r["remaining_bindings"])

    def test_remove_binding_unknown(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_remove_binding",
                      asset_path=self._seq_path, binding_name="NoSuchBinding_XYZ")
        self.assertFalse(r.get("success"))

    # ── tracks / keyframes ───────────────────────────────────────────────────────

    def test_add_transform_track(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        r = self.call("level_sequence_actions", "ue_add_transform_track",
                      asset_path=self._seq_path, binding_name=name)
        self.assertSuccess(r)

    def test_add_transform_keyframe(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        r = self.call("level_sequence_actions", "ue_add_transform_keyframe",
                      asset_path=self._seq_path, binding_name=name, time_seconds=2.0,
                      location=[100.0, 200.0, 300.0], rotation=[0.0, 45.0, 0.0])
        self.assertSuccess(r)
        self.assertIn("location", r["keyed"])
        self.assertIn("rotation", r["keyed"])
        # The section must span the keyed time, or the keys are invisible in Sequencer.
        start, end = r["section_range_seconds"]
        self.assertGreater(end, start)
        self.assertGreaterEqual(end, 2.0)

    def test_keyframe_beyond_range_extends_section(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        # Key past the 5s playback end → section must extend to include it.
        r = self.call("level_sequence_actions", "ue_add_transform_keyframe",
                      asset_path=self._seq_path, binding_name=name, time_seconds=8.0,
                      location=[0.0, 0.0, 0.0])
        self.assertSuccess(r)
        self.assertGreaterEqual(r["section_range_seconds"][1], 8.0)

    def test_add_transform_keyframe_no_channels(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        r = self.call("level_sequence_actions", "ue_add_transform_keyframe",
                      asset_path=self._seq_path, binding_name=name, time_seconds=1.0)
        self.assertFalse(r.get("success"))

    # ── camera / anim / sequencer editor ─────────────────────────────────────────

    def test_add_camera_with_cut_track(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_add_camera",
                      asset_path=self._seq_path, spawnable=True)
        self.assertSuccess(r)
        self.assertTrue(r["camera_binding"])
        self.assertTrue(r["camera_cut_track"])
        info = self.call("level_sequence_actions", "ue_get_sequence_info", asset_path=self._seq_path)
        self.assertIn(r["camera_binding"], [b["name"] for b in info["bindings"]])

    def test_add_anim_track(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_add_spawnable_from_class",
                      asset_path=self._seq_path, class_path="/Script/Engine.SkeletalMeshActor")
        self.assertSuccess(r)
        name = r["binding_name"]
        r = self.call("level_sequence_actions", "ue_add_anim_track",
                      asset_path=self._seq_path, binding_name=name,
                      anim_path="/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle")
        self.assertSuccess(r)
        self.assertEqual(len(r["range_seconds"]), 2)

    def test_add_anim_track_bad_anim(self):
        self._skip_if_no_seq()
        name = self._add_camera()
        r = self.call("level_sequence_actions", "ue_add_anim_track",
                      asset_path=self._seq_path, binding_name=name,
                      anim_path="/Engine/BasicShapes/Cube")
        self.assertFalse(r.get("success"))

    def test_open_and_close_sequencer(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_open_in_sequencer", asset_path=self._seq_path)
        self.assertSuccess(r)
        r = self.call("level_sequence_actions", "ue_close_sequencer")
        self.assertSuccess(r)

    def test_convert_binding_to_spawnable(self):
        self._skip_if_no_seq()
        spawn = self.call("actor_actions", "ue_spawn_from_class",
                          class_path="/Script/Engine.PointLight", location=[0, 0, 450])
        self.assertSuccess(spawn)
        label = spawn["actor_label"]
        try:
            r = self.call("level_sequence_actions", "ue_add_possessable",
                          asset_path=self._seq_path, actor_label=label)
            self.assertSuccess(r)
            r = self.call("level_sequence_actions", "ue_convert_binding",
                          asset_path=self._seq_path, binding_name=r["binding_name"], to="spawnable")
            self.assertSuccess(r)
            self.assertTrue(r["bindings"])
        finally:
            self.delete_actor_by_label(label)

    def test_convert_binding_bad_mode(self):
        self._skip_if_no_seq()
        r = self.call("level_sequence_actions", "ue_convert_binding",
                      asset_path=self._seq_path, binding_name="X", to="nonsense")
        self.assertFalse(r.get("success"))
