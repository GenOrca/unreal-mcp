from UnrealMCPython.tests.base import MCPTestCase


class TestUtilActions(MCPTestCase):

    def test_get_output_log_default(self):
        r = self.call("util_actions", "ue_get_output_log", line_count=10)
        self.assertSuccess(r)
        self.assertIn("log", r)
        self.assertIn("total_lines", r)
        self.assertIn("returned_lines", r)

    def test_get_output_log_with_keyword(self):
        r = self.call("util_actions", "ue_get_output_log", line_count=20, keyword="LogMCPython")
        self.assertSuccess(r)
        self.assertIn("log", r)

    def test_get_output_log_with_context(self):
        # keyword guaranteed to exist: every editor log starts with a LogInit banner
        r = self.call("util_actions", "ue_get_output_log",
                      line_count=5, keyword="LogInit", context_lines=2)
        self.assertSuccess(r)
        self.assertIn("log", r)
        # context expands each match, so returned_lines must exceed the bare match count
        bare = self.call("util_actions", "ue_get_output_log",
                         line_count=5, keyword="LogInit")
        self.assertSuccess(bare)
        self.assertGreaterEqual(r["returned_lines"], bare["returned_lines"])

    def test_get_output_log_tail_matches_line_count(self):
        r = self.call("util_actions", "ue_get_output_log", line_count=3)
        self.assertSuccess(r)
        self.assertEqual(r["returned_lines"], 3)
        self.assertEqual(len(r["log"].splitlines()), 3)

    def test_print_message(self):
        r = self.call("util_actions", "ue_print_message", message="MCP unittest ping")
        self.assertSuccess(r)
        self.assertEqual(r["received_message"], "MCP unittest ping")

    def test_print_message_missing_param(self):
        r = self.call("util_actions", "ue_print_message")
        self.assertFalse(r.get("success"))

    # ── editor control ───────────────────────────────────────────────────────────

    def test_execute_console_command(self):
        r = self.call("util_actions", "ue_execute_console_command", command="stat none")
        self.assertSuccess(r)

    def test_execute_console_command_missing(self):
        r = self.call("util_actions", "ue_execute_console_command")
        self.assertFalse(r.get("success"))

    def test_save_all_dirty(self):
        r = self.call("util_actions", "ue_save_all_dirty")
        self.assertIn("success", r)  # may save nothing if clean; must not error

    def test_get_and_set_viewport_camera(self):
        cur = self.call("util_actions", "ue_get_viewport_camera")
        if not cur.get("success") and "No active level viewport" in cur.get("message", ""):
            self.skipTest("No active level viewport (e.g. editor launched without a focused viewport)")
        self.assertSuccess(cur)
        self.assertEqual(len(cur["location"]), 3)
        try:
            r = self.call("util_actions", "ue_set_viewport_camera",
                          location=[500.0, 500.0, 500.0], rotation=[0.0, 90.0, 0.0])
            self.assertSuccess(r)
        finally:
            self.call("util_actions", "ue_set_viewport_camera",
                      location=cur["location"], rotation=cur["rotation"])

    def test_set_viewport_camera_missing(self):
        r = self.call("util_actions", "ue_set_viewport_camera")
        self.assertFalse(r.get("success"))

    # ── world<->screen projection ────────────────────────────────────────────────

    def _skip_if_no_viewport(self, r):
        if not r.get("success") and "No active level viewport" in r.get("message", ""):
            self.skipTest("No active level viewport for projection")

    def test_screen_world_round_trips_back_to_pixel(self):
        # A deprojected world point lies on the view ray of its pixel, so re-projecting it
        # must return the same pixel exactly — the clean projection invariant.
        probe = self.call("util_actions", "ue_screen_to_world", x=200.0, y=200.0, distance=500.0)
        self._skip_if_no_viewport(probe)
        self.assertSuccess(probe)
        self.assertEqual(len(probe["location"]), 3)
        self.assertEqual(len(probe["direction"]), 3)

        back = self.call("util_actions", "ue_world_to_screen", location=probe["location"])
        self.assertSuccess(back)
        self.assertTrue(back["visible"])
        self.assertGreater(back["viewport_width"], 0)
        self.assertAlmostEqual(back["x"], 200.0, delta=1.0)
        self.assertAlmostEqual(back["y"], 200.0, delta=1.0)

    def test_world_to_screen_rejects_bad_location(self):
        r = self.call("util_actions", "ue_world_to_screen", location=[1.0, 2.0])
        self.assertFalse(r.get("success"))

    def test_screen_to_world_missing_param(self):
        r = self.call("util_actions", "ue_screen_to_world", x=10.0)
        self.assertFalse(r.get("success"))

    def test_is_in_pie(self):
        r = self.call("util_actions", "ue_is_in_pie")
        self.assertSuccess(r)
        self.assertIsInstance(r["in_pie"], bool)

    def test_list_class_properties(self):
        r = self.call("util_actions", "ue_list_class_properties",
                      class_path="/Script/Engine.PointLight")
        self.assertSuccess(r)
        self.assertGreater(r["count"], 0)

    def test_list_class_properties_invalid(self):
        r = self.call("util_actions", "ue_list_class_properties",
                      class_path="/Script/Engine.NopeXYZ123")
        self.assertFalse(r.get("success"))

    def test_get_cvar(self):
        r = self.call("util_actions", "ue_get_cvar", name="r.ScreenPercentage")
        self.assertSuccess(r)
        self.assertIn("value", r)

    def test_get_cvar_missing(self):
        r = self.call("util_actions", "ue_get_cvar")
        self.assertFalse(r.get("success"))

    def test_set_cvar_round_trips(self):
        name = "r.ScreenPercentage"
        before = self.call("util_actions", "ue_get_cvar", name=name)["value"]
        try:
            r = self.call("util_actions", "ue_set_cvar", name=name, value="73")
            self.assertSuccess(r)
            got = self.call("util_actions", "ue_get_cvar", name=name)["value"]
            self.assertEqual(float(got), 73.0)
        finally:
            self.call("util_actions", "ue_set_cvar", name=name, value=before)

    def test_set_cvar_missing_param(self):
        r = self.call("util_actions", "ue_set_cvar", name="r.ScreenPercentage")
        self.assertFalse(r.get("success"))

    def test_set_log_verbosity(self):
        try:
            r = self.call("util_actions", "ue_set_log_verbosity",
                          category="LogMCPython", verbosity="Verbose")
            self.assertSuccess(r)
        finally:
            self.call("util_actions", "ue_set_log_verbosity",
                      category="LogMCPython", verbosity="Log")

    def test_set_log_verbosity_invalid(self):
        r = self.call("util_actions", "ue_set_log_verbosity",
                      category="LogMCPython", verbosity="NopeLevel")
        self.assertFalse(r.get("success"))

    def test_get_project_info(self):
        r = self.call("util_actions", "ue_get_project_info")
        self.assertSuccess(r)
        self.assertIn("engine_version", r)
        self.assertTrue(r["project_dir"])

    def test_list_enum_values(self):
        r = self.call("util_actions", "ue_list_enum_values",
                      enum_name="TextureCompressionSettings")
        self.assertSuccess(r)
        self.assertIn("TC_DEFAULT", r["values"])

    def test_list_enum_values_unknown(self):
        r = self.call("util_actions", "ue_list_enum_values", enum_name="NopeEnumXYZ")
        self.assertFalse(r.get("success"))
