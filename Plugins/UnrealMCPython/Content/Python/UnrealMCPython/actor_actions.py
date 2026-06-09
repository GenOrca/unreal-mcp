# Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

import unreal
import json
import traceback

ACTOR_ACTIONS_MODULE = "actor_actions"

# Helper function (consider if it should be private or utility)
def _get_actor_by_label(actor_label: str):
    """
    Helper function to find an actor by its label.
    Returns the actor or None if not found.
    """
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = subsystem.get_all_level_actors()
    for actor in all_actors:
        if actor.get_actor_label() == actor_label:
            return actor
    return None

def ue_spawn_from_object(asset_path: str = None, location: list = None) -> str:
    """
    Spawns an actor from the specified asset path at the given location.
    Wrapped in a ScopedEditorTransaction.

    :param asset_path: Path to the asset in the Content Browser
    :param location: [x, y, z] coordinates for the actor spawn position
    :return: JSON string indicating success or failure and actor label if spawned
    """
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if location is None:
        return json.dumps({"success": False, "message": "Required parameter 'location' is missing."})

    transaction_description = "MCP: Spawn Actor from Object"
    asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
    if not asset_data:
        return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})

    if len(location) != 3:
        return json.dumps({"success": False, "message": "Invalid location format. Expected list of 3 floats."})

    try:
        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            vec = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
            asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            if not asset:
                 return json.dumps({"success": False, "message": f"Failed to load asset: {asset_path}"})

            actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_object(
                asset, vec
            )
            if actor:
                return json.dumps({"success": True, "actor_label": actor.get_actor_label(), "actor_path": actor.get_path_name()})
            else:
                return json.dumps({"success": False, "message": "Failed to spawn actor. spawn_actor_from_object returned None."})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during spawn: {str(e)}", "type": e.__name__, "traceback": traceback.format_exc()})

def ue_duplicate_selected(offset: list) -> str:
    """
    Duplicates all selected actors in the editor and applies a position offset to each duplicate.

    :param offset: [x, y, z] offset to apply to each duplicated actor.
    :return: JSON string indicating success or failure and details of duplicated actors.
    """
    if len(offset) != 3:
        return json.dumps({"success": False, "message": "Invalid offset format. Expected list of 3 floats."})

    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        selected_actors = subsystem.get_selected_level_actors()
        if not selected_actors:
            return json.dumps({"success": False, "message": "No actors selected."})

        duplicated_actors = []
        for actor in selected_actors:
            offset_vector = unreal.Vector(float(offset[0]), float(offset[1]), float(offset[2]))
            duplicated_actor = subsystem.duplicate_actor(actor, offset=offset_vector)
            if duplicated_actor:
                duplicated_actors.append(duplicated_actor.get_actor_label())

        return json.dumps({
            "success": True,
            "message": f"Duplicated {len(duplicated_actors)} actors with offset {offset}.",
            "duplicated_actors": duplicated_actors
        })
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during duplication: {e}"})

def ue_select_all() -> str:
    """
    Selects all actors in the current level.
    """
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        subsystem.select_all(unreal.EditorLevelLibrary.get_editor_world())
        return json.dumps({"success": True, "message": "All actors selected."})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during selection: {e}"})

def ue_invert_selection() -> str:
    """
    Inverts the selection of actors in the current level.
    """
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        subsystem.invert_selection(unreal.EditorLevelLibrary.get_editor_world())
        return json.dumps({"success": True, "message": "Actor selection inverted."})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during selection inversion: {e}"})

def ue_delete_by_label(actor_label: str) -> str:
    """
    Deletes an actor with the specified name from the current level.

    :param actor_label: Name of the actor to delete.
    :return: JSON string indicating success or failure.
    """
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()
        deleted_actors = []

        for actor in all_actors:
            if actor.get_actor_label() == actor_label:
                if subsystem.destroy_actor(actor):
                    deleted_actors.append(actor_label)

        if deleted_actors:
            return json.dumps({
                "success": True,
                "message": f"Deleted actors: {deleted_actors}",
                "deleted_actors": deleted_actors
            })
        else:
            return json.dumps({"success": False, "message": f"No actor found with name: {actor_label}"})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during actor deletion: {e}"})

def ue_list_all_with_locations() -> str:
    """
    Lists all actors in the current level along with their world locations.

    :return: JSON string containing actor names and locations.
    """
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()
        actor_data = []

        for actor in all_actors:
            location = actor.get_actor_location()
            actor_data.append({
                "name": actor.get_actor_label(),
                "location": [location.x, location.y, location.z]
            })

        return json.dumps({"success": True, "actors": actor_data})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during actor listing: {str(e)}", "type": e.__name__, "traceback": traceback.format_exc()})

