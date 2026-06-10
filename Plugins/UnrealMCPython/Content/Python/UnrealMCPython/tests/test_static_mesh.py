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

    # ── LODs ─────────────────────────────────────────────────────────────────────

    def _dup_mesh(self, name):
        self.ensure_test_dir()
        dst = f"{TEST_ROOT}/{name}"
        self.delete_asset(dst)
        unreal.EditorAssetLibrary.duplicate_asset(_SRC, dst)
        return dst

    def test_set_and_remove_lods(self):
        dst = self._dup_mesh("MCP_SMLod")
        try:
            r = self.call("static_mesh_actions", "ue_set_lods", asset_path=dst,
                          lod_settings=[{"percent_triangles": 1.0, "screen_size": 1.0},
                                        {"percent_triangles": 0.5, "screen_size": 0.5}])
            self.assertSuccess(r)
            self.assertEqual(r["lod_count"], 2)
            r = self.call("static_mesh_actions", "ue_get_lod_screen_sizes", asset_path=dst)
            self.assertSuccess(r)
            self.assertEqual(len(r["screen_sizes"]), 2)
            r = self.call("static_mesh_actions", "ue_remove_lods", asset_path=dst)
            self.assertSuccess(r)
            self.assertEqual(r["lod_count"], 1)
        finally:
            self.delete_asset(dst)

    def test_set_lods_missing(self):
        r = self.call("static_mesh_actions", "ue_set_lods", asset_path=_SRC)
        self.assertFalse(r.get("success"))

    def test_set_lod_from_static_mesh(self):
        dst = self._dup_mesh("MCP_SMLodCopy")
        try:
            r = self.call("static_mesh_actions", "ue_set_lod_from_static_mesh",
                          asset_path=dst, lod_index=1,
                          source_path="/Engine/BasicShapes/Sphere", source_lod_index=0)
            self.assertSuccess(r)
            self.assertEqual(r["lod_count"], 2)
        finally:
            self.delete_asset(dst)

    # ── convex / collision management ───────────────────────────────────────────

    def test_convex_and_remove_collisions(self):
        dst = self._dup_mesh("MCP_SMConvex")
        try:
            r = self.call("static_mesh_actions", "ue_set_convex_collision",
                          asset_path=dst, hull_count=2, max_hull_verts=16, hull_precision=100000)
            self.assertSuccess(r)
            self.assertGreaterEqual(r["convex_collision_count"], 1)
            r = self.call("static_mesh_actions", "ue_remove_collisions", asset_path=dst)
            self.assertSuccess(r)
            self.assertEqual(r["convex_collision_count"], 0)
        finally:
            self.delete_asset(dst)

    def test_set_lod_for_collision(self):
        dst = self._dup_mesh("MCP_SMLodCol")
        try:
            r = self.call("static_mesh_actions", "ue_set_lod_for_collision",
                          asset_path=dst, lod_index=0)
            self.assertSuccess(r)
            r = self.call("static_mesh_actions", "ue_set_lod_for_collision",
                          asset_path=dst, lod_index=99)
            self.assertFalse(r.get("success"))
        finally:
            self.delete_asset(dst)
