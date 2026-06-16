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

    def test_get_dependencies(self):
        r = self.call("asset_actions", "ue_get_dependencies", asset_path=self._SRC)
        self.assertSuccess(r)
        self.assertIn("dependencies", r)

    def test_get_dependencies_missing(self):
        r = self.call("asset_actions", "ue_get_dependencies", asset_path="/Game/Nope_XYZ")
        self.assertFalse(r.get("success"))

    def test_metadata_tag_roundtrip(self):
        import unreal
        self.call("asset_actions", "ue_make_directory", directory_path=self._DIR)
        dst = self._dup("MetaCube")
        unreal.EditorAssetLibrary.duplicate_asset(self._SRC, dst)
        try:
            r = self.call("asset_actions", "ue_set_metadata_tag",
                          asset_path=dst, tag="MCP_Tag", value="hello")
            self.assertSuccess(r)
            r = self.call("asset_actions", "ue_get_metadata_tag", asset_path=dst, tag="MCP_Tag")
            self.assertEqual(r["value"], "hello")
            r = self.call("asset_actions", "ue_remove_metadata_tag", asset_path=dst, tag="MCP_Tag")
            self.assertSuccess(r)
            r = self.call("asset_actions", "ue_get_metadata_tag", asset_path=dst, tag="MCP_Tag")
            self.assertEqual(r["value"], "")
        finally:
            if unreal.EditorAssetLibrary.does_asset_exist(dst):
                unreal.EditorAssetLibrary.delete_asset(dst)

    # ── file import / export ─────────────────────────────────────────────────────

    def test_export_import_fbx_roundtrip(self):
        import unreal, os, tempfile
        fbx = os.path.join(tempfile.gettempdir(), "mcp_test_roundtrip.fbx")
        imported = None
        try:
            r = self.call("asset_actions", "ue_export_fbx",
                          asset_path="/Engine/BasicShapes/Cube", file_path=fbx)
            self.assertSuccess(r)
            self.assertGreater(r["file_size"], 0)
            r = self.call("asset_actions", "ue_import_fbx",
                          file_path=fbx, destination_path="/Game/Tests/MCP",
                          destination_name="MCP_RoundtripCube")
            self.assertSuccess(r)
            imported = r["imported_assets"][0]
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(imported))
        finally:
            if imported:
                self.delete_asset(imported)
            if os.path.exists(fbx):
                os.remove(fbx)

    def test_import_texture(self):
        import unreal, os, tempfile, struct, zlib
        def png_bytes():
            w = h = 2
            raw = b""
            for _ in range(h):
                raw += b"\x00" + (b"\xff\x00\x00") * w
            def chunk(t, d):
                c = t + d
                return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return (b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        p = os.path.join(tempfile.gettempdir(), "mcp_test_tex.png")
        with open(p, "wb") as f:
            f.write(png_bytes())
        imported = None
        try:
            r = self.call("asset_actions", "ue_import_texture",
                          file_path=p, destination_path="/Game/Tests/MCP",
                          destination_name="MCP_ImportedTex")
            self.assertSuccess(r)
            imported = r["imported_assets"][0]
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(imported))
        finally:
            if imported:
                self.delete_asset(imported)
            os.remove(p)

    def test_export_fbx_unsupported(self):
        import os, tempfile
        r = self.call("asset_actions", "ue_export_fbx",
                      asset_path="/Engine/BasicShapes/BasicShapeMaterial",
                      file_path=os.path.join(tempfile.gettempdir(), "nope.fbx"))
        self.assertFalse(r.get("success"))

    def test_import_fbx_missing_file(self):
        r = self.call("asset_actions", "ue_import_fbx",
                      file_path="C:/no/such/file.fbx", destination_path="/Game/Tests/MCP")
        self.assertFalse(r.get("success"))

    # ── glTF import (deferred-tick; happy path is covered by test_e2e) ────────────

    def test_import_gltf_missing_param(self):
        r = self.call("asset_actions", "ue_import_gltf", file_path="C:/x.glb")
        self.assertFalse(r.get("success"))  # destination_path missing

    def test_import_gltf_file_not_found(self):
        r = self.call("asset_actions", "ue_import_gltf",
                      file_path="C:/no/such/model.glb", destination_path="/Game/Tests/MCP/glb_guard")
        self.assertFalse(r.get("success"))

    def test_get_gltf_import_status_missing_param(self):
        r = self.call("asset_actions", "ue_get_gltf_import_status")
        self.assertFalse(r.get("success"))

    def test_get_gltf_import_status_no_import(self):
        # nothing scheduled for this path → valid response, not done yet (pending)
        r = self.call("asset_actions", "ue_get_gltf_import_status",
                      destination_path="/Game/Tests/MCP/never_imported_xyz")
        self.assertSuccess(r)
        self.assertFalse(r["done"])
