from UnrealMCPython.tests.base import MCPTestCase


class TestAssetActions(MCPTestCase):

    def test_find_by_type(self):
        r = self.call("asset_actions", "ue_find_by_query", asset_type="StaticMesh")
        self.assertSuccess(r)
        self.assertIsInstance(r["assets"], list)

    def test_find_by_name(self):
        r = self.call("asset_actions", "ue_find_by_query", name="Cube")
        self.assertSuccess(r)
        self.assertIsInstance(r["assets"], list)

    def test_find_by_name_and_type(self):
        r = self.call("asset_actions", "ue_find_by_query",
                      name="Cube", asset_type="StaticMesh")
        self.assertSuccess(r)

    def test_find_missing_params_fails(self):
        r = self.call("asset_actions", "ue_find_by_query")
        self.assertFalse(r.get("success"))

    def test_get_static_mesh_details_invalid(self):
        r = self.call("asset_actions", "ue_get_static_mesh_details",
                      asset_path="/Game/DoesNotExist/FakeMesh")
        self.assertFalse(r.get("success"))


    # ── asset management ─────────────────────────────────────────────────────────

    _SRC = "/Engine/BasicShapes/Cube"
    _DIR = "/Game/Tests/MCP_AssetMgmt"

    def _dup(self, name):
        import unreal
        dst = f"{self._DIR}/{name}"
        if unreal.EditorAssetLibrary.does_asset_exist(dst):
            unreal.EditorAssetLibrary.delete_asset(dst)
        return dst

    def test_asset_exists(self):
        r = self.call("asset_actions", "ue_asset_exists", asset_path=self._SRC)
        self.assertSuccess(r)
        self.assertTrue(r["exists"])
        r = self.call("asset_actions", "ue_asset_exists", asset_path="/Game/Nope_XYZ")
        self.assertFalse(r["exists"])

    def test_get_asset_info(self):
        r = self.call("asset_actions", "ue_get_asset_info", asset_path=self._SRC)
        self.assertSuccess(r)
        self.assertEqual(r["asset_class"], "StaticMesh")

    def test_duplicate_and_delete_asset(self):
        import unreal
        self.call("asset_actions", "ue_make_directory", directory_path=self._DIR)
        dst = self._dup("DupCube")
        try:
            r = self.call("asset_actions", "ue_duplicate_asset", source_path=self._SRC, dest_path=dst)
            self.assertSuccess(r)
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(dst))
            r = self.call("asset_actions", "ue_delete_asset", asset_path=dst)
            self.assertSuccess(r)
            self.assertFalse(unreal.EditorAssetLibrary.does_asset_exist(dst))
        finally:
            if unreal.EditorAssetLibrary.does_asset_exist(dst):
                unreal.EditorAssetLibrary.delete_asset(dst)

    def test_rename_asset(self):
        import unreal
        self.call("asset_actions", "ue_make_directory", directory_path=self._DIR)
        src = self._dup("RenameSrc")
        dst = self._dup("RenameDst")
        unreal.EditorAssetLibrary.duplicate_asset(self._SRC, src)
        try:
            r = self.call("asset_actions", "ue_rename_asset", source_path=src, dest_path=dst)
            self.assertSuccess(r)
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(dst))
        finally:
            for p in (src, dst):
                if unreal.EditorAssetLibrary.does_asset_exist(p):
                    unreal.EditorAssetLibrary.delete_asset(p)

    def test_list_assets(self):
        r = self.call("asset_actions", "ue_list_assets",
                      directory_path="/Engine/BasicShapes", recursive=True)
        self.assertSuccess(r)
        self.assertGreater(r["count"], 0)

    def test_find_referencers(self):
        r = self.call("asset_actions", "ue_find_referencers", asset_path=self._SRC)
        self.assertSuccess(r)
        self.assertIn("referencers", r)

    def test_make_and_delete_directory(self):
        import unreal
        d = "/Game/Tests/MCP_TempDir"
        r = self.call("asset_actions", "ue_make_directory", directory_path=d)
        self.assertSuccess(r)
        self.assertTrue(unreal.EditorAssetLibrary.does_directory_exist(d))
        r = self.call("asset_actions", "ue_delete_directory", directory_path=d)
        self.assertSuccess(r)

    def test_delete_asset_missing(self):
        r = self.call("asset_actions", "ue_delete_asset", asset_path="/Game/Nope_XYZ123")
        self.assertFalse(r.get("success"))

    def test_save_asset(self):
        import unreal
        self.call("asset_actions", "ue_make_directory", directory_path=self._DIR)
        dst = self._dup("SaveCube")
        unreal.EditorAssetLibrary.duplicate_asset(self._SRC, dst)
        try:
            r = self.call("asset_actions", "ue_save_asset", asset_path=dst)
            self.assertSuccess(r)
        finally:
            if unreal.EditorAssetLibrary.does_asset_exist(dst):
                unreal.EditorAssetLibrary.delete_asset(dst)

    def test_save_asset_missing(self):
        r = self.call("asset_actions", "ue_save_asset", asset_path="/Game/Nope_XYZ123")
        self.assertFalse(r.get("success"))
