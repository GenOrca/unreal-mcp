# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback
from typing import List, Dict, Optional, Any # Modified import

def ue_get_selected_assets() -> str:
    """Gets the set of currently selected assets."""
    try:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()
        
        serialized_assets = []
        for asset in selected_assets:
            serialized_assets.append({
                "asset_name": asset.get_name(),
                "asset_path": asset.get_path_name(),
                "asset_class": asset.get_class().get_name(),
            })
        
        return json.dumps({"success": True, "selected_assets": serialized_assets})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)})

# Helper function to load MaterialInterface assets (can be Material or MaterialInstance)
def _load_material_interface(material_path: str):
    # Helper implementation (ensure this is robust or use existing if available)
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    if not material:
        raise FileNotFoundError(f"Material asset not found at path: {material_path}")
    if not isinstance(material, unreal.MaterialInterface): # Allows Material or MaterialInstance
        raise TypeError(f"Asset at {material_path} is not a MaterialInterface, but {type(material).__name__}")
    return material

# Helper function to load StaticMesh assets
def _load_static_mesh(mesh_path: str):
    # Helper implementation (ensure this is robust or use existing if available)
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if not mesh:
        raise FileNotFoundError(f"StaticMesh asset not found at path: {mesh_path}")
    if not isinstance(mesh, unreal.StaticMesh):
        raise TypeError(f"Asset at {mesh_path} is not a StaticMesh, but {type(mesh).__name__}")
    return mesh

# Helper function to get material paths from a mesh component
def _get_component_material_paths(component: unreal.MeshComponent) -> List[str]:
    material_paths = []
    if component:
        for i in range(component.get_num_materials()):
            material = component.get_material(i)
            if material:
                material_paths.append(material.get_path_name())
            else:
                material_paths.append("") # Represent empty slot
    return material_paths

# Helper function to get actors by their paths
def _get_actors_by_paths(actor_paths: List[str]) -> List[unreal.Actor]:
    actors = []
    all_level_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for path in actor_paths:
        actor = next((a for a in all_level_actors if a.get_path_name() == path), None)
        if actor:
            actors.append(actor)
        else:
            unreal.log_warning(f"MCP: Actor not found at path: {path}")
    return actors

# Helper to create a map of actor paths to their unique material asset paths
def _get_materials_map_for_actors(actors_list: List[unreal.Actor]) -> Dict[str, List[str]]:
    materials_map = {}
    if not actors_list:
        return materials_map
    for actor in actors_list:
        if not actor: continue
        actor_path_name = actor.get_path_name()
        actor_material_paths = set()
        mesh_components = actor.get_components_by_class(unreal.MeshComponent.static_class())
        for comp in mesh_components:
            if comp:
                for i in range(comp.get_num_materials()):
                    material = comp.get_material(i)
                    if material:
                        actor_material_paths.add(material.get_path_name())
        materials_map[actor_path_name] = sorted(list(actor_material_paths))
    return materials_map

# Helper to get static mesh path from a static mesh component
def _get_component_mesh_path(component: unreal.StaticMeshComponent) -> str:
    if component and hasattr(component, 'static_mesh') and component.static_mesh:
        return component.static_mesh.get_path_name()
    return ""

# Helper to create a map of actor paths to their unique static mesh asset paths
def _get_meshes_map_for_actors(actors_list: List[unreal.Actor]) -> Dict[str, List[str]]:
    meshes_map = {}
    if not actors_list:
        return meshes_map
    for actor in actors_list:
        if not actor: continue
        actor_path_name = actor.get_path_name()
        actor_mesh_paths = set()
        sm_components = actor.get_components_by_class(unreal.StaticMeshComponent.static_class())
        for comp in sm_components:
            mesh_path = _get_component_mesh_path(comp)
            if mesh_path:
                actor_mesh_paths.add(mesh_path)
        meshes_map[actor_path_name] = sorted(list(actor_mesh_paths))
    return meshes_map