def ue_spawn_from_class(class_path: str = None, location: list = None, rotation: list = None) -> str:
    """
    Spawns an actor from the specified class path at the given location and rotation
    using unreal.EditorLevelLibrary.spawn_actor_from_class.
    Wrapped in a ScopedEditorTransaction.

    :param class_path: Path to the actor class (e.g., "/Game/Blueprints/MyActorBP.MyActorBP_C" or "/Script/Engine.StaticMeshActor").
    :param location: [x, y, z] coordinates for the actor spawn position.
    :param rotation: Optional [pitch, yaw, roll] for the actor spawn rotation. Defaults to [0.0, 0.0, 0.0].
    :return: JSON string indicating success or failure and actor label/path if spawned.
    """
    if class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'class_path' is missing."})
    if location is None:
        return json.dumps({"success": False, "message": "Required parameter 'location' is missing."})

    transaction_description = "MCP: Spawn Actor from Class (EditorLevelLibrary)"
    if rotation is None:
        rotation = [0.0, 0.0, 0.0]

    if len(location) != 3:
        return json.dumps({"success": False, "message": "Invalid location format. Expected list of 3 floats."})
    if len(rotation) != 3:
        return json.dumps({"success": False, "message": "Invalid rotation format. Expected list of 3 floats."})

    try:
        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            actor_class = unreal.load_class(None, class_path)
            
            if not actor_class:
                return json.dumps({"success": False, "message": f"Failed to load actor class from path: {class_path}. Ensure it's a valid class path (e.g., with _C for Blueprints or /Script/ for native classes)."})

            vec_location = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
            rot_rotation = unreal.Rotator(float(rotation[2]), float(rotation[0]), float(rotation[1]))

            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                actor_class,
                vec_location,
                rot_rotation
            )

            if actor:
                return json.dumps({
                    "success": True, 
                    "actor_label": actor.get_actor_label(), 
                    "actor_path": actor.get_path_name()
                })
            else:
                return json.dumps({"success": False, "message": "Failed to spawn actor using EditorLevelLibrary.spawn_actor_from_class. The function returned None."})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during spawn_actor_from_class (EditorLevelLibrary): {str(e)}", "type": e.__name__, "traceback": traceback.format_exc()})

def ue_get_all_details() -> str:
    """
    Lists all actors in the current level with detailed information including
    label, class, location, rotation, and world-space bounding box.

    :return: JSON string containing a list of actor details.
    """
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()
        actors_details = []

        for actor in all_actors:
            loc = actor.get_actor_location()
            rot = actor.get_actor_rotation()
            
            bounds_origin, bounds_extent = actor.get_actor_bounds(False)

            detail = {
                "label": actor.get_actor_label(),
                "class": actor.get_class().get_path_name(),
                "location": [loc.x, loc.y, loc.z],
                "rotation": [rot.pitch, rot.yaw, rot.roll],
                "world_bounds_origin": [bounds_origin.x, bounds_origin.y, bounds_origin.z],
                "world_bounds_extent": [bounds_extent.x, bounds_extent.y, bounds_extent.z],
                "world_dimensions": [bounds_extent.x * 2, bounds_extent.y * 2, bounds_extent.z * 2]
            }
            
            if isinstance(actor, unreal.StaticMeshActor):
                sm_component = actor.static_mesh_component
                if hasattr(actor, 'get_static_mesh_component'):
                    sm_component = actor.get_static_mesh_component()

                if sm_component and sm_component.static_mesh:
                    detail["static_mesh_asset_path"] = sm_component.static_mesh.get_path_name()

            actors_details.append(detail)

        return json.dumps({"success": True, "actors": actors_details})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error listing all actors details: {str(e)}", "type": e.__name__, "traceback": traceback.format_exc()})

