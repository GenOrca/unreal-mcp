# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Control Rig authoring: create rigs, build the element hierarchy, add RigVM
unit nodes, and recompile.

All actions require the ControlRig plugin (built-in, usually enabled by
default). The dependency is soft: actions guard at call time. Adding controls
(RigControlSettings/Value structs) is deferred to a follow-up.
"""
import unreal
import json
import traceback


def _plugin_missing():
    if not hasattr(unreal, "ControlRigBlueprint"):
        return json.dumps({"success": False,
                           "message": "Requires the ControlRig plugin. Enable it in Edit > Plugins and restart."})
    return None


def _load_rig(asset_path: str):
    rig = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not rig:
        raise FileNotFoundError(f"Control Rig not found at path: {asset_path}")
    if not isinstance(rig, unreal.ControlRigBlueprint):
        raise TypeError(f"Asset at {asset_path} is not a ControlRigBlueprint, but {type(rig).__name__}")
    return rig


def _parent_key(rig, parent_name: str, parent_type: str):
    if not parent_name:
        return unreal.RigElementKey()
    etype = {"bone": unreal.RigElementType.BONE,
             "null": unreal.RigElementType.NULL,
             "control": unreal.RigElementType.CONTROL}.get((parent_type or "bone").lower())
    if etype is None:
        raise ValueError(f"Unknown parent_type '{parent_type}' (use bone, null, or control).")
    return unreal.RigElementKey(type=etype, name=parent_name)


def ue_create_control_rig(asset_path: str = None, skeletal_mesh_path: str = None) -> str:
    """Creates a Control Rig at asset_path; with a skeletal mesh, imports its bones and sets it as preview (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        rig = unreal.ControlRigBlueprintFactory.create_new_control_rig_asset(asset_path)
        if not rig:
            return json.dumps({"success": False, "message": f"Failed to create Control Rig at {asset_path}."})
        imported = 0
        if skeletal_mesh_path:
            mesh = unreal.EditorAssetLibrary.load_asset(skeletal_mesh_path)
            if not mesh or not isinstance(mesh, unreal.SkeletalMesh):
                return json.dumps({"success": False, "message": f"Not a SkeletalMesh: {skeletal_mesh_path}"})
            # Import bones BEFORE set_preview_mesh (which itself populates the
            # hierarchy, making a later import report 0 new keys), then count
            # bones from the hierarchy so the number is reliable either way.
            rig.get_hierarchy_controller().import_bones(mesh.skeleton)
            rig.set_preview_mesh(mesh)
            imported = sum(1 for k in rig.hierarchy.get_all_keys()
                           if getattr(k.type, "name", "") == "BONE")
        rig.recompile_vm()
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "skeletal_mesh": skeletal_mesh_path, "imported_bones": imported})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_control_rig_info(asset_path: str = None) -> str:
    """Returns element counts by type and the preview mesh of a Control Rig (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        rig = _load_rig(asset_path)
        counts = {}
        names = {}
        for k in rig.hierarchy.get_all_keys():
            t = getattr(k.type, "name", str(k.type))
            counts[t] = counts.get(t, 0) + 1
            names.setdefault(t, []).append(str(k.name))
        mesh = rig.get_preview_mesh()
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "element_counts": counts,
            "elements": {t: v[:50] for t, v in names.items()},
            "preview_mesh": mesh.get_path_name() if mesh else None,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_rig_bone(asset_path: str = None, bone_name: str = None,
                    parent_name: str = "", parent_type: str = "bone",
                    location: list = None) -> str:
    """Adds a bone to a Control Rig hierarchy under an optional parent (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or bone_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, bone_name."})
    try:
        rig = _load_rig(asset_path)
        parent = _parent_key(rig, parent_name, parent_type)
        tf = unreal.Transform()
        if location:
            if len(location) != 3:
                return json.dumps({"success": False, "message": "location must be a list of 3 floats."})
            tf.translation = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
        key = rig.get_hierarchy_controller().add_bone(bone_name, parent, tf, True)
        if not str(key.name):
            return json.dumps({"success": False, "message": "add_bone returned an invalid key (bad parent?)."})
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path, "bone": str(key.name)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_rig_null(asset_path: str = None, null_name: str = None,
                    parent_name: str = "", parent_type: str = "bone",
                    location: list = None) -> str:
    """Adds a null (group transform) to a Control Rig hierarchy (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or null_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, null_name."})
    try:
        rig = _load_rig(asset_path)
        parent = _parent_key(rig, parent_name, parent_type)
        tf = unreal.Transform()
        if location:
            if len(location) != 3:
                return json.dumps({"success": False, "message": "location must be a list of 3 floats."})
            tf.translation = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
        key = rig.get_hierarchy_controller().add_null(null_name, parent, tf, True)
        if not str(key.name):
            return json.dumps({"success": False, "message": "add_null returned an invalid key (bad parent?)."})
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path, "null": str(key.name)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_unit_node(asset_path: str = None, struct_path: str = None,
                     method: str = "Execute", pos_x: float = 0.0, pos_y: float = 0.0) -> str:
    """Adds a RigVM unit node by struct path (e.g. '/Script/ControlRig.RigUnit_GetTransform') to a Control Rig graph (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or struct_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, struct_path."})
    try:
        rig = _load_rig(asset_path)
        controller = rig.get_controller()
        node = controller.add_unit_node_from_struct_path(
            struct_path, method or "Execute", unreal.Vector2D(float(pos_x), float(pos_y)))
        if not node:
            return json.dumps({"success": False, "message": f"Could not add unit node for '{struct_path}'."})
        rig.recompile_vm()
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "node": node.get_node_path(), "struct_path": struct_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_recompile_control_rig(asset_path: str = None) -> str:
    """Recompiles a Control Rig's VM and saves it (requires the ControlRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        rig = _load_rig(asset_path)
        rig.recompile_vm()
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