# Helper to create a map of actor paths to their unique skeletal mesh asset paths
def _get_skeletal_meshes_map_for_actors(actors_list: List[unreal.Actor]) -> Dict[str, List[str]]:
    skeletal_meshes_map = {}
    if not actors_list:
        return skeletal_meshes_map
    for actor in actors_list:
        if not actor:
            continue
        actor_path_name = actor.get_path_name()
        actor_skel_mesh_paths = set()
        skel_components = actor.get_components_by_class(unreal.SkeletalMeshComponent.static_class())
        for comp in skel_components:
            if hasattr(comp, 'skeletal_mesh') and comp.skeletal_mesh:
                actor_skel_mesh_paths.add(comp.skeletal_mesh.get_path_name())
        skeletal_meshes_map[actor_path_name] = sorted(list(actor_skel_mesh_paths))
    return skeletal_meshes_map


# Base helper for replacing meshes
def _replace_meshes_on_actors_components_base(
    actors: List[unreal.Actor],
    mesh_to_be_replaced_path: str, # Can be empty/None to replace any mesh
    new_mesh_path: str
) -> Dict[str, Any]:
    """Base logic for replacing static meshes on components of given actors."""
    mesh_to_replace = None
    # Only load if a specific mesh is targeted for replacement
    if mesh_to_be_replaced_path and mesh_to_be_replaced_path.lower() not in ["", "none", "any"]:
        mesh_to_replace = _load_static_mesh(mesh_to_be_replaced_path) # Uses existing helper
        # If _load_static_mesh raises, it will be caught by the calling ue_ function's try-except

    new_mesh = _load_static_mesh(new_mesh_path) # Uses existing helper
    # If _load_static_mesh raises, it will be caught by the calling ue_ function's try-except

    if mesh_to_replace and new_mesh and mesh_to_replace.get_path_name() == new_mesh.get_path_name():
        return {"success": True, "message": "Mesh to be replaced is the same as the new mesh. No changes made.", "changed_actors_count": 0, "changed_components_count": 0}


    changed_actors_count = 0
    changed_components_count = 0
    details = {"actors_affected": []}

    with unreal.ScopedEditorTransaction("Replace Static Meshes on Components") as trans:
        for actor in actors:
            if not actor: continue
            actor_path = actor.get_path_name()
            actor_changed_this_iteration = False
            actor_details = {"actor_path": actor_path, "components_changed": []}
            
            static_mesh_components = actor.get_components_by_class(unreal.StaticMeshComponent.static_class())
            for component in static_mesh_components:
                if not component or component.get_owner() != actor:
                    continue
                
                component_path = component.get_path_name()
                current_mesh = component.static_mesh
                
                should_replace = False
                # Case 1: Replace any mesh (mesh_to_be_replaced_path is empty/None/Any)
                if not mesh_to_be_replaced_path or mesh_to_be_replaced_path.lower() in ["", "none", "any"]:
                    if current_mesh != new_mesh : # Avoid replacing with itself if no specific mesh to replace
                        should_replace = True
                # Case 2: Replace a specific mesh
                elif mesh_to_replace and current_mesh and current_mesh.get_path_name() == mesh_to_replace.get_path_name():
                     if current_mesh.get_path_name() != new_mesh.get_path_name(): # Don't replace if it's already the new mesh
                        should_replace = True
                # Case 3: Component has no mesh, and we want to set one (mesh_to_be_replaced_path is empty/None/Any)
                elif (not mesh_to_be_replaced_path or mesh_to_be_replaced_path.lower() in ["", "none", "any"]) and not current_mesh:
                    should_replace = True


                if should_replace:
                    if component.set_static_mesh(new_mesh):
                        changed_components_count += 1
                        actor_changed_this_iteration = True
                        actor_details["components_changed"].append({"component_path": component_path, "previous_mesh": current_mesh.get_path_name() if current_mesh else None})
                    else:
                        unreal.log_warning(f"MCP: Failed to set static mesh on component {component_path} for actor {actor_path}")
            
            if actor_changed_this_iteration:
                changed_actors_count += 1
                details["actors_affected"].append(actor_details)
            
    if changed_actors_count > 0:
        unreal.EditorLevelLibrary.refresh_all_level_editors()

    return {
        "success": True,
        "message": f"Mesh replacement processed. Actors processed: {len(actors)}.",
        "changed_actors_count": changed_actors_count,
        "changed_components_count": changed_components_count,
        "details": details
    }

