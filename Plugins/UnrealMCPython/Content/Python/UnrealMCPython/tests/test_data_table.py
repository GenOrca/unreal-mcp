import unreal
from UnrealMCPython.tests.base import MCPTestCase, TEST_ROOT

# A DataTable that ships with the NNEDenoiser plugin (10 rows) — duplicated into
# /Game so write actions never touch read-only plugin assets.
_SRC_DT = "/NNEDenoiser/NNEDIM_ColorAlbedoNormal_Default"
_DT_NAME = "MCP_TestDataTable"
_DT_PATH = f"{TEST_ROOT}/{_DT_NAME}"


class TestDataTableActions(MCPTestCase):

    def setUp(self):
        self._dt_path = None
        self.ensure_test_dir()
        self.delete_asset(_DT_PATH)
        if unreal.EditorAssetLibrary.does_asset_exist(_SRC_DT):
            dt = unreal.EditorAssetLibrary.duplicate_asset(_SRC_DT, _DT_PATH)
            if dt:
                self._dt_path = _DT_PATH

    def tearDown(self):
        if self._dt_path:
            self.delete_asset(self._dt_path)

    def _skip_if_no_dt(self):
        if not self._dt_path:
            self.skipTest("Source DataTable (NNEDenoiser) not available")

    def test_get_row_names(self):
        self._skip_if_no_dt()
        r = self.call("data_table_actions", "ue_get_row_names", asset_path=self._dt_path)
        self.assertSuccess(r)
        self.assertGreater(r["count"], 0)

    def test_get_column_names(self):
        self._skip_if_no_dt()
        r = self.call("data_table_actions", "ue_get_column_names", asset_path=self._dt_path)
        self.assertSuccess(r)
        self.assertIsInstance(r["columns"], list)
        self.assertIsNotNone(r["row_struct"])

    def test_get_rows_as_json(self):
        self._skip_if_no_dt()
        r = self.call("data_table_actions", "ue_get_rows_as_json", asset_path=self._dt_path)
        self.assertSuccess(r)
        self.assertIn("rows", r)
        self.assertTrue(r["rows"].strip().startswith("["))

    def test_export_to_csv(self):
        self._skip_if_no_dt()
        r = self.call("data_table_actions", "ue_export_to_csv", asset_path=self._dt_path)
        self.assertSuccess(r)
        self.assertIn("csv", r)

    def test_does_row_exist(self):
        self._skip_if_no_dt()
        names = self.call("data_table_actions", "ue_get_row_names", asset_path=self._dt_path)["row_names"]
        r = self.call("data_table_actions", "ue_does_row_exist",
                      asset_path=self._dt_path, row_name=names[0])
        self.assertSuccess(r)
        self.assertTrue(r["exists"])
        r = self.call("data_table_actions", "ue_does_row_exist",
                      asset_path=self._dt_path, row_name="NoSuchRow_XYZ")
        self.assertFalse(r["exists"])

    def test_remove_row(self):
        self._skip_if_no_dt()
        names = self.call("data_table_actions", "ue_get_row_names", asset_path=self._dt_path)["row_names"]
        before = len(names)
        r = self.call("data_table_actions", "ue_remove_row",
                      asset_path=self._dt_path, row_name=names[0])
        self.assertSuccess(r)
        after = self.call("data_table_actions", "ue_get_row_names", asset_path=self._dt_path)["count"]
        self.assertEqual(after, before - 1)

    def test_remove_row_missing(self):
        self._skip_if_no_dt()
        r = self.call("data_table_actions", "ue_remove_row",
                      asset_path=self._dt_path, row_name="NoSuchRow_XYZ")
        self.assertFalse(r.get("success"))

    def test_set_rows_from_json(self):
        self._skip_if_no_dt()
        original = self.call("data_table_actions", "ue_get_rows_as_json", asset_path=self._dt_path)["rows"]
        r = self.call("data_table_actions", "ue_set_rows_from_json",
                      asset_path=self._dt_path, json_string=original)
        self.assertSuccess(r)
        self.assertGreater(r["row_count"], 0)

    def test_create_data_table(self):
        self._skip_if_no_dt()
        # Reuse the source table's row struct to create a fresh, empty DataTable.
        struct_path = self.call("data_table_actions", "ue_get_column_names",
                                asset_path=self._dt_path)["row_struct"]
        new_path = f"{TEST_ROOT}/MCP_CreatedDT"
        self.delete_asset(new_path)
        try:
            r = self.call("data_table_actions", "ue_create_data_table",
                          asset_path=new_path, row_struct_path=struct_path)
            self.assertSuccess(r)
            self.assertTrue(unreal.EditorAssetLibrary.does_asset_exist(new_path))
        finally:
            self.delete_asset(new_path)
