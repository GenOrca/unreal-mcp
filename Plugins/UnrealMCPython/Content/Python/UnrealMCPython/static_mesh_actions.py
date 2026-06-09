# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Python action functions for StaticMesh assets (info, materials, collision)."""
import unreal
import json
import traceback

SMS = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

_SHAPES = {
    "BOX": unreal.ScriptCollisionShapeType.BOX,
    "SPHERE": unreal.ScriptCollisionShapeType.SPHERE,
    "CAPSULE": unreal.ScriptCollisionShapeType.CAPSULE,
    "NDOP10_X": unreal.ScriptCollisionShapeType.NDOP10_X,
    "NDOP10_Y": unreal.ScriptCollisionShapeType.NDOP10_Y,
    "NDOP10_Z": unreal.ScriptCollisionShapeType.NDOP10_Z,
    "NDOP18": unreal.ScriptCollisionShapeType.NDOP18,
    "NDOP26": unreal.ScriptCollisionShapeType.NDOP26,
}


def _load_static_mesh(asset_path: str):
    if not asset_path:
        raise ValueError("StaticMesh path cannot be empty.")
    sm = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not sm:
        raise FileNotFoundError(f"StaticMesh not found at path: {asset_path}")
    if not isinstance(sm, unreal.StaticMesh):
        raise TypeError(f"Asset at {asset_path} is not a StaticMesh, but {type(sm).__name__}")
    return sm


def ue_get_static_mesh_info(asset_path: str = None) -> str:
    """Returns LOD/section/triangle/vertex/material counts and Nanite state of a StaticMesh."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        sm = _load_static_mesh(asset_path)
        try:
            nanite = bool(SMS.get_nanite_settings(sm).enabled)
        except Exception:
            nanite = None
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "num_lods": SMS.get_lod_count(sm),
            "num_materials": SMS.get_number_materials(sm),
            "num_sections_lod0": sm.get_num_sections(0),
            "num_triangles_lod0": sm.get_num_triangles(0),
            "num_vertices_lod0": sm.get_num_vertices(0),
            "nanite_enabled": nanite,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_static_mesh_materials(asset_path: str = None) -> str:
    """Lists the material slots of a StaticMesh (slot index + material path)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        sm = _load_static_mesh(asset_path)
        slots = []
        for i in range(SMS.get_number_materials(sm)):
            mat = sm.get_material(i)
            slots.append({"slot": i, "material": mat.get_path_name() if mat else None})
        return json.dumps({"success": True, "asset_path": asset_path,
                           "num_materials": len(slots), "materials": slots})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_static_mesh_material(asset_path: str = None, slot_index: int = None, material_path: str = None) -> str:
    """Assigns a material to a StaticMesh material slot."""
    if asset_path is None or slot_index is None or material_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, slot_index, material_path."})
    try:
        sm = _load_static_mesh(asset_path)
        if slot_index < 0 or slot_index >= SMS.get_number_materials(sm):
            return json.dumps({"success": False, "message": f"slot_index {slot_index} out of range (0..{SMS.get_number_materials(sm)-1})."})
        mat = unreal.EditorAssetLibrary.load_asset(material_path)
        if not mat or not isinstance(mat, unreal.MaterialInterface):
            return json.dumps({"success": False, "message": f"Not a material: {material_path}"})
        sm.set_material(slot_index, mat)
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
        return json.dumps({"success": True, "asset_path": asset_path, "slot": slot_index, "material": material_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_collision_info(asset_path: str = None) -> str:
    """Returns collision complexity and simple/convex collision counts of a StaticMesh."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        sm = _load_static_mesh(asset_path)
        return json.dumps({
            "success": True, "asset_path": asset_path,
            "collision_complexity": str(SMS.get_collision_complexity(sm)),
            "simple_collision_count": SMS.get_simple_collision_count(sm),
            "convex_collision_count": SMS.get_convex_collision_count(sm),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_simple_collision(asset_path: str = None, shape: str = "BOX") -> str:
    """Adds a simple collision primitive to a StaticMesh. shape: BOX, SPHERE, CAPSULE, NDOP10_X/Y/Z, NDOP18, NDOP26."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    shape_key = (shape or "BOX").upper()
    if shape_key not in _SHAPES:
        return json.dumps({"success": False, "message": f"Unknown shape '{shape}'.", "valid_shapes": list(_SHAPES)})
    try:
        sm = _load_static_mesh(asset_path)
        before = SMS.get_simple_collision_count(sm)
        SMS.add_simple_collisions(sm, _SHAPES[shape_key])
        after = SMS.get_simple_collision_count(sm)
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
        return json.dumps({"success": True, "asset_path": asset_path, "shape": shape_key,
                           "simple_collision_count": after, "added": after - before})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