def ue_set_transform(actor_label: str = None, location: list = None, rotation: list = None, scale: list = None) -> str:
    """
    Sets the transform (location, rotation, scale) of a specified actor.
    Any component of the transform not provided will remain unchanged.
    This operation is wrapped in a ScopedEditorTransaction.
    """
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})

    transaction_description = f"MCP: Set Transform for actor {actor_label}"
    try:
        actor_to_modify = _get_actor_by_label(actor_label)
        if not actor_to_modify:
            return json.dumps({"success": False, "message": f"Actor with label \'{actor_label}\' not found."})

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            modified_properties = []
            if location is not None:
                if len(location) == 3:
                    new_loc = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
                    actor_to_modify.set_actor_location(new_loc, False, False) # bSweep, bTeleport
                    modified_properties.append("location")
                else:
                    return json.dumps({"success": False, "message": "Invalid location format. Expected list of 3 floats."})

            if rotation is not None:
                if len(rotation) == 3:
                    new_rot = unreal.Rotator(float(rotation[2]), float(rotation[0]), float(rotation[1]))
                    actor_to_modify.set_actor_rotation(new_rot, False) # bTeleport
                    modified_properties.append("rotation")
                else:
                    return json.dumps({"success": False, "message": "Invalid rotation format. Expected list of 3 floats."})

            if scale is not None:
                if len(scale) == 3:
                    new_scale = unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2]))
                    actor_to_modify.set_actor_scale3d(new_scale)
                    modified_properties.append("scale")
                else:
                    return json.dumps({"success": False, "message": "Invalid scale format. Expected list of 3 floats."})
            
            if not modified_properties:
                return json.dumps({"success": True, "message": f"No transform properties provided for actor \'{actor_label}\'. Actor was not modified."})

            return json.dumps({"success": True, "message": f"Actor \'{actor_label}\' transform updated for: {', '.join(modified_properties)}."})

    except Exception as e:
        return json.dumps({"success": False, "message": f"Error setting transform for actor \'{actor_label}\': {str(e)}", "type": e.__name__, "traceback": traceback.format_exc()})

def ue_set_location(actor_label: str = None, location: list = None) -> str:
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    if location is None:
        return json.dumps({"success": False, "message": "Required parameter 'location' is missing."})
    return ue_set_transform(actor_label=actor_label, location=location)

def ue_set_rotation(actor_label: str = None, rotation: list = None) -> str:
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    if rotation is None:
        return json.dumps({"success": False, "message": "Required parameter 'rotation' is missing."})
    return ue_set_transform(actor_label=actor_label, rotation=rotation)

def ue_set_scale(actor_label: str = None, scale: list = None) -> str:
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    if scale is None:
        return json.dumps({"success": False, "message": "Required parameter 'scale' is missing."})
    return ue_set_transform(actor_label=actor_label, scale=scale)

def ue_line_trace(
    ray_start: list = None,
    ray_end: list = None,
    trace_channel: str = 'Visibility',
    actors_to_ignore_labels: list = None,
    trace_complex: bool = True
) -> str:
    """
    Performs a line trace (raycast) and returns hit information without spawning anything.

    :param ray_start: [x, y, z] start of the ray.
    :param ray_end: [x, y, z] end of the ray.
    :param trace_channel: 'Visibility' or 'Camera'. Defaults to 'Visibility'.
    :param actors_to_ignore_labels: Optional list of actor labels to ignore.
    :param trace_complex: Whether to use complex collision. Defaults to True.
    :return: JSON string with hit details.
    """
    if ray_start is None:
        return json.dumps({"success": False, "message": "Required parameter 'ray_start' is missing."})
    if ray_end is None:
        return json.dumps({"success": False, "message": "Required parameter 'ray_end' is missing."})

    if len(ray_start) != 3 or len(ray_end) != 3:
        return json.dumps({"success": False, "message": "Invalid vector format. Expected lists of 3 floats."})

    try:
        start_loc = unreal.Vector(float(ray_start[0]), float(ray_start[1]), float(ray_start[2]))
        end_loc = unreal.Vector(float(ray_end[0]), float(ray_end[1]), float(ray_end[2]))

        actors_to_ignore_objects = []
        if actors_to_ignore_labels:
            for label in actors_to_ignore_labels:
                actor = _get_actor_by_label(label)
                if actor:
                    actors_to_ignore_objects.append(actor)

        trace_type_query = unreal.TraceTypeQuery.TRACE_TYPE_QUERY1
        if trace_channel.lower() == 'camera':
            trace_type_query = unreal.TraceTypeQuery.TRACE_TYPE_QUERY2

        hit_result = unreal.SystemLibrary.line_trace_single(
            world_context_object=unreal.EditorLevelLibrary.get_editor_world(),
            start=start_loc,
            end=end_loc,
            trace_channel=trace_type_query,
            trace_complex=trace_complex,
            actors_to_ignore=actors_to_ignore_objects,
            draw_debug_type=unreal.DrawDebugTrace.FOR_DURATION,
            ignore_self=True
        )

        if not hit_result:
            return json.dumps({"success": True, "hit": False, "message": "Raycast did not hit any surface."})

        (
            blocking_hit,
            initial_overlap,
            time,
            distance,
            location,
            impact_point,
            normal,
            impact_normal,
            phys_mat,
            hit_actor,
            hit_component,
            hit_bone_name,
            bone_name,
            hit_item,
            element_index,
            face_index,
            trace_start,
            trace_end
        ) = hit_result.to_tuple()

        if not blocking_hit:
            return json.dumps({"success": True, "hit": False, "message": "Raycast did not hit any blocking surface."})

        result = {
            "success": True,
            "hit": True,
            "location": [location.x, location.y, location.z],
            "impact_point": [impact_point.x, impact_point.y, impact_point.z],
            "normal": [normal.x, normal.y, normal.z],
            "impact_normal": [impact_normal.x, impact_normal.y, impact_normal.z],
            "distance": distance,
            "hit_actor_label": hit_actor.get_actor_label() if hit_actor else None,
            "hit_bone_name": str(hit_bone_name) if hit_bone_name and str(hit_bone_name) != "None" else None,
        }
        return json.dumps(result)

    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during line_trace: {str(e)}", "traceback": traceback.format_exc()})

