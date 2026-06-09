# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback

ASSET_ACTIONS_MODULE = "asset_actions"

def ue_find_by_query(name : str = None, asset_type : str = None) -> str:
    """
    Returns a JSON list of asset paths under '/Game' matching the given query dict.
    Supported keys: 'name' (substring match), 'asset_type' (Unreal class name, e.g. 'StaticMesh')
    At least one of name or asset_type must be provided.
    """
    if name is None and asset_type is None: # This check is specific to this function's logic
        return json.dumps({"success": False, "message": "At least one of 'name' or 'asset_type' must be provided for ue_find_by_query.", "assets": []})

    assets = unreal.EditorAssetLibrary.list_assets('/Game', recursive=True)
    matches = []
    for asset_path in assets:
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        
        current_asset_type_str = ""
        if hasattr(asset_data, 'asset_class_str') and asset_data.asset_class_str:
            current_asset_type_str = str(asset_data.asset_class_str)
        elif hasattr(asset_data, 'asset_class') and asset_data.asset_class:
            current_asset_type_str = str(asset_data.asset_class)
        else:
            # Fallback if asset class information is not directly available or named differently
            # This might happen with certain asset types or engine versions
            # unreal.log_warning(f"Could not determine asset class for {asset_path}")
            pass # Continue checking name if type is indeterminable but name is specified

        name_match = True
        if name is not None:
            name_match = name.lower() in asset_path.lower()

        type_match = True
        if asset_type is not None:
            if not current_asset_type_str: # If type couldn't be determined, it can't match a specified type
                type_match = False
            else:
                type_match = asset_type.lower() == current_asset_type_str.lower()

        if name_match and type_match:
            matches.append(asset_path)
            
    return json.dumps({"success": True, "assets": matches, "message": f"{len(matches)} assets found matching query."})

def ue_get_static_mesh_details(asset_path: str = None) -> str:
    """
    Retrieves the bounding box and dimensions of a static mesh asset.

    :param asset_path: Path to the static mesh asset (e.g., "/Game/Meshes/MyCube.MyCube").
    :return: JSON string with asset details including bounding box and dimensions.
    """
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        static_mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not static_mesh or not isinstance(static_mesh, unreal.StaticMesh):
            return json.dumps({"success": False, "message": f"Asset is not a StaticMesh or could not be loaded: {asset_path}"})

        bounds = static_mesh.get_bounding_box()  # This returns a Box type object
        
        min_point = bounds.min
        max_point = bounds.max

        dimensions = {
            "x": max_point.x - min_point.x,
            "y": max_point.y - min_point.y,
            "z": max_point.z - min_point.z
        }

        details = {
            "asset_path": asset_path,
            "bounding_box_min": {"x": min_point.x, "y": min_point.y, "z": min_point.z},
            "bounding_box_max": {"x": max_point.x, "y": max_point.y, "z": max_point.z},
            "dimensions": dimensions
        }
        return json.dumps({"success": True, "details": details})
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_get_static_mesh_details for {asset_path}: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


# --- Asset management (EditorAssetLibrary) ------------------------------------

def ue_duplicate_asset(source_path: str = None, dest_path: str = None) -> str:
    """Duplicates an asset to a new content-browser path."""
    if source_path is None or dest_path is None:
        return json.dumps({"success": False, "message": "Required parameters: source_path, dest_path."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(source_path):
            return json.dumps({"success": False, "message": f"Source asset not found: {source_path}"})
        if unreal.EditorAssetLibrary.does_asset_exist(dest_path):
            return json.dumps({"success": False, "message": f"Destination already exists: {dest_path}"})
        new_asset = unreal.EditorAssetLibrary.duplicate_asset(source_path, dest_path)
        if not new_asset:
            return json.dumps({"success": False, "message": f"Failed to duplicate to {dest_path}."})
        return json.dumps({"success": True, "source_path": source_path, "dest_path": dest_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_rename_asset(source_path: str = None, dest_path: str = None) -> str:
    """Renames/moves an asset to a new content-browser path."""
    if source_path is None or dest_path is None:
        return json.dumps({"success": False, "message": "Required parameters: source_path, dest_path."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(source_path):
            return json.dumps({"success": False, "message": f"Source asset not found: {source_path}"})
        ok = unreal.EditorAssetLibrary.rename_asset(source_path, dest_path)
        return json.dumps({"success": bool(ok), "source_path": source_path, "dest_path": dest_path,
                           "message": "Renamed." if ok else "rename_asset returned False."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_delete_asset(asset_path: str = None) -> str:
    """Deletes an asset from the content browser."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        ok = unreal.EditorAssetLibrary.delete_asset(asset_path)
        return json.dumps({"success": bool(ok), "asset_path": asset_path,
                           "message": "Deleted." if ok else "delete_asset returned False."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_save_asset(asset_path: str = None) -> str:
    """Saves an asset to disk."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        ok = unreal.EditorAssetLibrary.save_asset(asset_path)
        return json.dumps({"success": bool(ok), "asset_path": asset_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_asset_exists(asset_path: str = None) -> str:
    """Returns whether an asset exists at the given path."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        return json.dumps({"success": True, "asset_path": asset_path,
                           "exists": bool(unreal.EditorAssetLibrary.does_asset_exist(asset_path))})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_asset_info(asset_path: str = None) -> str:
    """Returns class and package info for an asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if not data or not data.is_valid():
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "asset_name": str(data.asset_name),
            "asset_class": str(data.asset_class_path.asset_name) if hasattr(data, "asset_class_path") else "",
            "package_name": str(data.package_name),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_assets(directory_path: str = None, recursive: bool = True) -> str:
    """Lists asset paths under a content directory."""
    if directory_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'directory_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist(directory_path):
            return json.dumps({"success": False, "message": f"Directory not found: {directory_path}"})
        assets = [str(a) for a in unreal.EditorAssetLibrary.list_assets(directory_path, recursive=bool(recursive))]
        return json.dumps({"success": True, "directory_path": directory_path,
                           "count": len(assets), "assets": assets})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_find_referencers(asset_path: str = None) -> str:
    """Lists packages that reference the given asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        refs = [str(r) for r in unreal.EditorAssetLibrary.find_package_referencers_for_asset(asset_path, False)]
        return json.dumps({"success": True, "asset_path": asset_path,
                           "count": len(refs), "referencers": refs})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_make_directory(directory_path: str = None) -> str:
    """Creates a content-browser directory."""
    if directory_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'directory_path' is missing."})
    try:
        ok = unreal.EditorAssetLibrary.make_directory(directory_path)
        return json.dumps({"success": bool(ok), "directory_path": directory_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_delete_directory(directory_path: str = None) -> str:
    """Deletes a content-browser directory and its assets."""
    if directory_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'directory_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist(directory_path):
            return json.dumps({"success": False, "message": f"Directory not found: {directory_path}"})
        ok = unreal.EditorAssetLibrary.delete_directory(directory_path)
        return json.dumps({"success": bool(ok), "directory_path": directory_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
