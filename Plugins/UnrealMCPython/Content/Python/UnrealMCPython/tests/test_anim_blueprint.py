import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

# Engine assets that ship with the editor: a Skeleton to bind, and a SkeletalMesh
# used as a deliberately-wrong (non-Skeleton) asset for the type-guard test.
_SKELETON = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP_Skeleton"
_NON_SKELETON = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP"
# Two AnimSequences that ship on the TutorialTPP skeleton — used for the AnimGraph builders.
_IDLE_ANIM = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle"
_WALK_ANIM = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Walk_Fwd"
_ABP_PATH = f"{TEST_ROOT}/MCP_TestAnimBP"


class TestAnimBlueprintActions(MCPTestCase):

    def setUp(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_SKELETON):
            self.skipTest("Engine TutorialTPP_Skeleton not available")
        self.ensure_test_dir()
        self.delete_asset(_ABP_PATH)

    def tearDown(self):
        self.delete_asset(_ABP_PATH)

    # ── create + introspection happy path ─────────────────────────────────────────

    def test_create_binds_skeleton_and_info_reports_it(self):
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=_SKELETON)
        self.assertSuccess(r)
        self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(_ABP_PATH))

        info = self.call("anim_blueprint_actions", "ue_get_anim_blueprint_info", asset_path=_ABP_PATH)
        self.assertSuccess(info)
        # the skeleton must actually be bound (the whole point of an AnimBlueprint)
        self.assertEqual(info["target_skeleton"].split(".")[0], _SKELETON)
        # an AnimBlueprint always owns both an AnimGraph and an EventGraph
        self.assertIn("AnimGraph", info["graphs"])
        self.assertIn("EventGraph", info["graphs"])
        self.assertTrue(info["generated_class"].endswith("_C"))

    def test_create_with_custom_anim_instance_parent(self):
        # AnimInstance itself is a valid explicit parent; proves parent validation accepts it.
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=_SKELETON,
                      parent_class_path="/Script/Engine.AnimInstance")
        self.assertSuccess(r)
        self.assertEqual(r["parent_class"], "/Script/Engine.AnimInstance")

    # ── create guards (each a distinct failure mode) ──────────────────────────────

    def test_create_requires_skeleton_param(self):
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint", asset_path=_ABP_PATH)
        self.assertFalse(r.get("success"))

    def test_create_rejects_missing_skeleton_asset(self):
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=f"{TEST_ROOT}/NoSuchSkeleton_XYZ")
        self.assertFalse(r.get("success"))

    def test_create_rejects_non_skeleton_asset(self):
        # pointing skeleton_path at a SkeletalMesh must be caught by the type guard,
        # not silently accepted (which would produce a broken AnimBlueprint).
        if not unreal.EditorAssetLibrary.does_asset_exist(_NON_SKELETON):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=_NON_SKELETON)
        self.assertFalse(r.get("success"))
        self.assertIn("Skeleton", r.get("message", ""))

    def test_create_rejects_non_anim_instance_parent(self):
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=_SKELETON,
                      parent_class_path="/Script/Engine.Actor")
        self.assertFalse(r.get("success"))
        self.assertIn("AnimInstance", r.get("message", ""))

    def test_create_rejects_duplicate(self):
        first = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                          asset_path=_ABP_PATH, skeleton_path=_SKELETON)
        self.assertSuccess(first)
        again = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                          asset_path=_ABP_PATH, skeleton_path=_SKELETON)
        self.assertFalse(again.get("success"))
        self.assertIn("already exists", again.get("message", ""))

    # ── info guards ───────────────────────────────────────────────────────────────

    def test_info_requires_asset_path(self):
        r = self.call("anim_blueprint_actions", "ue_get_anim_blueprint_info")
        self.assertFalse(r.get("success"))

    def test_info_rejects_non_anim_blueprint(self):
        # the Skeleton asset exists but is not an AnimBlueprint — type guard must reject it.
        r = self.call("anim_blueprint_actions", "ue_get_anim_blueprint_info", asset_path=_SKELETON)
        self.assertFalse(r.get("success"))
        self.assertIn("AnimBlueprint", r.get("message", ""))

    # ── AnimGraph node authoring (C++ helper) ─────────────────────────────────────

    def _make_abp(self):
        r = self.call("anim_blueprint_actions", "ue_create_anim_blueprint",
                      asset_path=_ABP_PATH, skeleton_path=_SKELETON)
        self.assertSuccess(r)

    def _anim_graph_node_classes(self):
        info = self.call("blueprint_actions", "ue_get_blueprint_graph_info",
                         asset_path=_ABP_PATH, graph_name="AnimGraph")
        self.assertSuccess(info)
        return [n["node_class"] for n in info["nodes"]]

    def test_add_sequence_player_links_to_output(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_IDLE_ANIM):
            self.skipTest("Engine Tutorial_Idle anim not available")
        self._make_abp()
        r = self.call("anim_blueprint_actions", "ue_add_anim_graph_sequence_player",
                      asset_path=_ABP_PATH, anim_sequence_path=_IDLE_ANIM, link_to_output_pose=True)
        self.assertSuccess(r)
        self.assertTrue(r["linked_to_output"])
        # the node must actually exist in the AnimGraph
        self.assertIn("AnimGraphNode_SequencePlayer", self._anim_graph_node_classes())

    def test_add_sequence_player_rejects_missing_anim(self):
        self._make_abp()
        r = self.call("anim_blueprint_actions", "ue_add_anim_graph_sequence_player",
                      asset_path=_ABP_PATH, anim_sequence_path=f"{TEST_ROOT}/NoSuchAnim_XYZ")
        self.assertFalse(r.get("success"))

    # ── generic spec-driven state machine ─────────────────────────────────────────

    def test_build_generic_three_state_machine(self):
        for a in (_IDLE_ANIM, _WALK_ANIM):
            if not unreal.EditorAssetLibrary.does_asset_exist(a):
                self.skipTest("Engine tutorial locomotion anims not available")
        self._make_abp()
        spec = {
            "machine_name": "Locomotion", "entry": "Idle",
            "states": [
                {"name": "Idle", "anim": _IDLE_ANIM},
                {"name": "Walk", "anim": _WALK_ANIM},
                {"name": "Run",  "anim": _WALK_ANIM},
            ],
            "transitions": [
                {"from": "Idle", "to": "Walk", "var": "Speed", "op": ">", "value": 10},
                {"from": "Walk", "to": "Idle", "var": "Speed", "op": "<", "value": 10},
                {"from": "Walk", "to": "Run",  "var": "Speed", "op": ">", "value": 300},
                {"from": "Run",  "to": "Walk", "var": "Speed", "op": "<", "value": 300},
            ],
        }
        r = self.call("anim_blueprint_actions", "ue_build_anim_state_machine",
                      asset_path=_ABP_PATH, spec=spec)
        self.assertSuccess(r)
        self.assertEqual(r["states"], ["Idle", "Walk", "Run"])
        self.assertEqual(r["transition_count"], 4)
        self.assertEqual(r.get("warnings", []), [])  # all 4 speed rules wired, no fallbacks
        self.assertIn("AnimGraphNode_StateMachine", self._anim_graph_node_classes())

    def test_build_generic_rejects_unknown_transition_state(self):
        self._make_abp()
        spec = {"states": [{"name": "A", "anim": _IDLE_ANIM}],
                "transitions": [{"from": "A", "to": "DoesNotExist"}]}
        r = self.call("anim_blueprint_actions", "ue_build_anim_state_machine",
                      asset_path=_ABP_PATH, spec=spec)
        self.assertFalse(r.get("success"))

    def test_build_generic_rejects_empty_states(self):
        self._make_abp()
        r = self.call("anim_blueprint_actions", "ue_build_anim_state_machine",
                      asset_path=_ABP_PATH, spec={"states": []})
        self.assertFalse(r.get("success"))

    def test_build_generic_rejects_missing_anim(self):
        self._make_abp()
        r = self.call("anim_blueprint_actions", "ue_build_anim_state_machine",
                      asset_path=_ABP_PATH,
                      spec={"states": [{"name": "Idle", "anim": f"{TEST_ROOT}/NoSuchAnim_XYZ"}]})
        self.assertFalse(r.get("success"))