def ue_spawn_on_surface_raycast(
    asset_or_class_path: str = None,
    ray_start: list = None,
    ray_end: list = None,
    is_class_path: bool = True,
    desired_rotation: list = None,
    location_offset: list = None, # New parameter
    trace_channel: str = 'Visibility',
    actors_to_ignore_labels: list = None
) -> str:
    if asset_or_class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_or_class_path' is missing."})
    if ray_start is None:
        return json.dumps({"success": False, "message": "Required parameter 'ray_start' is missing."})
    if ray_end is None:
        return json.dumps({"success": False, "message": "Required parameter 'ray_end' is missing."})

    transaction_description = f"MCP: Spawn Actor on Surface via Raycast ({asset_or_class_path})"

    if desired_rotation is None:
        desired_rotation = [0.0, 0.0, 0.0]
    if location_offset is None: # Default offset
        location_offset = [0.0, 0.0, 0.0]

    if len(ray_start) != 3 or len(ray_end) != 3 or len(desired_rotation) != 3 or len(location_offset) != 3:
        return json.dumps({"success": False, "message": "Invalid vector/rotator/offset format. Expected lists of 3 floats."})

    try:
        start_loc = unreal.Vector(float(ray_start[0]), float(ray_start[1]), float(ray_start[2]))
        end_loc = unreal.Vector(float(ray_end[0]), float(ray_end[1]), float(ray_end[2]))
        
        actors_to_ignore_objects = []
        if actors_to_ignore_labels:
            for label in actors_to_ignore_labels:
                actor = _get_actor_by_label(label)
                if actor:
                    actors_to_ignore_objects.append(actor)
        
        trace_type_query = unreal.TraceTypeQuery.TRACE_TYPE_QUERY1
        if trace_channel.lower() == 'camera':
            trace_type_query = unreal.TraceTypeQuery.TRACE_TYPE_QUERY2

        hit_result = unreal.SystemLibrary.line_trace_single(
            world_context_object=unreal.EditorLevelLibrary.get_editor_world(),
            start=start_loc,
            end=end_loc,
            trace_channel=trace_type_query, 
            trace_complex=True,
            actors_to_ignore=actors_to_ignore_objects,
            draw_debug_type=unreal.DrawDebugTrace.FOR_DURATION,
            ignore_self=True
        )

        if not hit_result:
            return json.dumps({"success": False, "message": "Raycast did not hit any surface."})

        (
            blocking_hit,
            initial_overlap,
            time,
            distance,
            location,
            impact_point,
            normal,
            impact_normal,
            phys_mat,
            hit_actor,
            hit_component,
            hit_bone_name,
            bone_name,
            hit_item,
            element_index,
            face_index,
            trace_start,
            trace_end
        ) = hit_result.to_tuple()
        
        if not blocking_hit:
            return json.dumps({"success": False, "message": "Raycast did not hit any blocking surface."})

        spawn_location = location
        # Apply location offset
        spawn_location.x += float(location_offset[0])
        spawn_location.y += float(location_offset[1])
        spawn_location.z += float(location_offset[2])

        # Apply rotation final
        spawn_rotation_final = unreal.Rotator(float(desired_rotation[2]), float(desired_rotation[0]), float(desired_rotation[1]))

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            actor_spawned = None
            if is_class_path:
                actor_class = unreal.load_class(None, asset_or_class_path)
                if not actor_class:
                    return json.dumps({"success": False, "message": f"Failed to load actor class: {asset_or_class_path}"})
                actor_spawned = unreal.EditorLevelLibrary.spawn_actor_from_class(actor_class, spawn_location, spawn_rotation_final)
            else:
                asset = unreal.EditorAssetLibrary.load_asset(asset_or_class_path)
                if not asset:
                    return json.dumps({"success": False, "message": f"Failed to load asset: {asset_or_class_path}"})
                actor_spawned = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_object(asset, spawn_location)

            if actor_spawned:
                return json.dumps({
                    "success": True, 
                    "actor_label": actor_spawned.get_actor_label(), 
                    "actor_path": actor_spawned.get_path_name(),
                    "location": [spawn_location.x, spawn_location.y, spawn_location.z],
                    "rotation": [spawn_rotation_final.pitch, spawn_rotation_final.yaw, spawn_rotation_final.roll],
                })
            else:
                return json.dumps({"success": False, "message": "Failed to spawn actor after raycast hit."})

    except Exception as e:
        return json.dumps({"success": False, "message": f"Error during spawn_actor_on_surface_with_raycast: {str(e)}", "traceback": traceback.format_exc()})

