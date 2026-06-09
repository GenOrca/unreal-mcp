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

    def test_is_in_pie(self):
        r = self.call("util_actions", "ue_is_in_pie")
        self.assertSuccess(r)
        self.assertIsInstance(r["in_pie"], bool)
