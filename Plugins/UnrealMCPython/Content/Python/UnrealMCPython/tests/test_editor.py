import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_CLASS_PATH = "/Script/Engine.PointLight"


class TestEditorActions(MCPTestCase):

    def setUp(self):
        self._actor_label = None
        self._actor_path = None
        r = self.call("actor_actions", "ue_spawn_from_class",
                      class_path=_CLASS_PATH, location=[0, 0, 600])
        if r.get("success"):
            self._actor_label = r["actor_label"]
            self._actor_path = r.get("actor_path")

    def tearDown(self):
        if self._actor_label:
            self.delete_actor_by_label(self._actor_label)

    # ── get selected assets ───────────────────────────────────────────────────

    def test_get_selected_assets(self):
        r = self.call("editor_actions", "ue_get_selected_assets")
        self.assertSuccess(r)
        self.assertIn("selected_assets", r)
        self.assertIsInstance(r["selected_assets"], list)

    # ── material replace (specified) ──────────────────────────────────────────

    def test_replace_mtl_on_specified_no_mesh_actor(self):
        # PointLight has no mesh component — operation should succeed but change 0 slots
        if not self._actor_path:
            self.skipTest("Actor not spawned in setUp")
        r = self.call("editor_actions", "ue_replace_mtl_on_specified",
                      actor_paths=[self._actor_path],
                      material_to_be_replaced_path="/Game/DoesNotExist/OldMat",
                      new_material_path="/Game/DoesNotExist/NewMat")
        # No mesh to replace on, so result depends on implementation;
        # at minimum, the call should not crash the editor
        self.assertIsInstance(r.get("success"), bool)

    # ── mesh replace (specified) ──────────────────────────────────────────────

    def test_replace_mesh_on_specified_no_mesh_actor(self):
        if not self._actor_path:
            self.skipTest("Actor not spawned in setUp")
        r = self.call("editor_actions", "ue_replace_mesh_on_specified",
                      actor_paths=[self._actor_path],
                      mesh_to_be_replaced_path="/Game/DoesNotExist/OldMesh",
                      new_mesh_path="/Game/DoesNotExist/NewMesh")
        self.assertIsInstance(r.get("success"), bool)

    # ── replace on selected ─────────────────────────────────────────────────────

    def _select_setup_actor(self):
        import unreal
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = next((a for a in sub.get_all_level_actors()
                      if a.get_actor_label() == self._actor_label), None)
        self.assertIsNotNone(actor, "setUp actor not found")
        sub.set_selected_level_actors([actor])

    def test_replace_mtl_on_selected_no_mesh_actor(self):
        if not self._actor_label:
            self.skipTest("Actor not spawned in setUp")
        self._select_setup_actor()
        r = self.call("editor_actions", "ue_replace_mtl_on_selected",
                      material_to_be_replaced_path="/Game/DoesNotExist/OldMat",
                      new_material_path="/Game/DoesNotExist/NewMat")
        self.assertIsInstance(r.get("success"), bool)

    def test_replace_mesh_on_selected_no_mesh_actor(self):
        if not self._actor_label:
            self.skipTest("Actor not spawned in setUp")
        self._select_setup_actor()
        r = self.call("editor_actions", "ue_replace_mesh_on_selected",
                      mesh_to_be_replaced_path="/Game/DoesNotExist/OldMesh",
                      new_mesh_path="/Game/DoesNotExist/NewMesh")
        self.assertIsInstance(r.get("success"), bool)

    # ── replace selected with blueprint ─────────────────────────────────────────

    def test_replace_selected_with_bp_invalid_path(self):
        # Use an invalid BP path so the setUp actor is not actually replaced
        # (keeps the test session/cleanup intact). Proves the action runs.
        if not self._actor_label:
            self.skipTest("Actor not spawned in setUp")
        self._select_setup_actor()
        r = self.call("editor_actions", "ue_replace_selected_with_bp",
                      blueprint_asset_path="/Game/DoesNotExist/BP_Nope")
        self.assertFalse(r.get("success"))

    # ── merge / join / proxy ─────────────────────────────────────────────────────

    def _spawn_cubes(self, n=2):
        labels = []
        for i in range(n):
            r = self.call("actor_actions", "ue_spawn_from_object",
                          asset_path="/Engine/BasicShapes/Cube", location=[i * 150, 0, 2200])
            self.assertSuccess(r)
            labels.append(r["actor_label"])
        return labels

    def test_merge_actors(self):
        import unreal
        labels = self._spawn_cubes()
        merged_actor = None
        mesh_asset = None
        try:
            r = self.call("editor_actions", "ue_merge_actors",
                          actor_labels=labels,
                          base_package_name="/Game/Tests/MCP/MCP_Merged")
            self.assertSuccess(r)
            merged_actor = r["merged_actor"]
            mesh_asset = r["mesh_asset"]
            self.assertIsNotNone(mesh_asset)
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(mesh_asset))
        finally:
            for l in labels + ([merged_actor] if merged_actor else []):
                self.delete_actor_by_label(l)
            if mesh_asset:
                self.delete_asset(mesh_asset)

    def test_join_actors(self):
        labels = self._spawn_cubes()
        joined = None
        try:
            r = self.call("editor_actions", "ue_join_actors",
                          actor_labels=labels, new_actor_label="MCP_Joined")
            self.assertSuccess(r)
            joined = r["joined_actor"]
        finally:
            for l in labels + ([joined] if joined else []):
                self.delete_actor_by_label(l)

    def test_create_proxy_actor(self):
        import unreal
        labels = self._spawn_cubes()
        proxy = None
        mesh_asset = None
        try:
            r = self.call("editor_actions", "ue_create_proxy_actor",
                          actor_labels=labels,
                          base_package_name="/Game/Tests/MCP/MCP_Proxy",
                          screen_size=300)
            self.assertSuccess(r)
            proxy = r["proxy_actor"]
            mesh_asset = r["mesh_asset"]
        finally:
            for l in labels + ([proxy] if proxy else []):
                self.delete_actor_by_label(l)
            if mesh_asset:
                self.delete_asset(mesh_asset)

    def test_merge_actors_missing(self):
        r = self.call("editor_actions", "ue_merge_actors",
                      actor_labels=["NoSuchActor_XYZ"],
                      base_package_name="/Game/Tests/MCP/Nope")
        self.assertFalse(r.get("success"))