def _serialize_ue_value(value):
    """Convert an Unreal Engine value to a JSON-safe Python type."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, unreal.Vector):
        return [value.x, value.y, value.z]
    if isinstance(value, unreal.Rotator):
        return [value.pitch, value.yaw, value.roll]
    if isinstance(value, unreal.LinearColor):
        return [value.r, value.g, value.b, value.a]
    if isinstance(value, unreal.Name):
        return str(value)
    if isinstance(value, unreal.Text):
        return str(value)
    # Fallback for enums and other types
    return str(value)

def _convert_value_for_property(current_value, new_value):
    """Convert a JSON value to the appropriate Unreal type based on the current property value's type."""
    if isinstance(current_value, unreal.Vector):
        if isinstance(new_value, (list, tuple)) and len(new_value) == 3:
            return unreal.Vector(float(new_value[0]), float(new_value[1]), float(new_value[2]))
    elif isinstance(current_value, unreal.Rotator):
        if isinstance(new_value, (list, tuple)) and len(new_value) == 3:
            return unreal.Rotator(float(new_value[0]), float(new_value[1]), float(new_value[2]))
    elif isinstance(current_value, unreal.LinearColor):
        if isinstance(new_value, (list, tuple)) and len(new_value) == 4:
            return unreal.LinearColor(float(new_value[0]), float(new_value[1]), float(new_value[2]), float(new_value[3]))
    elif isinstance(current_value, unreal.Name):
        return unreal.Name(str(new_value))
    elif isinstance(current_value, bool):
        return bool(new_value)
    elif isinstance(current_value, int):
        return int(new_value)
    elif isinstance(current_value, float):
        return float(new_value)
    elif isinstance(current_value, str):
        return str(new_value)
    # Fallback: return as-is and let UE attempt conversion
    return new_value

def ue_get_property(actor_label: str = None, property_name: str = None) -> str:
    """
    Gets a property value from an actor using get_editor_property().

    :param actor_label: Label of the actor to query.
    :param property_name: UE property name to get.
    :return: JSON string with the property value.
    """
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    if property_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'property_name' is missing."})

    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor with label '{actor_label}' not found."})

        value = actor.get_editor_property(property_name)
        serialized = _serialize_ue_value(value)

        result = {"success": True, "property_name": property_name, "value": serialized}
        # Add type hint when fallback string conversion was used
        if not isinstance(value, (type(None), bool, int, float, str)) and isinstance(serialized, str):
            if not isinstance(value, (unreal.Vector, unreal.Rotator, unreal.LinearColor, unreal.Name, unreal.Text)):
                result["value_type"] = type(value).__name__
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error getting property '{property_name}' on actor '{actor_label}': {str(e)}", "type": type(e).__name__, "traceback": traceback.format_exc()})

def ue_set_property(actor_label: str = None, property_name: str = None, value=None) -> str:
    """
    Sets a property value on an actor using set_editor_property().
    Wrapped in a ScopedEditorTransaction for Undo support.

    :param actor_label: Label of the actor to modify.
    :param property_name: UE property name to set.
    :param value: The value to set (str, int, float, bool, list, or None).
    :return: JSON string indicating success or failure.
    """
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    if property_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'property_name' is missing."})

    transaction_description = f"MCP: Set Property '{property_name}' on actor '{actor_label}'"
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor with label '{actor_label}' not found."})

        # Try to read current value to determine the target type
        try:
            current_value = actor.get_editor_property(property_name)
            converted_value = _convert_value_for_property(current_value, value)
        except Exception:
            # If we can't read the current value, pass the raw value through
            converted_value = value

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            actor.set_editor_property(property_name, converted_value)

        return json.dumps({"success": True, "message": f"Property '{property_name}' set on actor '{actor_label}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": f"Error setting property '{property_name}' on actor '{actor_label}': {str(e)}", "type": type(e).__name__, "traceback": traceback.format_exc()})

