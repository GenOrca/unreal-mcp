# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Python action functions for DataTable assets (read/write rows via DataTableFunctionLibrary)."""
import unreal
import json
import traceback

DFL = unreal.DataTableFunctionLibrary


def _load_data_table(asset_path: str):
    if not asset_path:
        raise ValueError("DataTable path cannot be empty.")
    dt = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not dt:
        raise FileNotFoundError(f"DataTable not found at path: {asset_path}")
    if not isinstance(dt, unreal.DataTable):
        raise TypeError(f"Asset at {asset_path} is not a DataTable, but {type(dt).__name__}")
    return dt


def _split_asset_path(asset_path: str):
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


def ue_create_data_table(asset_path: str = None, row_struct_path: str = None) -> str:
    """Creates a DataTable asset with the given row struct (e.g. '/Script/MyModule.MyRow' or a UserDefinedStruct path)."""
    if asset_path is None or row_struct_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, row_struct_path."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        struct = unreal.load_object(None, row_struct_path)
        if not struct:
            return json.dumps({"success": False, "message": f"Row struct not found: {row_struct_path}"})
        name, package = _split_asset_path(asset_path)
        factory = unreal.DataTableFactory()
        factory.set_editor_property("struct", struct)
        dt = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package, unreal.DataTable, factory)
        if not dt:
            return json.dumps({"success": False, "message": f"Failed to create DataTable at {asset_path}."})
        unreal.EditorAssetLibrary.save_loaded_asset(dt)
        return json.dumps({"success": True, "asset_path": asset_path, "row_struct": row_struct_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_row_names(asset_path: str = None) -> str:
    """Lists the row names of a DataTable."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        dt = _load_data_table(asset_path)
        names = [str(n) for n in DFL.get_data_table_row_names(dt)]
        return json.dumps({"success": True, "asset_path": asset_path, "count": len(names), "row_names": names})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_column_names(asset_path: str = None) -> str:
    """Lists the column (property) names of a DataTable's row struct."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        dt = _load_data_table(asset_path)
        cols = [str(c) for c in DFL.get_data_table_column_export_names(dt)]
        struct = dt.get_row_struct()
        return json.dumps({"success": True, "asset_path": asset_path, "columns": cols,
                           "row_struct": struct.get_path_name() if struct else None})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_rows_as_json(asset_path: str = None) -> str:
    """Returns all rows of a DataTable as a JSON string (under the 'rows' field)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        dt = _load_data_table(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "rows": DFL.export_data_table_to_json_string(dt)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_export_to_csv(asset_path: str = None) -> str:
    """Returns all rows of a DataTable as a CSV string."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        dt = _load_data_table(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "csv": DFL.export_data_table_to_csv_string(dt)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_does_row_exist(asset_path: str = None, row_name: str = None) -> str:
    """Returns whether a row exists in a DataTable."""
    if asset_path is None or row_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, row_name."})
    try:
        dt = _load_data_table(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path, "row_name": row_name,
                           "exists": bool(DFL.does_data_table_row_exist(dt, unreal.Name(row_name)))})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_row(asset_path: str = None, row_name: str = None) -> str:
    """Removes a row from a DataTable by name."""
    if asset_path is None or row_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, row_name."})
    try:
        dt = _load_data_table(asset_path)
        if not DFL.does_data_table_row_exist(dt, unreal.Name(row_name)):
            return json.dumps({"success": False, "message": f"Row '{row_name}' does not exist."})
        # remove_data_table_row returns None; confirm via does_row_exist.
        DFL.remove_data_table_row(dt, unreal.Name(row_name))
        still = DFL.does_data_table_row_exist(dt, unreal.Name(row_name))
        if still:
            return json.dumps({"success": False, "message": f"Row '{row_name}' was not removed."})
        unreal.EditorAssetLibrary.save_loaded_asset(dt)
        return json.dumps({"success": True, "asset_path": asset_path, "removed": row_name})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_rows_from_json(asset_path: str = None, json_string: str = None) -> str:
    """Replaces a DataTable's rows from a JSON string (array of row objects with a 'Name' key)."""
    if asset_path is None or json_string is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, json_string."})
    try:
        dt = _load_data_table(asset_path)
        # Return type varies by engine version: bool (ok) or a list of problem strings.
        result = DFL.fill_data_table_from_json_string(dt, json_string)
        if isinstance(result, bool):
            if not result:
                return json.dumps({"success": False, "message": "fill_data_table_from_json_string returned False."})
        else:
            problems = [str(p) for p in result] if result else []
            if problems:
                return json.dumps({"success": False, "message": "Fill reported problems.", "problems": problems})
        unreal.EditorAssetLibrary.save_loaded_asset(dt)
        names = [str(n) for n in DFL.get_data_table_row_names(dt)]
        return json.dumps({"success": True, "asset_path": asset_path, "row_count": len(names)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
