# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import os
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


# --- Dependencies + metadata tags ---------------------------------------------

def _package_of(asset_path: str) -> str:
    return asset_path.split(".")[0]


def ue_get_dependencies(asset_path: str = None) -> str:
    """Lists packages that the given asset depends on (references)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        ar = unreal.AssetRegistryHelpers.get_asset_registry()
        opt = unreal.AssetRegistryDependencyOptions(
            include_soft_package_references=True, include_hard_package_references=True)
        deps = ar.get_dependencies(unreal.Name(_package_of(asset_path)), opt) or []
        deps = [str(d) for d in deps]
        return json.dumps({"success": True, "asset_path": asset_path,
                           "count": len(deps), "dependencies": deps})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_metadata_tag(asset_path: str = None, tag: str = None) -> str:
    """Reads a metadata tag value on an asset (empty string if unset)."""
    if asset_path is None or tag is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, tag."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        return json.dumps({"success": True, "asset_path": asset_path, "tag": tag,
                           "value": unreal.EditorAssetLibrary.get_metadata_tag(asset, unreal.Name(tag))})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_metadata_tag(asset_path: str = None, tag: str = None, value: str = None) -> str:
    """Sets a metadata tag value on an asset."""
    if asset_path is None or tag is None or value is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, tag, value."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        unreal.EditorAssetLibrary.set_metadata_tag(asset, unreal.Name(tag), value)
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
        return json.dumps({"success": True, "asset_path": asset_path, "tag": tag, "value": value})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_metadata_tag(asset_path: str = None, tag: str = None) -> str:
    """Removes a metadata tag from an asset."""
    if asset_path is None or tag is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, tag."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        unreal.EditorAssetLibrary.remove_metadata_tag(asset, unreal.Name(tag))
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
        return json.dumps({"success": True, "asset_path": asset_path, "removed_tag": tag})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- File import / export (FBX, textures) --------------------------------------
# IMPORTANT: imports pin a LEGACY factory (FbxFactory / TextureFactory) on the
# AssetImportTask. Routing through Interchange (the default when no factory is
# set) crashes the editor from this TCP-handler context with a TaskGraph
# RecursionGuard assertion (re-entrant task-graph pumping inside InterchangeEngine).

def ue_import_fbx(file_path: str = None, destination_path: str = None,
                  destination_name: str = "", as_skeletal: bool = False,
                  import_materials: bool = False, import_textures: bool = False,
                  import_animations: bool = False) -> str:
    """Imports an FBX file as a Static/Skeletal mesh using the legacy FBX importer."""
    if file_path is None or destination_path is None:
        return json.dumps({"success": False, "message": "Required parameters: file_path, destination_path."})
    try:
        if not os.path.isfile(file_path):
            return json.dumps({"success": False, "message": f"File not found: {file_path}"})
        ui = unreal.FbxImportUI()
        ui.automated_import_should_detect_type = False
        ui.mesh_type_to_import = (unreal.FBXImportType.FBXIT_SKELETAL_MESH if as_skeletal
                                  else unreal.FBXImportType.FBXIT_STATIC_MESH)
        ui.import_mesh = True
        ui.import_as_skeletal = bool(as_skeletal)
        ui.import_materials = bool(import_materials)
        ui.import_textures = bool(import_textures)
        ui.import_animations = bool(import_animations)
        task = unreal.AssetImportTask()
        task.filename = file_path
        task.destination_path = destination_path
        if destination_name:
            task.destination_name = destination_name
        task.automated = True
        task.replace_existing = True
        task.save = True
        task.options = ui
        task.factory = unreal.FbxFactory()  # legacy importer — bypass Interchange (crash)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        paths = [str(p).split(".")[0] for p in task.imported_object_paths]
        if not paths:
            return json.dumps({"success": False, "message": "Import produced no assets (see Output Log)."})
        return json.dumps({"success": True, "file_path": file_path, "imported_assets": paths})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def _gltf_status_path(destination_path: str) -> str:
    safe = destination_path.strip("/").replace("/", "_").replace("\\", "_")
    return os.path.join(unreal.Paths.project_saved_dir(), f"_mcp_gltf_{safe}.json").replace("\\", "/")


def ue_import_gltf(file_path: str = None, destination_path: str = None) -> str:
    """Imports a .glb/.gltf via Interchange, deferred to the editor tick. Poll get_gltf_import_status for the result."""
    # glTF import goes through Interchange, which is async (task-graph based). Driving it
    # synchronously from the MCP game-thread task re-enters the task graph and crashes
    # (RecursionGuard assertion). There is no legacy synchronous glTF factory in UE 5.7
    # (unlike FBX), so we schedule the import on the next editor tick — outside our task —
    # and report the result via a status sidecar polled by get_gltf_import_status.
    if file_path is None or destination_path is None:
        return json.dumps({"success": False, "message": "Required parameters: file_path, destination_path."})
    try:
        if not os.path.isfile(file_path):
            return json.dumps({"success": False, "message": f"File not found: {file_path}"})
        status_path = _gltf_status_path(destination_path)
        if os.path.isfile(status_path):
            os.remove(status_path)
        unreal.EditorAssetLibrary.make_directory(destination_path)

        handle = [None]
        fired = [False]

        def _run(delta_seconds):
            if fired[0]:
                return
            fired[0] = True
            try:
                task = unreal.AssetImportTask()
                task.filename = file_path
                task.destination_path = destination_path
                task.automated = True
                task.replace_existing = True
                task.save = True
                unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                res = {"success": True}
            except Exception as e:
                res = {"success": False, "error": str(e), "traceback": traceback.format_exc()}
            try:
                with open(status_path, "w", encoding="utf-8") as f:
                    json.dump(res, f)
            except Exception:
                pass
            if handle[0] is not None:
                unreal.unregister_slate_post_tick_callback(handle[0])

        handle[0] = unreal.register_slate_post_tick_callback(_run)
        return json.dumps({"success": True, "pending": True, "destination_path": destination_path,
                           "message": "glTF import scheduled on the editor tick. Poll 'get_gltf_import_status' with this destination_path."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_gltf_import_status(destination_path: str = None) -> str:
    """Polls a scheduled glTF import; returns done + imported assets once Interchange finishes."""
    if destination_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'destination_path' is missing."})
    try:
        status_path = _gltf_status_path(destination_path)
        if not os.path.isfile(status_path):
            return json.dumps({"success": True, "done": False, "pending": True,
                               "message": "Import tick has not fired yet; retry shortly."})
        with open(status_path, encoding="utf-8") as f:
            res = json.load(f)
        if not res.get("success"):
            os.remove(status_path)
            return json.dumps({"success": False, "done": True,
                               "message": res.get("error", "glTF import failed."),
                               "traceback": res.get("traceback")})
        created = (unreal.EditorAssetLibrary.list_assets(destination_path, recursive=True)
                   if unreal.EditorAssetLibrary.does_directory_exist(destination_path) else [])
        if not created:
            # import_asset_tasks was called but Interchange is still finishing asynchronously
            return json.dumps({"success": True, "done": False, "pending": True,
                               "message": "Interchange still importing; retry shortly."})
        assets = [{"path": str(p).split(".")[0],
                   "class": str(unreal.EditorAssetLibrary.find_asset_data(p).asset_class_path.asset_name)}
                  for p in created]
        os.remove(status_path)
        return json.dumps({"success": True, "done": True, "destination_path": destination_path,
                           "imported_assets": assets, "count": len(assets)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_import_texture(file_path: str = None, destination_path: str = None,
                      destination_name: str = "") -> str:
    """Imports an image file (PNG/JPG/TGA...) as a Texture2D using the legacy texture importer."""
    if file_path is None or destination_path is None:
        return json.dumps({"success": False, "message": "Required parameters: file_path, destination_path."})
    try:
        if not os.path.isfile(file_path):
            return json.dumps({"success": False, "message": f"File not found: {file_path}"})
        task = unreal.AssetImportTask()
        task.filename = file_path
        task.destination_path = destination_path
        if destination_name:
            task.destination_name = destination_name
        task.automated = True
        task.replace_existing = True
        task.save = True
        task.factory = unreal.TextureFactory()  # legacy importer — bypass Interchange (crash)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        paths = [str(p).split(".")[0] for p in task.imported_object_paths]
        if not paths:
            return json.dumps({"success": False, "message": "Import produced no assets (see Output Log)."})
        return json.dumps({"success": True, "file_path": file_path, "imported_assets": paths})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


_FBX_EXPORTERS = {
    "StaticMesh": "StaticMeshExporterFBX",
    "SkeletalMesh": "SkeletalMeshExporterFBX",
    "AnimSequence": "AnimSequenceExporterFBX",
}


def ue_export_fbx(asset_path: str = None, file_path: str = None) -> str:
    """Exports a StaticMesh, SkeletalMesh, or AnimSequence asset to an FBX file."""
    if asset_path is None or file_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, file_path."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        cls = asset.get_class().get_name()
        exporter_name = _FBX_EXPORTERS.get(cls)
        if not exporter_name:
            return json.dumps({"success": False,
                               "message": f"Unsupported asset class '{cls}' for FBX export.",
                               "supported": list(_FBX_EXPORTERS)})
        task = unreal.AssetExportTask()
        task.object = asset
        task.filename = file_path
        task.automated = True
        task.prompt = False
        task.exporter = getattr(unreal, exporter_name)()
        task.options = unreal.FbxExportOption()
        ok = unreal.Exporter.run_asset_export_task(task)
        if not ok or not os.path.isfile(file_path):
            return json.dumps({"success": False, "message": "Export failed (see Output Log)."})
        return json.dumps({"success": True, "asset_path": asset_path, "file_path": file_path,
                           "file_size": os.path.getsize(file_path)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