def ue_get_in_view_frustum() -> str:
    """
    Retrieves a list of actors that are potentially visible within the active editor viewport's frustum.

    This function performs an *approximate* frustum check using a sphere-cone intersection test:
    - Actors are represented by their bounding spheres.
    - The view frustum is approximated as a cone based on the camera's vertical FOV.
    - Camera location and rotation are fetched using `unreal.UnrealEditorSubsystem().get_level_viewport_camera_info()`.
    - FOV, Aspect ratio, near plane, and far plane are based on defaults as they cannot be reliably queried
      through the subsystem directly. This means actors visible in the horizontal periphery of a wide viewport
      or very close/far might be misclassified.

    :return: JSON string containing a list of potentially visible actor details or an error message.
    """
    try:
        cam_loc = None
        cam_rot = None
        # Default values. FOV is not returned by UnrealEditorSubsystem.get_level_viewport_camera_info()
        v_fov_degrees = 60.0      # Default Vertical FOV
        aspect_ratio = 16.0 / 9.0 # Default aspect ratio
        near_plane = 10.0         # Default near clip plane
        far_plane = 100000.0      # Default far clip plane

        # Get core camera info using UnrealEditorSubsystem
        try:
            editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
            if not editor_subsystem:
                return json.dumps({"success": False, "message": "Failed to get UnrealEditorSubsystem."})
            
            camera_info = editor_subsystem.get_level_viewport_camera_info()
            if camera_info:
                cam_loc, cam_rot = camera_info
            else:
                return json.dumps({"success": False, "message": "Failed to obtain camera info from UnrealEditorSubsystem."})

        except Exception as e:
            return json.dumps({"success": False, "message": f"Failed to obtain essential camera info from UnrealEditorSubsystem: {e}"})

        if cam_loc is None or cam_rot is None:
            return json.dumps({"success": False, "message": "Failed to obtain essential camera location and rotation from UnrealEditorSubsystem."})

        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        all_actors = actor_subsystem.get_all_level_actors()
        visible_actors_details = []

        cam_forward_vec = cam_rot.get_forward_vector()
        v_fov_rad = unreal.MathLibrary.degrees_to_radians(v_fov_degrees)

        for actor in all_actors:
            if not actor: continue

            bounds_origin, bounds_extent = actor.get_actor_bounds(False)
            actor_bounding_radius = bounds_extent.length()
            
            vec_to_actor_center = bounds_origin - cam_loc
            dist_to_actor_center = vec_to_actor_center.length()

            sphere_closest_to_cam = dist_to_actor_center - actor_bounding_radius
            sphere_farthest_from_cam = dist_to_actor_center + actor_bounding_radius

            if sphere_farthest_from_cam < near_plane or sphere_closest_to_cam > far_plane:
                continue

            if dist_to_actor_center <= actor_bounding_radius:
                pass
            elif dist_to_actor_center > 0:
                vec_to_actor_center_normalized = vec_to_actor_center.normal()
                dot_product = cam_forward_vec.dot(vec_to_actor_center_normalized)
                dot_product_clamped = unreal.MathLibrary.clamp(dot_product, -1.0, 1.0)
                angle_to_actor_center_rad = unreal.MathLibrary.acos(dot_product_clamped)

                if dist_to_actor_center > actor_bounding_radius:
                    asin_arg = unreal.MathLibrary.clamp(actor_bounding_radius / dist_to_actor_center, -1.0, 1.0)
                    angular_radius_of_sphere_rad = unreal.MathLibrary.asin(asin_arg)
                else:
                    angular_radius_of_sphere_rad = unreal.MathLibrary.PI

                if angle_to_actor_center_rad > (v_fov_rad / 2.0) + angular_radius_of_sphere_rad:
                    continue
            else:
                pass

            loc = actor.get_actor_location()
            rot = actor.get_actor_rotation()
            actor_details_dict = {
                "label": actor.get_actor_label(),
                "class": actor.get_class().get_path_name(),
                "location": [loc.x, loc.y, loc.z],
                "rotation": [rot.pitch, rot.yaw, rot.roll],
                "world_bounds_origin": [bounds_origin.x, bounds_origin.y, bounds_origin.z],
                "world_bounds_extent": [bounds_extent.x, bounds_extent.y, bounds_extent.z]
            }
            if isinstance(actor, unreal.StaticMeshActor):
                sm_component = actor.static_mesh_component
                if sm_component and sm_component.static_mesh:
                    actor_details_dict["static_mesh_asset_path"] = sm_component.static_mesh.get_path_name()
            
            visible_actors_details.append(actor_details_dict)

        return json.dumps({"success": True, "visible_actors": visible_actors_details})

    except Exception as e:
        return json.dumps({"success": False, "message": f"Error in ue_get_in_view_frustum: {str(e)}", "type": type(e).__name__})


