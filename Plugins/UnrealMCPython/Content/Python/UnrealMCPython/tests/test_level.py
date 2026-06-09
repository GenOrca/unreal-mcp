from UnrealMCPython.tests.base import MCPTestCase


class TestLevelActions(MCPTestCase):

    def setUp(self):
        self._gravity_changed = False

    def tearDown(self):
        # Restore default gravity if we changed it
        if self._gravity_changed:
            self.call("level_actions", "ue_set_world_settings", gravity=-980.0)

    def test_list_level_actors(self):
        r = self.call("level_actions", "ue_list_level_actors")
        self.assertSuccess(r)
        self.assertIn("actors", r)
        self.assertIsInstance(r["actors"], list)
        self.assertIn("count", r)

    def test_list_level_actors_with_class_filter(self):
        r = self.call("level_actions", "ue_list_level_actors", class_filter="Light")
        self.assertSuccess(r)
        for actor in r["actors"]:
            self.assertIn("Light", actor["class"])

    def test_set_world_gravity(self):
        self._gravity_changed = True
        r = self.call("level_actions", "ue_set_world_settings", gravity=-500.0)
        self.assertSuccess(r)
        self.assertIn("gravity", r.get("applied", {}))

    def test_set_world_time_dilation(self):
        r = self.call("level_actions", "ue_set_world_settings", time_dilation=1.0)
        self.assertSuccess(r)

    def test_set_world_settings_no_params(self):
        r = self.call("level_actions", "ue_set_world_settings")
        self.assertFalse(r.get("success"))

    # ── create / load (guard paths only) ────────────────────────────────────────
    #
    # NOTE: create_level (new_level) and load_level switch/replace the editor's
    # OPEN level. Exercising their happy path in the shared in-editor suite is
    # destructive — creating a temp level, then deleting it while it is the open
    # level, destabilized the editor and reset the TCP server during development.
    # So we only assert the parameter-guard path here (runs the action through the
    # full chain without mutating the editor session). The empty-param round-trip
    # is also covered by the E2E suite.

    def test_create_level_missing_path(self):
        r = self.call("level_actions", "ue_create_level")
        self.assertFalse(r.get("success"))

    def test_load_level_missing_path(self):
        r = self.call("level_actions", "ue_load_level")
        self.assertFalse(r.get("success"))

    # ── current level ────────────────────────────────────────────────────────────

    def test_get_current_level_path(self):
        r = self.call("level_actions", "ue_get_current_level_path")
        self.assertSuccess(r)
        self.assertIn("level_path", r)
        self.assertTrue(r["level_path"])

    # save_current_level / save_all_levels are not auto-tested: on an unsaved
    # (untitled) level save_current_level can raise a modal Save-As dialog that
    # would hang the headless suite. Verified manually instead (see KNOWN_UNTESTED).