def ue_replace_mtl_on_selected(material_to_be_replaced_path: str, new_material_path: str) -> str:
    try:
        material_to_replace = _load_material_interface(material_to_be_replaced_path)
        new_material = _load_material_interface(new_material_path)
        
        selected_actors = unreal.EditorLevelLibrary.get_selected_level_actors()
        if not selected_actors:
            return json.dumps({"success": False, "message": "No actors selected."})

        mesh_components = []
        for actor in selected_actors:
            components = actor.get_components_by_class(unreal.MeshComponent.static_class())
            mesh_components.extend(c for c in components if c)
        
        if not mesh_components:
            return json.dumps({"success": False, "message": "No mesh components found on selected actors."})

        initial_materials_map = {}
        for comp in mesh_components:
            initial_materials_map[comp.get_path_name()] = _get_component_material_paths(comp)

        unreal.EditorLevelLibrary.replace_mesh_components_materials(
            mesh_components, 
            material_to_replace, 
            new_material
        )

        num_components_affected = 0
        affected_component_paths = []
        for comp in mesh_components:
            current_materials = _get_component_material_paths(comp)
            original_materials = initial_materials_map.get(comp.get_path_name(), [])
            
            component_changed_here = False
            for slot_idx, original_mat_path in enumerate(original_materials):
                if original_mat_path == material_to_replace.get_path_name():
                    if slot_idx < len(current_materials) and current_materials[slot_idx] == new_material.get_path_name():
                        component_changed_here = True
                        break 
            if component_changed_here:
                num_components_affected += 1
                affected_component_paths.append(comp.get_path_name())
        
        if num_components_affected > 0:
            return json.dumps({
                "success": True, 
                "message": f"Successfully replaced material '{material_to_be_replaced_path}' with '{new_material_path}' on {num_components_affected} mesh component(s) across {len(selected_actors)} selected actor(s).",
                "affected_actors_count": len(selected_actors),
                "affected_components_count": num_components_affected,
                "affected_component_paths": affected_component_paths
            })
        else:
            return json.dumps({
                "success": False, 
                "message": f"Failed to replace material. Target material '{material_to_be_replaced_path}' not found or not replaced on any mesh components of selected actors."
            })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_replace_mtl_on_specified(actor_paths: List[str], material_to_be_replaced_path: str, new_material_path: str) -> str:
    try:
        material_to_replace = _load_material_interface(material_to_be_replaced_path)
        new_material = _load_material_interface(new_material_path)
        
        actors_to_process = _get_actors_by_paths(actor_paths)
        if not actors_to_process:
            return json.dumps({"success": False, "message": "No valid actors found from the provided paths."})

        all_mesh_components_in_actors = []
        for actor in actors_to_process:
            components = actor.get_components_by_class(unreal.MeshComponent.static_class())
            all_mesh_components_in_actors.extend(c for c in components if c)

        if not all_mesh_components_in_actors:
            return json.dumps({"success": False, "message": "No mesh components found on the specified actors."})

        initial_materials_map = {}
        for comp in all_mesh_components_in_actors:
            initial_materials_map[comp.get_path_name()] = _get_component_material_paths(comp)
        
        unreal.EditorLevelLibrary.replace_mesh_components_materials_on_actors(
            actors_to_process, 
            material_to_replace, 
            new_material
        )
        
        num_components_affected = 0
        affected_component_paths = []
        for comp in all_mesh_components_in_actors:
            current_materials = _get_component_material_paths(comp)
            original_materials = initial_materials_map.get(comp.get_path_name(), [])
            
            component_changed_here = False
            for slot_idx, original_mat_path in enumerate(original_materials):
                if original_mat_path == material_to_replace.get_path_name():
                    if slot_idx < len(current_materials) and current_materials[slot_idx] == new_material.get_path_name():
                        component_changed_here = True
                        break
            if component_changed_here:
                num_components_affected += 1
                affected_component_paths.append(comp.get_path_name())
        
        if num_components_affected > 0:
            return json.dumps({
                "success": True, 
                "message": f"Successfully replaced material '{material_to_be_replaced_path}' with '{new_material_path}' on {num_components_affected} mesh component(s) across {len(actors_to_process)} specified actor(s).",
                "affected_actors_count": len(actors_to_process),
                "affected_components_count": num_components_affected,
                "affected_component_paths": affected_component_paths
            })
        else:
            return json.dumps({
                "success": False, 
                "message": f"Failed to replace material. Target material '{material_to_be_replaced_path}' not found or not replaced on any mesh components of specified actors."
            })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_replace_mesh_on_selected(mesh_to_be_replaced_path: str, new_mesh_path: str) -> str:
    """Replaces static meshes on components of selected actors using Unreal's batch API if available."""
    try:
        # Check if mesh_to_be_replaced_path exists (if specified)
        if mesh_to_be_replaced_path and mesh_to_be_replaced_path.lower() not in ["", "none", "any"]:
            try:
                _ = _load_static_mesh(mesh_to_be_replaced_path)
            except FileNotFoundError:
                return json.dumps({
                    "success": False,
                    "message": f"The mesh_to_be_replaced_path '{mesh_to_be_replaced_path}' does not exist as a StaticMesh asset.",
                    "error_type": "MeshToReplaceNotFound"
                })
        
        selected_actors = unreal.EditorLevelLibrary.get_selected_level_actors()
        if not selected_actors:
            return json.dumps({"success": True, "message": "No actors selected.", "changed_actors_count": 0, "changed_components_count": 0})

        mesh_to_replace = None
        if mesh_to_be_replaced_path and mesh_to_be_replaced_path.lower() not in ["", "none", "any"]:
            mesh_to_replace = _load_static_mesh(mesh_to_be_replaced_path)
        new_mesh = _load_static_mesh(new_mesh_path)

        # Gather all static mesh components from selected actors
        all_mesh_components = []
        for actor in selected_actors:
            comps = actor.get_components_by_class(unreal.StaticMeshComponent.static_class())
            all_mesh_components.extend(c for c in comps if c)

        if not all_mesh_components:
            return json.dumps({"success": False, "message": "No static mesh components found on selected actors."})

        # Save initial mesh paths for change detection
        initial_meshes_map = {comp.get_path_name(): comp.static_mesh.get_path_name() if comp.static_mesh else "" for comp in all_mesh_components}

        # Use Unreal's batch API if available
        if hasattr(unreal.EditorLevelLibrary, "replace_mesh_components_meshes_on_actors"):
            unreal.EditorLevelLibrary.replace_mesh_components_meshes_on_actors(
                selected_actors,
                mesh_to_replace,
                new_mesh
            )
        else:
            # Fallback to manual replacement if batch API is not available
            for comp in all_mesh_components:
                current_mesh = comp.static_mesh
                should_replace = False
                if not mesh_to_replace:
                    if current_mesh != new_mesh:
                        should_replace = True
                elif current_mesh and current_mesh.get_path_name() == mesh_to_replace.get_path_name():
                    if current_mesh.get_path_name() != new_mesh.get_path_name():
                        should_replace = True
                elif not current_mesh and not mesh_to_replace:
                    should_replace = True
                if should_replace:
                    comp.set_static_mesh(new_mesh)

        # Detect changes
        changed_components_count = 0
        affected_component_paths = []
        for comp in all_mesh_components:
            before = initial_meshes_map.get(comp.get_path_name(), "")
            after = comp.static_mesh.get_path_name() if comp.static_mesh else ""
            if mesh_to_replace:
                if before == mesh_to_replace.get_path_name() and after == new_mesh.get_path_name():
                    changed_components_count += 1
                    affected_component_paths.append(comp.get_path_name())
            else:
                if before != after and after == new_mesh.get_path_name():
                    changed_components_count += 1
                    affected_component_paths.append(comp.get_path_name())

        if changed_components_count > 0:
            return json.dumps({
                "success": True,
                "message": f"Successfully replaced mesh on {changed_components_count} static mesh component(s) across {len(selected_actors)} selected actor(s).",
                "affected_actors_count": len(selected_actors),
                "affected_components_count": changed_components_count,
                "affected_component_paths": affected_component_paths
            })
        else:
            return json.dumps({
                "success": False,
                "message": f"Failed to replace mesh. Target mesh '{mesh_to_be_replaced_path}' not found or not replaced on any static mesh components of selected actors."
            })
    except FileNotFoundError as e:
        unreal.log_error(f"MCP: Asset loading error in ue_replace_mesh_on_selected: {e}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
    except TypeError as e:
        unreal.log_error(f"MCP: Asset type error in ue_replace_mesh_on_selected: {e}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
    except Exception as e:
        unreal.log_error(f"MCP: Error in ue_replace_mesh_on_selected: {e}\n{traceback.format_exc()}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_replace_mesh_on_specified(actor_paths: List[str], mesh_to_be_replaced_path: str, new_mesh_path: str) -> str:
    """Replaces static meshes on components of specified actors using Unreal's batch API if available."""
    try:
        # Check if mesh_to_be_replaced_path exists (if specified)
        if mesh_to_be_replaced_path and mesh_to_be_replaced_path.lower() not in ["", "none", "any"]:
            try:
                _ = _load_static_mesh(mesh_to_be_replaced_path)
            except FileNotFoundError:
                return json.dumps({
                    "success": False,
                    "message": f"The mesh_to_be_replaced_path '{mesh_to_be_replaced_path}' does not exist as a StaticMesh asset.",
                    "error_type": "MeshToReplaceNotFound"
                })
        actors_to_process = _get_actors_by_paths(actor_paths)
        if not actors_to_process:
            return json.dumps({"success": False, "message": "No valid actors found from the provided paths."})
        mesh_to_replace = None
        if mesh_to_be_replaced_path and mesh_to_be_replaced_path.lower() not in ["", "none", "any"]:
            mesh_to_replace = _load_static_mesh(mesh_to_be_replaced_path)
        new_mesh = _load_static_mesh(new_mesh_path)
        # Gather all static mesh components from specified actors
        all_mesh_components = []
        for actor in actors_to_process:
            comps = actor.get_components_by_class(unreal.StaticMeshComponent.static_class())
            all_mesh_components.extend(c for c in comps if c)
        if not all_mesh_components:
            # Get the actual actor types and names for better diagnosis
            actor_info = [{"name": actor.get_name(), "class": actor.get_class().get_name()} for actor in actors_to_process]
            actors_materials_info = _get_materials_map_for_actors(actors_to_process)
            actors_meshes_info = _get_meshes_map_for_actors(actors_to_process)
            actors_skel_meshes_info = _get_skeletal_meshes_map_for_actors(actors_to_process)
            return json.dumps({
                "success": False,
                "message": "No static mesh components found on specified actors.",
                "specified_actors_info": actor_info,
                "current_materials": actors_materials_info,
                "current_meshes": actors_meshes_info,
                "current_skeletal_meshes": actors_skel_meshes_info
            })
        # Save initial mesh paths for change detection
        initial_meshes_map = {comp.get_path_name(): comp.static_mesh.get_path_name() if comp.static_mesh else "" for comp in all_mesh_components}
        # Use Unreal's batch API if available
        if hasattr(unreal.EditorLevelLibrary, "replace_mesh_components_meshes_on_actors"):
            unreal.EditorLevelLibrary.replace_mesh_components_meshes_on_actors(
                actors_to_process,
                mesh_to_replace,
                new_mesh
            )
        else:
            # Fallback to manual replacement if batch API is not available
            for comp in all_mesh_components:
                current_mesh = comp.static_mesh
                should_replace = False
                if not mesh_to_replace:
                    if current_mesh != new_mesh:
                        should_replace = True
                elif current_mesh and current_mesh.get_path_name() == mesh_to_replace.get_path_name():
                    if current_mesh.get_path_name() != new_mesh.get_path_name():
                        should_replace = True
                elif not current_mesh and not mesh_to_replace:
                    should_replace = True
                if should_replace:
                    comp.set_static_mesh(new_mesh)
        # Detect changes
        changed_components_count = 0
        affected_component_paths = []
        unchanged_components_info = []
        for comp in all_mesh_components:
            before = initial_meshes_map.get(comp.get_path_name(), "")
            after = comp.static_mesh.get_path_name() if comp.static_mesh else ""
            owner_actor = comp.get_owner()
            owner_name = owner_actor.get_name() if owner_actor else "Unknown"
            if mesh_to_replace:
                if before == mesh_to_replace.get_path_name() and after == new_mesh.get_path_name():
                    changed_components_count += 1
                    affected_component_paths.append(comp.get_path_name())
                else:
                    is_candidate = before == mesh_to_replace.get_path_name()
                    unchanged_components_info.append({
                        "component_path": comp.get_path_name(),
                        "component_name": comp.get_name(),
                        "actor_name": owner_name,
                        "current_mesh": before,
                        "is_candidate": is_candidate,
                        "reason": (
                            "Component is a candidate for replacement (matches mesh_to_be_replaced_path) but was not changed"
                            if is_candidate else
                            ("Current mesh doesn't match the mesh to be replaced" if before != mesh_to_replace.get_path_name() else "Failed to set new mesh")
                        )
                    })
            else:
                if before != after and after == new_mesh.get_path_name():
                    changed_components_count += 1
                    affected_component_paths.append(comp.get_path_name())
                else:
                    unchanged_components_info.append({
                        "component_path": comp.get_path_name(),
                        "component_name": comp.get_name(),
                        "actor_name": owner_name,
                        "current_mesh": before,
                        "is_candidate": False,
                        "reason": "Component already has the target mesh" if before == new_mesh.get_path_name() else "Failed to set new mesh"
                    })
        unchanged_components_info = unchanged_components_info if 'unchanged_components_info' in locals() else []
        if changed_components_count > 0:
            return json.dumps({
                "success": True,
                "message": f"Successfully replaced mesh on {changed_components_count} static mesh component(s) across {len(actors_to_process)} specified actor(s).",
                "affected_actors_count": len(actors_to_process),
                "affected_components_count": changed_components_count,
                "affected_component_paths": affected_component_paths,
                "unchanged_components": unchanged_components_info
            })
        else:
            actors_materials_info = _get_materials_map_for_actors(actors_to_process)
            actors_meshes_info = _get_meshes_map_for_actors(actors_to_process)
            actors_skel_meshes_info = _get_skeletal_meshes_map_for_actors(actors_to_process)
            unchanged_components_info = unchanged_components_info if 'unchanged_components_info' in locals() else []
            return json.dumps({
                "success": False,
                "message": f"Failed to replace mesh. Target mesh '{mesh_to_be_replaced_path}' not found or not replaced on any static mesh components of specified actors.",
                "current_materials": actors_materials_info,
                "current_meshes": actors_meshes_info,
                "current_skeletal_meshes": actors_skel_meshes_info,
                "unchanged_components": unchanged_components_info
            })
    except FileNotFoundError as e:
        unreal.log_error(f"MCP: Asset loading error in ue_replace_mesh_on_specified: {e}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
    except TypeError as e:
        unreal.log_error(f"MCP: Asset type error in ue_replace_mesh_on_specified: {e}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
    except Exception as e:
        unreal.log_error(f"MCP: Error in ue_replace_mesh_on_specified: {e}\n{traceback.format_exc()}")
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_replace_selected_with_bp(blueprint_asset_path: str) -> str:
    """Replaces the currently selected actors with new actors spawned from a specified Blueprint asset path using Unreal's official API."""
    import unreal
    import json
    import traceback
    try:
        selected_actors = unreal.EditorLevelLibrary.get_selected_level_actors()
        if not selected_actors:
            return json.dumps({"success": False, "message": "No actors selected."})
        # Check if the blueprint asset exists
        blueprint = unreal.EditorAssetLibrary.load_asset(blueprint_asset_path)
        if not blueprint:
            return json.dumps({"success": False, "message": f"Blueprint asset not found at path: {blueprint_asset_path}"})
        # Use the official API
        unreal.EditorLevelLibrary.replace_selected_actors(blueprint_asset_path)
        return json.dumps({
            "success": True,
            "message": f"Replaced {len(selected_actors)} actors with Blueprint '{blueprint_asset_path}' using official API.",
            "replaced_actors_count": len(selected_actors)
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

# --- Actor merging / proxy geometry --------------------------------------------

def _actors_by_labels(labels):
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    by_label = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    found, missing = [], []
    for l in labels:
        (found.append(by_label[l]) if l in by_label else missing.append(l))
    return found, missing


def _merged_mesh_path(actor):
    try:
        mesh = actor.static_mesh_component.static_mesh
        return mesh.get_path_name().split(".")[0] if mesh else None
    except Exception:
        return None


def ue_merge_actors(actor_labels: list = None, base_package_name: str = None,
                    destroy_source_actors: bool = False) -> str:
    """Merges static mesh actors into ONE new static mesh asset + actor (geometry is baked together)."""
    if not actor_labels or base_package_name is None:
        return json.dumps({"success": False, "message": "Required: actor_labels (non-empty), base_package_name."})
    try:
        actors, missing = _actors_by_labels(actor_labels)
        if missing:
            return json.dumps({"success": False, "message": f"Actors not found: {missing}"})
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        opts = unreal.EditorScriptingMergeStaticMeshActorsOptions()
        opts.base_package_name = base_package_name
        opts.destroy_source_actors = bool(destroy_source_actors)
        merged = sms.merge_static_mesh_actors(actors, opts)
        if not merged:
            return json.dumps({"success": False, "message": "merge_static_mesh_actors returned None (are these StaticMesh actors?)."})
        return json.dumps({"success": True, "merged_actor": merged.get_actor_label(),
                           "mesh_asset": _merged_mesh_path(merged),
                           "source_destroyed": bool(destroy_source_actors)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_join_actors(actor_labels: list = None, new_actor_label: str = "") -> str:
    """Joins static mesh actors into one actor with multiple components (no new mesh asset is baked)."""
    if not actor_labels:
        return json.dumps({"success": False, "message": "Required parameter 'actor_labels' is missing."})
    try:
        actors, missing = _actors_by_labels(actor_labels)
        if missing:
            return json.dumps({"success": False, "message": f"Actors not found: {missing}"})
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        opts = unreal.EditorScriptingJoinStaticMeshActorsOptions()
        if new_actor_label:
            opts.new_actor_label = new_actor_label
        joined = sms.join_static_mesh_actors(actors, opts)
        if not joined:
            return json.dumps({"success": False, "message": "join_static_mesh_actors returned None."})
        return json.dumps({"success": True, "joined_actor": joined.get_actor_label()})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_create_proxy_actor(actor_labels: list = None, base_package_name: str = None,
                          screen_size: int = 300, destroy_source_actors: bool = False) -> str:
    """Bakes static mesh actors into ONE simplified proxy mesh (Proxy Geometry tool) and spawns it."""
    if not actor_labels or base_package_name is None:
        return json.dumps({"success": False, "message": "Required: actor_labels (non-empty), base_package_name."})
    try:
        actors, missing = _actors_by_labels(actor_labels)
        if missing:
            return json.dumps({"success": False, "message": f"Actors not found: {missing}"})
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        opts = unreal.EditorScriptingCreateProxyMeshActorOptions()
        opts.base_package_name = base_package_name
        opts.destroy_source_actors = bool(destroy_source_actors)
        settings = opts.mesh_proxy_settings
        settings.set_editor_property("screen_size", int(screen_size))
        opts.mesh_proxy_settings = settings
        proxy = sms.create_proxy_mesh_actor(actors, opts)
        if not proxy:
            return json.dumps({"success": False, "message": "create_proxy_mesh_actor returned None (ProxyLOD plugin enabled? StaticMesh actors?)."})
        return json.dumps({"success": True, "proxy_actor": proxy.get_actor_label(),
                           "mesh_asset": _merged_mesh_path(proxy),
                           "source_destroyed": bool(destroy_source_actors)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# ─── Asset editor control ─────────────────────────────────────────────────────

def ue_open_editor_for_asset(asset_path: str = None) -> str:
    """Opens the asset-specific editor (Blueprint, Material, etc.) for an asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([asset])
        return json.dumps({"success": True, "asset_path": asset_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_open_assets() -> str:
    """Lists assets that currently have an editor open."""
    try:
        assets = unreal.MCPythonHelper.get_all_edited_assets()
        open_assets = [{"asset_name": a.get_name(), "asset_path": a.get_path_name(),
                        "asset_class": a.get_class().get_name()} for a in assets if a]
        return json.dumps({"success": True, "count": len(open_assets), "open_assets": open_assets})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_close_asset_editor(asset_path: str = None) -> str:
    """Closes any open editor for the given asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not asset:
            return json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
        unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).close_all_editors_for_asset(asset)
        return json.dumps({"success": True, "asset_path": asset_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
