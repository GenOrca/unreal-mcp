from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

_WBP_NAME = "MCP_TestWidget"
_WBP_PATH = f"{TEST_ROOT}/{_WBP_NAME}"
_WBP_FULL = f"{_WBP_PATH}.{_WBP_NAME}"


class TestUMGActions(MCPTestCase):

    def setUp(self):
        self._wbp_path = None
        self.ensure_test_dir()
        r = self.call("umg_actions", "ue_create_widget_blueprint",
                      name=_WBP_NAME, path=TEST_ROOT)
        if r.get("success"):
            self._wbp_path = _WBP_FULL

    def tearDown(self):
        if self._wbp_path:
            self.delete_asset(self._wbp_path)

    def _skip_if_no_wbp(self):
        if not self._wbp_path:
            self.skipTest("WidgetBlueprint not created in setUp")

    # ── create / info ─────────────────────────────────────────────────────────

    def test_create_widget_blueprint(self):
        self.assertIsNotNone(self._wbp_path, "Widget Blueprint was not created in setUp")

    def test_get_widget_blueprint_info_empty(self):
        self._skip_if_no_wbp()
        r = self.call("umg_actions", "ue_get_widget_blueprint_info",
                      asset_path=self._wbp_path)
        self.assertSuccess(r)
        self.assertIn("widget_count", r)

    # ── add widgets ───────────────────────────────────────────────────────────

    def test_add_canvas_panel_root(self):
        self._skip_if_no_wbp()
        r = self.call("umg_actions", "ue_add_widget",
                      asset_path=self._wbp_path,
                      widget_type="CanvasPanel", widget_name="RootCanvas")
        self.assertSuccess(r)
        self.assertTrue(r.get("is_root"))

    def test_add_text_block_under_canvas(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        r = self.call("umg_actions", "ue_add_widget",
                      asset_path=self._wbp_path,
                      widget_type="TextBlock", widget_name="TitleText",
                      parent_name="RootCanvas")
        self.assertSuccess(r)

    def test_add_and_remove_widget(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="Button", widget_name="RemoveBtn",
                  parent_name="RootCanvas")
        r = self.call("umg_actions", "ue_remove_widget",
                      asset_path=self._wbp_path, widget_name="RemoveBtn")
        self.assertSuccess(r)

    # ── properties ────────────────────────────────────────────────────────────

    def test_set_widget_properties(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="TextBlock", widget_name="Label",
                  parent_name="RootCanvas")
        r = self.call("umg_actions", "ue_set_widget_properties",
                      asset_path=self._wbp_path, widget_name="Label",
                      properties={"text": "Hello", "font_size": 24,
                                  "slot_position": [100.0, 50.0],
                                  "slot_size": [300.0, 60.0]})
        self.assertSuccess(r)

    def test_set_slot_layout(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="Image", widget_name="BgImage",
                  parent_name="RootCanvas")
        r = self.call("umg_actions", "ue_set_slot_layout",
                      asset_path=self._wbp_path, widget_name="BgImage",
                      anchor_min_x=0.0, anchor_min_y=0.0,
                      anchor_max_x=1.0, anchor_max_y=1.0,
                      offset_x=0.0, offset_y=0.0,
                      size_x=800.0, size_y=600.0)
        self.assertSuccess(r)

    def test_set_get_widget_property(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="TextBlock", widget_name="PropText",
                  parent_name="RootCanvas")
        r = self.call("umg_actions", "ue_set_widget_property",
                      asset_path=self._wbp_path, widget_name="PropText",
                      property_name="ToolTipText", value="hello tip")
        self.assertSuccess(r)
        r = self.call("umg_actions", "ue_get_widget_property",
                      asset_path=self._wbp_path, widget_name="PropText",
                      property_name="ToolTipText")
        self.assertSuccess(r)
        self.assertIn("value", r)

    def test_set_text_style(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="TextBlock", widget_name="StyledText",
                  parent_name="RootCanvas")
        r = self.call("umg_actions", "ue_set_text_style",
                      asset_path=self._wbp_path, widget_name="StyledText",
                      font_size=30, color_r=1.0, color_g=0.0, color_b=0.0, color_a=1.0)
        self.assertSuccess(r)

    # ── compile ───────────────────────────────────────────────────────────────

    def test_compile_widget_blueprint(self):
        self._skip_if_no_wbp()
        self.call("umg_actions", "ue_add_widget",
                  asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="RootCanvas")
        r = self.call("umg_actions", "ue_compile_widget_blueprint",
                      asset_path=self._wbp_path)
        self.assertSuccess(r)

    # ── hierarchy ops: reparent / wrap / replace ─────────────────────────────────

    def _root_canvas_with(self, *widgets):
        self.call("umg_actions", "ue_add_widget", asset_path=self._wbp_path,
                  widget_type="CanvasPanel", widget_name="Root")
        for wtype, wname in widgets:
            self.call("umg_actions", "ue_add_widget", asset_path=self._wbp_path,
                      widget_type=wtype, widget_name=wname, parent_name="Root")

    def test_reparent_widget_and_cycle_guard(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("VerticalBox", "VBox"), ("Button", "Btn"))
        r = self.call("umg_actions", "ue_reparent_widget", asset_path=self._wbp_path,
                      widget_name="Btn", new_parent_name="VBox")
        self.assertSuccess(r)
        # Btn now lives under VBox — reparenting VBox into Btn must be rejected (cycle)
        r2 = self.call("umg_actions", "ue_reparent_widget", asset_path=self._wbp_path,
                       widget_name="VBox", new_parent_name="Btn")
        self.assertFalse(r2.get("success"))

    def test_reparent_missing_param(self):
        self._skip_if_no_wbp()
        r = self.call("umg_actions", "ue_reparent_widget",
                      asset_path=self._wbp_path, widget_name="Btn")
        self.assertFalse(r.get("success"))

    def test_wrap_widget(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "Btn"))
        r = self.call("umg_actions", "ue_wrap_widget", asset_path=self._wbp_path,
                      widget_name="Btn", wrapper_type="VerticalBox", wrapper_name="Wrapper")
        self.assertSuccess(r)
        self.assertEqual(r["wrapper_type"], "VerticalBox")
        # tree must still compile after the structural change
        c = self.call("umg_actions", "ue_compile_widget_blueprint", asset_path=self._wbp_path)
        self.assertSuccess(c)

    def test_wrap_rejects_non_panel_wrapper(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "Btn"))
        r = self.call("umg_actions", "ue_wrap_widget", asset_path=self._wbp_path,
                      widget_name="Btn", wrapper_type="TextBlock", wrapper_name="BadWrap")
        self.assertFalse(r.get("success"))

    def test_replace_widget(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "OldBtn"))
        r = self.call("umg_actions", "ue_replace_widget", asset_path=self._wbp_path,
                      widget_name="OldBtn", new_type="Image", new_name="NewImg")
        self.assertSuccess(r)
        self.assertEqual(r["new_type"], "Image")
        # the old widget must be gone — operating on it now fails
        gone = self.call("umg_actions", "ue_reparent_widget", asset_path=self._wbp_path,
                         widget_name="OldBtn", new_parent_name="Root")
        self.assertFalse(gone.get("success"))

    # ── event binding ────────────────────────────────────────────────────────────

    def test_list_widget_events(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "Btn"))
        r = self.call("umg_actions", "ue_list_widget_events",
                      asset_path=self._wbp_path, widget_name="Btn")
        self.assertSuccess(r)
        # a Button exposes OnClicked among its multicast delegates
        self.assertIn("OnClicked", r["events"])

    def test_bind_widget_event(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "Btn"))
        r = self.call("umg_actions", "ue_bind_widget_event",
                      asset_path=self._wbp_path, widget_name="Btn", event_name="OnClicked")
        self.assertSuccess(r)
        self.assertEqual(r["event"], "OnClicked")
        self.assertTrue(r["node"])
        # binding the same event again is idempotent (reports the existing node)
        again = self.call("umg_actions", "ue_bind_widget_event",
                          asset_path=self._wbp_path, widget_name="Btn", event_name="OnClicked")
        self.assertSuccess(again)
        self.assertTrue(again["already_existed"])

    def test_bind_widget_event_unknown_event(self):
        self._skip_if_no_wbp()
        self._root_canvas_with(("Button", "Btn"))
        r = self.call("umg_actions", "ue_bind_widget_event",
                      asset_path=self._wbp_path, widget_name="Btn", event_name="OnNopeEvent_XYZ")
        self.assertFalse(r.get("success"))

    def test_bind_widget_event_missing_param(self):
        self._skip_if_no_wbp()
        r = self.call("umg_actions", "ue_bind_widget_event",
                      asset_path=self._wbp_path, widget_name="Btn")
        self.assertFalse(r.get("success"))
