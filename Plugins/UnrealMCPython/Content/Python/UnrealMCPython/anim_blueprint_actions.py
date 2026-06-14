# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Python action functions for Animation Blueprint authoring in Unreal Engine.

This domain owns what is *unique* to Animation Blueprints — creating one bound to
a Skeleton, and skeleton-aware introspection. An AnimBlueprint is a UBlueprint, so
generic graph work is intentionally NOT duplicated here:
  - compile           -> use `blueprint compile_blueprint`
  - read AnimGraph     -> use `blueprint get_blueprint_graph_info` with graph_name="AnimGraph"
  - add/remove vars    -> use `blueprint add_variable` / `set_variable_flags`

AnimGraph node *authoring* (sequence players, state machines) lives in the editor-only
AnimGraph C++ module and is not exposed to Python (UAnimationGraph::Nodes is protected),
so ue_add_anim_graph_sequence_player and ue_build_anim_state_machine are backed by
dedicated MCPythonHelper C++ UFUNCTIONs.
"""
import unreal
import json
import traceback


def _split_object_path(asset_path: str):
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


def _load_anim_blueprint(asset_path: str):
    bp = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not bp:
        raise FileNotFoundError(f"AnimBlueprint not found at path: {asset_path}")
    if not isinstance(bp, unreal.AnimBlueprint):
        raise TypeError(f"Asset at {asset_path} is not an AnimBlueprint, but {type(bp).__name__}.")
    return bp


def _is_anim_instance_class(cls) -> bool:
    """True if cls is AnimInstance or a subclass — checked via its class-default object."""
    try:
        return isinstance(unreal.get_default_object(cls), unreal.AnimInstance)
    except Exception:
        return False


def ue_create_anim_blueprint(asset_path: str = None, skeleton_path: str = None,
                             parent_class_path: str = "/Script/Engine.AnimInstance") -> str:
    """Creates an Animation Blueprint bound to a Skeleton (parent defaults to AnimInstance)."""
    if asset_path is None or skeleton_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, skeleton_path."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})

        skeleton = unreal.EditorAssetLibrary.load_asset(skeleton_path)
        if not skeleton:
            return json.dumps({"success": False, "message": f"Skeleton not found: {skeleton_path}"})
        if not isinstance(skeleton, unreal.Skeleton):
            return json.dumps({"success": False,
                               "message": f"Asset at {skeleton_path} is not a Skeleton, but {type(skeleton).__name__}."})

        parent = unreal.load_class(None, parent_class_path)
        if not parent:
            return json.dumps({"success": False, "message": f"Parent class not found: {parent_class_path}"})
        if not _is_anim_instance_class(parent):
            return json.dumps({"success": False,
                               "message": f"Parent class '{parent_class_path}' is not an AnimInstance subclass."})

        name, package = _split_object_path(asset_path)
        factory = unreal.AnimBlueprintFactory()
        factory.set_editor_property("target_skeleton", skeleton)
        factory.set_editor_property("parent_class", parent)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package, unreal.AnimBlueprint, factory)
        if not bp:
            return json.dumps({"success": False, "message": f"Failed to create AnimBlueprint at {asset_path}."})
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "skeleton": skeleton.get_path_name(), "parent_class": parent_class_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_anim_blueprint_info(asset_path: str = None) -> str:
    """Returns an AnimBlueprint's target skeleton, generated class, and graph names."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp = _load_anim_blueprint(asset_path)
        bel = unreal.BlueprintEditorLibrary
        gen = bel.generated_class(bp)
        skeleton = bp.get_editor_property("target_skeleton")
        graphs = [g for g in ("AnimGraph", "EventGraph") if bel.find_graph(bp, unreal.Name(g))]
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "generated_class": gen.get_name() if gen else None,
            "target_skeleton": skeleton.get_path_name() if skeleton else None,
            "graphs": graphs,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# ─── AnimGraph node authoring (backed by the MCPythonHelper C++ AnimGraph helpers) ──

def ue_add_anim_graph_sequence_player(asset_path: str = None, anim_sequence_path: str = None,
                                      link_to_output_pose: bool = True) -> str:
    """Adds a looping Sequence Player to the AnimGraph, optionally wired to the Output Pose."""
    if asset_path is None or anim_sequence_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, anim_sequence_path."})
    try:
        bp = _load_anim_blueprint(asset_path)
        if not unreal.EditorAssetLibrary.does_asset_exist(anim_sequence_path):
            return json.dumps({"success": False, "message": f"AnimSequence not found: {anim_sequence_path}"})
        result_json = unreal.MCPythonHelper.add_anim_graph_sequence_player(
            bp, anim_sequence_path, link_to_output_pose)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_build_anim_state_machine(asset_path: str = None, spec: dict = None) -> str:
    """Builds an arbitrary AnimGraph state machine from a spec: states[{name,anim?}], entry?, transitions[{from,to,var?,op?,value?}]."""
    if asset_path is None or spec is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, spec."})
    try:
        bp = _load_anim_blueprint(asset_path)
        states = spec.get("states") or []
        if not states:
            return json.dumps({"success": False, "message": "spec.states must be a non-empty list."})
        # Validate referenced anims up front (clearer error than a C++ load failure).
        for s in states:
            anim = s.get("anim")
            if anim and not unreal.EditorAssetLibrary.does_asset_exist(anim):
                return json.dumps({"success": False,
                                   "message": f"State '{s.get('name')}': AnimSequence not found: {anim}"})
        # Auto-create every float variable referenced by a transition rule.
        transitions = spec.get("transitions") or []
        needed_vars = {t["var"] for t in transitions if t.get("var")}
        if needed_vars:
            bel = unreal.BlueprintEditorLibrary
            pin = bel.get_basic_type_by_name(unreal.Name("real"))
            for v in needed_vars:
                bel.add_member_variable(bp, unreal.Name(v), pin)  # no-op if it already exists
            bel.compile_blueprint(bp)
        result_json = unreal.MCPythonHelper.build_anim_state_machine(bp, json.dumps(spec))
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
