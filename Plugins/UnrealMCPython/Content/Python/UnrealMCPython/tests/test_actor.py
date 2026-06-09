import unreal
from UnrealMCPython.tests.base import MCPTestCase

_CLASS_PATH = "/Script/Engine.PointLight"


class TestActorActions(MCPTestCase):

    def setUp(self):
        self._actor_label = None
        r = self.call("actor_actions", "ue_spawn_from_class",
                      class_path=_CLASS_PATH, location=[0, 0, 500])
        if r.get("success"):
            self._actor_label = r["actor_label"]

    def tearDown(self):
        if self._actor_label:
            self.delete_actor_by_label(self._actor_label)

    # ── spawn ──────────────────────────────────────────────────────────────────

    def test_spawn_from_class(self):
        self.assertIsNotNone(self._actor_label, "Actor was not spawned in setUp")

    def test_spawn_missing_class(self):
        r = self.call("actor_actions", "ue_spawn_from_class",
                      class_path="/Script/Engine.NonExistentClass123", location=[0, 0, 0])
        self.assertFalse(r.get("success"))

    # ── list / query ───────────────────────────────────────────────────────────

    def test_list_all_with_locations(self):
        r = self.call("actor_actions", "ue_list_all_with_locations")
        self.assertSuccess(r)
        self.assertIsInstance(r["actors"], list)
        labels = [a["name"] for a in r["actors"]]
        self.assertIn(self._actor_label, labels)

    def test_get_all_details(self):
        r = self.call("actor_actions", "ue_get_all_details")
        self.assertSuccess(r)
        self.assertIsInstance(r["actors"], list)

    def test_get_in_view_frustum(self):
        r = self.call("actor_actions", "ue_get_in_view_frustum")
        self.assertSuccess(r)
        self.assertIn("visible_actors", r)

    # ── transform ─────────────────────────────────────────────────────────────

    def test_set_location(self):
        r = self.call("actor_actions", "ue_set_location",
                      actor_label=self._actor_label, location=[100, 200, 300])
        self.assertSuccess(r)

    def test_set_rotation(self):
        r = self.call("actor_actions", "ue_set_rotation",
                      actor_label=self._actor_label, rotation=[0, 45, 0])
        self.assertSuccess(r)

    def test_set_scale(self):
        r = self.call("actor_actions", "ue_set_scale",
                      actor_label=self._actor_label, scale=[2, 2, 2])
        self.assertSuccess(r)

    def test_set_transform_full(self):
        r = self.call("actor_actions", "ue_set_transform",
                      actor_label=self._actor_label,
                      location=[50, 50, 50], rotation=[0, 0, 0], scale=[1, 1, 1])
        self.assertSuccess(r)

    def test_set_transform_unknown_actor(self):
        r = self.call("actor_actions", "ue_set_transform",
                      actor_label="NonExistentActor_XYZ123", location=[0, 0, 0])
        self.assertFalse(r.get("success"))

    # ── property ──────────────────────────────────────────────────────────────

    def test_get_property(self):
        r = self.call("actor_actions", "ue_get_property",
                      actor_label=self._actor_label, property_name="can_be_damaged")
        self.assertSuccess(r)
        self.assertIn("value", r)

    def test_set_property(self):
        r = self.call("actor_actions", "ue_set_property",
                      actor_label=self._actor_label,
                      property_name="can_be_damaged", value=False)
        self.assertSuccess(r)

    # ── selection ─────────────────────────────────────────────────────────────

    def test_select_all(self):
        r = self.call("actor_actions", "ue_select_all")
        self.assertSuccess(r)

    def test_invert_selection(self):
        self.call("actor_actions", "ue_select_all")
        r = self.call("actor_actions", "ue_invert_selection")
        self.assertSuccess(r)

    # ── delete ────────────────────────────────────────────────────────────────

    def test_delete_by_label(self):
        r = self.call("actor_actions", "ue_spawn_from_class",
                      class_path=_CLASS_PATH, location=[9999, 9999, 9999])
        self.assertSuccess(r)
        extra_label = r["actor_label"]
        r = self.call("actor_actions", "ue_delete_by_label", actor_label=extra_label)
        self.assertSuccess(r)

    # ── raycast ───────────────────────────────────────────────────────────────

    def test_line_trace_no_hit(self):
        r = self.call("actor_actions", "ue_line_trace",
                      ray_start=[0, 0, 100000], ray_end=[0, 0, 200000])
        self.assertSuccess(r)
        self.assertFalse(r.get("hit"))

    # ── spawn from object ───────────────────────────────────────────────────────

    def test_spawn_from_object(self):
        r = self.call("actor_actions", "ue_spawn_from_object",
                      asset_path="/Engine/BasicShapes/Cube", location=[1500, 1500, 0])
        self.assertSuccess(r)
        self.assertIn("actor_label", r)
        self.delete_actor_by_label(r["actor_label"])

    def test_spawn_from_object_missing_asset(self):
        r = self.call("actor_actions", "ue_spawn_from_object",
                      asset_path="/Game/DoesNotExist_XYZ123", location=[0, 0, 0])
        self.assertFalse(r.get("success"))

    # ── duplicate ────────────────────────────────────────────────────────────────

    def _select_setup_actor(self):
        import unreal
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = next((a for a in sub.get_all_level_actors()
                      if a.get_actor_label() == self._actor_label), None)
        self.assertIsNotNone(actor, "setUp actor not found in level")
        sub.set_selected_level_actors([actor])

    def test_duplicate_selected(self):
        if not self._actor_label:
            self.skipTest("Actor not spawned in setUp")
        self._select_setup_actor()
        r = self.call("actor_actions", "ue_duplicate_selected", offset=[200, 0, 0])
        self.assertSuccess(r)
        self.assertIsInstance(r.get("duplicated_actors"), list)
        self.assertGreaterEqual(len(r["duplicated_actors"]), 1)
        for label in r["duplicated_actors"]:
            self.delete_actor_by_label(label)

    def test_duplicate_selected_none_selected(self):
        import unreal
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).set_selected_level_actors([])
        r = self.call("actor_actions", "ue_duplicate_selected", offset=[0, 0, 0])
        self.assertFalse(r.get("success"))

    # ── spawn on surface (raycast) ─────────────────────────────────────────────

    def test_spawn_on_surface_raycast_no_hit(self):
        # Raycast through empty space high above the level → no surface to hit.
        r = self.call("actor_actions", "ue_spawn_on_surface_raycast",
                      asset_or_class_path=_CLASS_PATH,
                      ray_start=[0, 0, 500000], ray_end=[0, 0, 600000])
        self.assertFalse(r.get("success"))

    def test_spawn_on_surface_raycast_hit(self):
        # Place a cube as a surface, then raycast straight down onto it.
        floor = self.call("actor_actions", "ue_spawn_from_object",
                          asset_path="/Engine/BasicShapes/Cube", location=[4000, 4000, 0])
        if not floor.get("success"):
            self.skipTest("Could not spawn floor cube for raycast surface")
        try:
            r = self.call("actor_actions", "ue_spawn_on_surface_raycast",
                          asset_or_class_path=_CLASS_PATH,
                          ray_start=[4000, 4000, 1000], ray_end=[4000, 4000, -1000])
            self.assertSuccess(r)
            self.assertIn("actor_label", r)
            self.delete_actor_by_label(r["actor_label"])
        finally:
            self.delete_actor_by_label(floor["actor_label"])

    # ── folders / tags / components / bounds ─────────────────────────────────────

    def test_set_get_actor_folder(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_set_actor_folder",
                      actor_label=self._actor_label, folder_path="MCP/TestFolder")
        self.assertSuccess(r)
        r = self.call("actor_actions", "ue_get_actor_folder", actor_label=self._actor_label)
        self.assertSuccess(r)
        self.assertEqual(r["folder_path"], "MCP/TestFolder")

    def test_actor_tags(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_add_actor_tag",
                      actor_label=self._actor_label, tag="MCP_Tag")
        self.assertSuccess(r)
        self.assertIn("MCP_Tag", r["tags"])
        r = self.call("actor_actions", "ue_get_actor_tags", actor_label=self._actor_label)
        self.assertIn("MCP_Tag", r["tags"])
        r = self.call("actor_actions", "ue_remove_actor_tag",
                      actor_label=self._actor_label, tag="MCP_Tag")
        self.assertSuccess(r)
        self.assertNotIn("MCP_Tag", r["tags"])

    def test_list_actor_components(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_list_actor_components", actor_label=self._actor_label)
        self.assertSuccess(r)
        self.assertGreater(r["count"], 0)

    def test_get_actor_bounds(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_get_actor_bounds", actor_label=self._actor_label)
        self.assertSuccess(r)
        self.assertEqual(len(r["extent"]), 3)

    def test_get_actor_bounds_unknown(self):
        r = self.call("actor_actions", "ue_get_actor_bounds", actor_label="NoSuchActor_XYZ")
        self.assertFalse(r.get("success"))

    # ── attach / detach ──────────────────────────────────────────────────────────

    def test_attach_and_detach(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        spawn = self.call("actor_actions", "ue_spawn_from_class",
                          class_path=_CLASS_PATH, location=[300, 300, 300])
        self.assertSuccess(spawn)
        child = spawn["actor_label"]
        try:
            r = self.call("actor_actions", "ue_attach_actor",
                          child_label=child, parent_label=self._actor_label)
            self.assertSuccess(r)
            r = self.call("actor_actions", "ue_get_attached_actors", actor_label=self._actor_label)
            self.assertSuccess(r)
            self.assertIn(child, r["attached"])
            r = self.call("actor_actions", "ue_detach_actor", actor_label=child)
            self.assertSuccess(r)
            r = self.call("actor_actions", "ue_get_attached_actors", actor_label=self._actor_label)
            self.assertNotIn(child, r["attached"])
        finally:
            self.delete_actor_by_label(child)

    def test_attach_unknown_parent(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_attach_actor",
                      child_label=self._actor_label, parent_label="NoSuchActor_XYZ")
        self.assertFalse(r.get("success"))

    def test_get_actors_of_class(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_get_actors_of_class",
                      class_path="/Script/Engine.PointLight")
        self.assertSuccess(r)
        self.assertIn(self._actor_label, r["actors"])

    def test_get_actors_of_class_invalid(self):
        r = self.call("actor_actions", "ue_get_actors_of_class",
                      class_path="/Script/Engine.NopeXYZ123")
        self.assertFalse(r.get("success"))

    def test_get_selected_actors(self):
        self.call("actor_actions", "ue_select_all")
        r = self.call("actor_actions", "ue_get_selected_actors")
        self.assertSuccess(r)
        self.assertIsInstance(r["actors"], list)

    def test_rename_actor(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        new = self._actor_label + "_Renamed"
        r = self.call("actor_actions", "ue_rename_actor",
                      actor_label=self._actor_label, new_label=new)
        self.assertSuccess(r)
        self.assertEqual(r["new_label"], new)
        self._actor_label = new  # so tearDown deletes the right one

    def test_set_actor_hidden(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_set_actor_hidden",
                      actor_label=self._actor_label, hidden=True)
        self.assertSuccess(r)
        self.call("actor_actions", "ue_set_actor_hidden",
                  actor_label=self._actor_label, hidden=False)

    def test_select_actors(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_select_actors", actor_labels=[self._actor_label])
        self.assertSuccess(r)
        self.assertIn(self._actor_label, r["selected"])

    def test_select_actors_missing(self):
        r = self.call("actor_actions", "ue_select_actors", actor_labels=["NoSuchActor_XYZ"])
        self.assertSuccess(r)
        self.assertIn("NoSuchActor_XYZ", r["missing"])

    def test_get_transform(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_get_transform", actor_label=self._actor_label)
        self.assertSuccess(r)
        self.assertEqual(len(r["location"]), 3)
        self.assertEqual(len(r["rotation"]), 3)
        self.assertEqual(len(r["scale"]), 3)

    def test_get_set_component_property(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        comps = self.call("actor_actions", "ue_list_actor_components",
                          actor_label=self._actor_label)["components"]
        light = next((c["name"] for c in comps if "Light" in c["class"]), comps[0]["name"])
        r = self.call("actor_actions", "ue_set_component_property",
                      actor_label=self._actor_label, component_name=light,
                      property_name="intensity", value=12345.0)
        self.assertSuccess(r)
        r = self.call("actor_actions", "ue_get_component_property",
                      actor_label=self._actor_label, component_name=light,
                      property_name="intensity")
        self.assertSuccess(r)
        self.assertAlmostEqual(r["value"], 12345.0, places=1)

    def test_get_component_property_unknown(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_get_component_property",
                      actor_label=self._actor_label, component_name="NoSuchComp",
                      property_name="intensity")
        self.assertFalse(r.get("success"))

    def test_duplicate_actor(self):
        self.assertIsNotNone(self._actor_label, "no setUp actor")
        r = self.call("actor_actions", "ue_duplicate_actor",
                      actor_label=self._actor_label, offset=[150, 0, 0])
        self.assertSuccess(r)
        self.delete_actor_by_label(r["duplicated"])

    def test_duplicate_actor_unknown(self):
        r = self.call("actor_actions", "ue_duplicate_actor", actor_label="NoSuchActor_XYZ")
        self.assertFalse(r.get("success"))
