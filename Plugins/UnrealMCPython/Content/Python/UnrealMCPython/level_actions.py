# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback



def ue_create_level(level_path: str = None) -> str:
    """Creates a new empty level and saves it at the given content-browser path."""
    if not level_path:
        return json.dumps({"success": False, "message": "Required parameter 'level_path' is missing."})
    try:
        success = unreal.EditorLevelLibrary.new_level(level_path)
        if not success:
            return json.dumps({"success": False, "message": f"EditorLevelLibrary.new_level() returned False for '{level_path}'."})
        return json.dumps({"success": True, "level_path": level_path, "message": f"Level created at '{level_path}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_load_level(level_path: str = None) -> str:
    """Opens (loads) an existing level in the editor."""
    if not level_path:
        return json.dumps({"success": False, "message": "Required parameter 'level_path' is missing."})
    try:
        success = unreal.EditorLevelLibrary.load_level(level_path)
        if not success:
            return json.dumps({"success": False, "message": f"EditorLevelLibrary.load_level() returned False for '{level_path}'."})
        return json.dumps({"success": True, "level_path": level_path, "message": f"Level '{level_path}' loaded."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_level_actors(class_filter: str = None) -> str:
    """
    Lists all actors in the current level.
    Optional class_filter is a partial class name (e.g. 'StaticMeshActor', 'BP_Bird').
    """
    try:
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        result = []
        for actor in actors:
            class_name = actor.get_class().get_name()
            if class_filter and class_filter.lower() not in class_name.lower():
                continue
            result.append({
                "name": actor.get_name(),
                "label": actor.get_actor_label(),
                "class": class_name,
                "location": {
                    "x": actor.get_actor_location().x,
                    "y": actor.get_actor_location().y,
                    "z": actor.get_actor_location().z,
                },
                "path": actor.get_path_name(),
            })
        return json.dumps({"success": True, "actors": result, "count": len(result)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_world_settings(gravity: float = None, time_dilation: float = None) -> str:
    """
    Modifies WorldSettings of the current level.
    gravity sets GlobalGravityZ (negative = downward, e.g. -980).
    time_dilation sets the global time dilation multiplier.
    """
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        if world is None:
            return json.dumps({"success": False, "message": "No editor world available."})
        ws = world.get_world_settings()
        if ws is None:
            return json.dumps({"success": False, "message": "Could not get WorldSettings."})

        applied = {}

        if gravity is not None:
            for prop in ['global_gravity_z', 'GlobalGravityZ']:
                try:
                    # Must also enable custom gravity
                    for flag in ['global_gravity', 'bGlobalGravity', 'override_world_gravity', 'bOverrideWorldGravity']:
                        try:
                            ws.set_editor_property(flag, True)
                        except Exception:
                            pass
                    ws.set_editor_property(prop, gravity)
                    applied['gravity'] = gravity
                    break
                except Exception:
                    pass

        if time_dilation is not None:
            for prop in ['world_to_meters', 'TimeDilation', 'time_dilation']:
                try:
                    ws.set_editor_property(prop, time_dilation)
                    applied['time_dilation'] = time_dilation
                    break
                except Exception:
                    pass

        if not applied:
            return json.dumps({"success": False, "message": "No settings were applied. Check property names for this UE version."})

        unreal.EditorLevelLibrary.save_current_level()
        return json.dumps({"success": True, "applied": applied, "message": "World settings updated."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})



# --- Current level info / saving ----------------------------------------------

def ue_get_current_level_path() -> str:
    """Returns the path of the currently open editor world/level."""
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if not world:
            return json.dumps({"success": False, "message": "No editor world is open."})
        return json.dumps({"success": True, "level_path": world.get_path_name(),
                           "level_name": world.get_name()})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_save_current_level() -> str:
    """Saves the currently open level. Returns success=False for an unsaved/untitled level."""
    try:
        ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        return json.dumps({"success": bool(ok),
                           "message": "Saved current level." if ok else "save_current_level returned False (untitled or unsaved level)."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_save_all_levels() -> str:
    """Saves all dirty levels."""
    try:
        ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_all_dirty_levels()
        return json.dumps({"success": bool(ok),
                           "message": "Saved all dirty levels." if ok else "save_all_dirty_levels returned False (nothing to save)."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
