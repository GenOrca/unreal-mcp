import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_MESH = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP"
_ANIM = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle"
_RIG_PATH = f"{TEST_ROOT}/MCP_TestIKRig"
_RTG_PATH = f"{TEST_ROOT}/MCP_TestRTG"


class TestRetargetActions(MCPTestCase):

    def setUp(self):
        if not hasattr(unreal, "IKRigController"):
            self.skipTest("IKRig plugin not enabled")
        if not unreal.EditorAssetLibrary.does_asset_exist(_MESH):
            self.skipTest("Engine TutorialTPP mesh not available")
        self.ensure_test_dir()
        for p in (_RTG_PATH, _RIG_PATH):
            self.delete_asset(p)

    def tearDown(self):
        for p in (_RTG_PATH, _RIG_PATH):
            self.delete_asset(p)

    def _make_rig(self):
        r = self.call("retarget_actions", "ue_create_ik_rig",
                      asset_path=_RIG_PATH, skeletal_mesh_path=_MESH, retarget_root="pelvis")
        self.assertSuccess(r)
        r = self.call("retarget_actions", "ue_add_retarget_chain",
                      ik_rig_path=_RIG_PATH, chain_name="Spine",
                      start_bone="spine_01", end_bone="spine_03")
        self.assertSuccess(r)
        return _RIG_PATH

    def test_create_ik_rig_and_info(self):
        self._make_rig()
        r = self.call("retarget_actions", "ue_get_ik_rig_info", ik_rig_path=_RIG_PATH)
        self.assertSuccess(r)
        self.assertEqual(r["retarget_root"], "pelvis")
        self.assertEqual(r["chains"][0]["name"], "Spine")
        self.assertEqual(r["chains"][0]["start_bone"], "spine_01")

    def test_create_ik_rig_bad_mesh(self):
        r = self.call("retarget_actions", "ue_create_ik_rig",
                      asset_path=_RIG_PATH, skeletal_mesh_path="/Engine/BasicShapes/Cube")
        self.assertFalse(r.get("success"))

    def test_add_chain_missing_params(self):
        r = self.call("retarget_actions", "ue_add_retarget_chain", ik_rig_path=_RIG_PATH)
        self.assertFalse(r.get("success"))

    def test_create_retargeter_and_automap(self):
        rig = self._make_rig()
        r = self.call("retarget_actions", "ue_create_retargeter",
                      asset_path=_RTG_PATH, source_ik_rig_path=rig,
                      target_ik_rig_path=rig, auto_map=True)
        self.assertSuccess(r)
        r = self.call("retarget_actions", "ue_auto_map_chains",
                      retargeter_path=_RTG_PATH, mode="EXACT", force=True)
        self.assertSuccess(r)
        r = self.call("retarget_actions", "ue_auto_map_chains",
                      retargeter_path=_RTG_PATH, mode="NONSENSE")
        self.assertFalse(r.get("success"))

    def test_batch_retarget(self):
        rig = self._make_rig()
        self.call("retarget_actions", "ue_create_retargeter",
                  asset_path=_RTG_PATH, source_ik_rig_path=rig,
                  target_ik_rig_path=rig, auto_map=True)
        r = self.call("retarget_actions", "ue_batch_retarget",
                      retargeter_path=_RTG_PATH, anim_paths=[_ANIM],
                      source_mesh_path=_MESH, target_mesh_path=_MESH,
                      suffix="_MCPRT")
        self.assertSuccess(r)
        self.assertEqual(r["count"], 1)
        for p in r["retargeted_assets"]:
            self.delete_asset(p)

    def test_batch_retarget_missing_anim(self):
        rig = self._make_rig()
        self.call("retarget_actions", "ue_create_retargeter",
                  asset_path=_RTG_PATH, source_ik_rig_path=rig,
                  target_ik_rig_path=rig)
        r = self.call("retarget_actions", "ue_batch_retarget",
                      retargeter_path=_RTG_PATH, anim_paths=["/Game/NoSuchAnim_XYZ"],
                      source_mesh_path=_MESH, target_mesh_path=_MESH)
        self.assertFalse(r.get("success"))
