import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_MESH = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP"
_CR_PATH = f"{TEST_ROOT}/MCP_TestCR"


class TestControlRigActions(MCPTestCase):

    def setUp(self):
        if not hasattr(unreal, "ControlRigBlueprint"):
            self.skipTest("ControlRig plugin not enabled")
        self.ensure_test_dir()
        self.delete_asset(_CR_PATH)

    def tearDown(self):
        self.delete_asset(_CR_PATH)

    def test_create_empty_and_info(self):
        r = self.call("control_rig_actions", "ue_create_control_rig", asset_path=_CR_PATH)
        self.assertSuccess(r)
        r = self.call("control_rig_actions", "ue_get_control_rig_info", asset_path=_CR_PATH)
        self.assertSuccess(r)
        self.assertIn("element_counts", r)

    def test_create_from_mesh_imports_bones(self):
        if not unreal.EditorAssetLibrary.does_asset_exist(_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        r = self.call("control_rig_actions", "ue_create_control_rig",
                      asset_path=_CR_PATH, skeletal_mesh_path=_MESH)
        self.assertSuccess(r)
        self.assertGreater(r["imported_bones"], 0)
        info = self.call("control_rig_actions", "ue_get_control_rig_info", asset_path=_CR_PATH)
        self.assertGreater(info["element_counts"].get("BONE", 0), 0)
        self.assertIsNotNone(info["preview_mesh"])

    def test_add_bone_and_null(self):
        self.call("control_rig_actions", "ue_create_control_rig", asset_path=_CR_PATH)
        r = self.call("control_rig_actions", "ue_add_rig_bone",
                      asset_path=_CR_PATH, bone_name="RootBone", location=[0, 0, 10])
        self.assertSuccess(r)
        r = self.call("control_rig_actions", "ue_add_rig_bone",
                      asset_path=_CR_PATH, bone_name="ChildBone",
                      parent_name="RootBone", parent_type="bone")
        self.assertSuccess(r)
        r = self.call("control_rig_actions", "ue_add_rig_null",
                      asset_path=_CR_PATH, null_name="GroupNull")
        self.assertSuccess(r)
        info = self.call("control_rig_actions", "ue_get_control_rig_info", asset_path=_CR_PATH)
        self.assertEqual(info["element_counts"].get("BONE"), 2)
        self.assertEqual(info["element_counts"].get("NULL"), 1)

    def test_add_unit_node_and_recompile(self):
        self.call("control_rig_actions", "ue_create_control_rig", asset_path=_CR_PATH)
        r = self.call("control_rig_actions", "ue_add_unit_node",
                      asset_path=_CR_PATH, struct_path="/Script/ControlRig.RigUnit_GetTransform")
        self.assertSuccess(r)
        self.assertTrue(r["node"])
        r = self.call("control_rig_actions", "ue_recompile_control_rig", asset_path=_CR_PATH)
        self.assertSuccess(r)

    def test_add_unit_node_bad_struct(self):
        self.call("control_rig_actions", "ue_create_control_rig", asset_path=_CR_PATH)
        r = self.call("control_rig_actions", "ue_add_unit_node",
                      asset_path=_CR_PATH, struct_path="/Script/ControlRig.RigUnit_NopeXYZ")
        self.assertFalse(r.get("success"))

    def test_bad_parent_type(self):
        self.call("control_rig_actions", "ue_create_control_rig", asset_path=_CR_PATH)
        r = self.call("control_rig_actions", "ue_add_rig_bone",
                      asset_path=_CR_PATH, bone_name="X",
                      parent_name="Y", parent_type="nonsense")
        self.assertFalse(r.get("success"))
