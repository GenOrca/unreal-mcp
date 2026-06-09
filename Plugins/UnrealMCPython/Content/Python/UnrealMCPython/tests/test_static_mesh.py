import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_SRC = "/Engine/BasicShapes/Cube"
_DEFAULT_MAT = "/Engine/BasicShapes/BasicShapeMaterial"


class TestStaticMeshActions(MCPTestCase):

    def test_get_static_mesh_info(self):
        r = self.call("static_mesh_actions", "ue_get_static_mesh_info", asset_path=_SRC)
        self.assertSuccess(r)
        self.assertGreaterEqual(r["num_lods"], 1)
        self.assertGreater(r["num_triangles_lod0"], 0)
        self.assertGreater(r["num_vertices_lod0"], 0)

    def test_get_static_mesh_info_invalid(self):
        r = self.call("static_mesh_actions", "ue_get_static_mesh_info",
                      asset_path="/Game/DoesNotExist_XYZ")
        self.assertFalse(r.get("success"))

    def test_list_materials(self):
        r = self.call("static_mesh_actions", "ue_list_static_mesh_materials", asset_path=_SRC)
        self.assertSuccess(r)
        self.assertGreaterEqual(r["num_materials"], 1)

    def test_get_collision_info(self):
        r = self.call("static_mesh_actions", "ue_get_collision_info", asset_path=_SRC)
        self.assertSuccess(r)
        self.assertIn("simple_collision_count", r)

    def test_set_material(self):
        self.ensure_test_dir()
        dst = f"{TEST_ROOT}/MCP_SMCopy"
        self.delete_asset(dst)
        unreal.EditorAssetLibrary.duplicate_asset(_SRC, dst)
        try:
            r = self.call("static_mesh_actions", "ue_set_static_mesh_material",
                          asset_path=dst, slot_index=0, material_path=_DEFAULT_MAT)
            self.assertSuccess(r)
        finally:
            self.delete_asset(dst)

    def test_add_simple_collision(self):
        self.ensure_test_dir()
        dst = f"{TEST_ROOT}/MCP_SMCol"
        self.delete_asset(dst)
        unreal.EditorAssetLibrary.duplicate_asset(_SRC, dst)
        try:
            before = self.call("static_mesh_actions", "ue_get_collision_info",
                               asset_path=dst)["simple_collision_count"]
            r = self.call("static_mesh_actions", "ue_add_simple_collision",
                          asset_path=dst, shape="SPHERE")
            self.assertSuccess(r)
            self.assertGreater(r["simple_collision_count"], before)
        finally:
            self.delete_asset(dst)

    def test_add_simple_collision_bad_shape(self):
        r = self.call("static_mesh_actions", "ue_add_simple_collision",
                      asset_path=_SRC, shape="NOTASHAPE")
        self.assertFalse(r.get("success"))