# --- Actor hierarchy / folders / tags / components ----------------------------

def ue_attach_actor(child_label: str = None, parent_label: str = None, socket_name: str = "") -> str:
    """Attaches one actor to another (keeps world transform). Optional socket on the parent."""
    if child_label is None or parent_label is None:
        return json.dumps({"success": False, "message": "Required parameters: child_label, parent_label."})
    try:
        child = _get_actor_by_label(child_label)
        parent = _get_actor_by_label(parent_label)
        if not child:
            return json.dumps({"success": False, "message": f"Child actor not found: {child_label}"})
        if not parent:
            return json.dumps({"success": False, "message": f"Parent actor not found: {parent_label}"})
        rule = unreal.AttachmentRule.KEEP_WORLD
        child.attach_to_actor(parent, unreal.Name(socket_name), rule, rule, rule, False)
        return json.dumps({"success": True, "child": child_label, "parent": parent_label})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_detach_actor(actor_label: str = None) -> str:
    """Detaches an actor from its parent (keeps world transform)."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        rule = unreal.DetachmentRule.KEEP_WORLD
        actor.detach_from_actor(rule, rule, rule)
        return json.dumps({"success": True, "actor_label": actor_label})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_attached_actors(actor_label: str = None) -> str:
    """Lists the labels of actors attached to the given actor."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        children = [a.get_actor_label() for a in actor.get_attached_actors()]
        parent = actor.get_attach_parent_actor()
        return json.dumps({"success": True, "actor_label": actor_label,
                           "attached": children,
                           "parent": parent.get_actor_label() if parent else None})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_actor_folder(actor_label: str = None, folder_path: str = None) -> str:
    """Sets the World Outliner folder path of an actor."""
    if actor_label is None or folder_path is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, folder_path."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        actor.set_folder_path(unreal.Name(folder_path))
        return json.dumps({"success": True, "actor_label": actor_label, "folder_path": folder_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_actor_folder(actor_label: str = None) -> str:
    """Returns the World Outliner folder path of an actor."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        return json.dumps({"success": True, "actor_label": actor_label,
                           "folder_path": str(actor.get_folder_path())})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_actor_components(actor_label: str = None) -> str:
    """Lists the components on an actor (name + class)."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        comps = [{"name": c.get_name(), "class": c.get_class().get_name()}
                 for c in actor.get_components_by_class(unreal.ActorComponent)]
        return json.dumps({"success": True, "actor_label": actor_label,
                           "count": len(comps), "components": comps})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_actor_tags(actor_label: str = None) -> str:
    """Returns the gameplay tags (Actor.Tags) of an actor."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        return json.dumps({"success": True, "actor_label": actor_label,
                           "tags": [str(t) for t in actor.tags]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_actor_tag(actor_label: str = None, tag: str = None) -> str:
    """Adds a tag to an actor (Actor.Tags)."""
    if actor_label is None or tag is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, tag."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        tags = list(actor.tags)
        if unreal.Name(tag) not in tags:
            tags.append(unreal.Name(tag))
            actor.tags = tags
        return json.dumps({"success": True, "actor_label": actor_label,
                           "tags": [str(t) for t in actor.tags]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_actor_tag(actor_label: str = None, tag: str = None) -> str:
    """Removes a tag from an actor (Actor.Tags)."""
    if actor_label is None or tag is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, tag."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        tags = [t for t in actor.tags if str(t) != tag]
        actor.tags = tags
        return json.dumps({"success": True, "actor_label": actor_label,
                           "tags": [str(t) for t in actor.tags]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_actor_bounds(actor_label: str = None) -> str:
    """Returns an actor's world-space bounds (origin + box extent)."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        origin, extent = actor.get_actor_bounds(False)
        return json.dumps({
            "success": True, "actor_label": actor_label,
            "origin": [round(origin.x, 3), round(origin.y, 3), round(origin.z, 3)],
            "extent": [round(extent.x, 3), round(extent.y, 3), round(extent.z, 3)],
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_actors_of_class(class_path: str = None) -> str:
    """Lists labels of level actors of the given class path (e.g. '/Script/Engine.PointLight')."""
    if class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'class_path' is missing."})
    try:
        cls = unreal.load_class(None, class_path)
        if not cls:
            return json.dumps({"success": False, "message": f"Class not found: {class_path}"})
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        actors = unreal.GameplayStatics.get_all_actors_of_class(world, cls)
        return json.dumps({"success": True, "class_path": class_path,
                           "count": len(actors), "actors": [a.get_actor_label() for a in actors]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_selected_actors() -> str:
    """Lists the currently selected level actors (label + class)."""
    try:
        sel = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()
        return json.dumps({"success": True, "count": len(sel),
                           "actors": [{"label": a.get_actor_label(), "class": a.get_class().get_name()} for a in sel]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_rename_actor(actor_label: str = None, new_label: str = None) -> str:
    """Renames an actor (changes its World Outliner label)."""
    if actor_label is None or new_label is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, new_label."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        actor.set_actor_label(new_label)
        return json.dumps({"success": True, "old_label": actor_label, "new_label": actor.get_actor_label()})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_actor_hidden(actor_label: str = None, hidden: bool = None) -> str:
    """Shows/hides an actor in the editor viewport (temporary editor visibility)."""
    if actor_label is None or hidden is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, hidden."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        actor.set_is_temporarily_hidden_in_editor(bool(hidden))
        return json.dumps({"success": True, "actor_label": actor_label, "hidden": bool(hidden)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_select_actors(actor_labels: list = None) -> str:
    """Selects the given actors by label in the editor (replaces current selection)."""
    if actor_labels is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_labels' is missing."})
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        found, missing = [], []
        for label in actor_labels:
            a = _get_actor_by_label(label)
            (found.append(a) if a else missing.append(label))
        sub.set_selected_level_actors(found)
        return json.dumps({"success": True, "selected": [a.get_actor_label() for a in found], "missing": missing})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_transform(actor_label: str = None) -> str:
    """Returns an actor's world location, rotation, and scale."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        loc = actor.get_actor_location()
        rot = actor.get_actor_rotation()
        scale = actor.get_actor_scale3d()
        return json.dumps({
            "success": True, "actor_label": actor_label,
            "location": [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)],
            "rotation": [round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3)],
            "scale": [round(scale.x, 3), round(scale.y, 3), round(scale.z, 3)],
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def _find_component_on_actor(actor, component_name):
    for c in actor.get_components_by_class(unreal.ActorComponent):
        if c.get_name() == component_name:
            return c
    return None


def ue_get_component_property(actor_label: str = None, component_name: str = None, property_name: str = None) -> str:
    """Reads a property on a named component of a live level actor."""
    if actor_label is None or component_name is None or property_name is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, component_name, property_name."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        comp = _find_component_on_actor(actor, component_name)
        if not comp:
            return json.dumps({"success": False, "message": f"Component '{component_name}' not found on '{actor_label}'."})
        value = _serialize_ue_value(comp.get_editor_property(property_name))
        return json.dumps({"success": True, "actor_label": actor_label, "component": component_name,
                           "property": property_name, "value": value})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_component_property(actor_label: str = None, component_name: str = None,
                             property_name: str = None, value=None) -> str:
    """Sets a property on a named component of a live level actor (e.g. PointLightComponent 'intensity')."""
    if actor_label is None or component_name is None or property_name is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, component_name, property_name."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        comp = _find_component_on_actor(actor, component_name)
        if not comp:
            return json.dumps({"success": False, "message": f"Component '{component_name}' not found on '{actor_label}'."})
        current = comp.get_editor_property(property_name)
        comp.set_editor_property(property_name, _convert_value_for_property(current, value))
        return json.dumps({"success": True, "actor_label": actor_label, "component": component_name,
                           "property": property_name, "value": _serialize_ue_value(comp.get_editor_property(property_name))})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_duplicate_actor(actor_label: str = None, offset: list = None) -> str:
    """Duplicates a specific actor (by label) with an optional [x,y,z] offset."""
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        actor = _get_actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        off = offset or [0.0, 0.0, 0.0]
        if len(off) != 3:
            return json.dumps({"success": False, "message": "offset must be a list of 3 floats."})
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        dup = sub.duplicate_actor(actor, offset=unreal.Vector(float(off[0]), float(off[1]), float(off[2])))
        if not dup:
            return json.dumps({"success": False, "message": "Duplication failed."})
        return json.dumps({"success": True, "source": actor_label, "duplicated": dup.get_actor_label()})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