class TestEditorAssetControl(MCPTestCase):

    _ASSET = f"{TEST_ROOT}/MCP_OpenEditorTest"

    def setUp(self):
        self.ensure_test_dir()
        self.delete_asset(self._ASSET)
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", unreal.Actor)
        name = self._ASSET.rsplit("/", 1)[1]
        self._bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, TEST_ROOT, unreal.Blueprint, factory)
        self.assertIsNotNone(self._bp, "could not create test blueprint")

    def tearDown(self):
        try:
            self.call("editor_actions", "ue_close_asset_editor", asset_path=self._ASSET)
        finally:
            self.delete_asset(self._ASSET)

    def _open_paths(self):
        opened = self.call("editor_actions", "ue_get_open_assets")
        self.assertSuccess(opened)
        return [a["asset_path"].split(".")[0] for a in opened["open_assets"]]

    def test_open_lists_then_close_removes(self):
        r = self.call("editor_actions", "ue_open_editor_for_asset", asset_path=self._ASSET)
        self.assertSuccess(r)
        self.assertIn(self._ASSET, self._open_paths())

        r = self.call("editor_actions", "ue_close_asset_editor", asset_path=self._ASSET)
        self.assertSuccess(r)
        self.assertNotIn(self._ASSET, self._open_paths())

    def test_open_editor_rejects_missing_asset(self):
        r = self.call("editor_actions", "ue_open_editor_for_asset",
                      asset_path=f"{TEST_ROOT}/NoSuchAsset_XYZ")
        self.assertFalse(r.get("success"))

    def test_open_editor_missing_param(self):
        r = self.call("editor_actions", "ue_open_editor_for_asset")
        self.assertFalse(r.get("success"))
