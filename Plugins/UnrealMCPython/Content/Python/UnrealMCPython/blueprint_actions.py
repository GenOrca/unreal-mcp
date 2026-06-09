# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback
from collections import deque


def _load_asset(asset_path, expected_class=None):
    """Load an asset and optionally verify its class. Returns (asset, error_json_str)."""
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if asset is None:
        return None, json.dumps({
            "success": False,
            "message": f"Asset not found or failed to load: {asset_path}"
        })
    if expected_class is not None and not isinstance(asset, expected_class):
        return None, json.dumps({
            "success": False,
            "message": f"Asset at '{asset_path}' is {type(asset).__name__}, expected {expected_class.__name__}."
        })
    return asset, None


# ─── Read Actions ─────────────────────────────────────────────────────────────

def ue_get_selected_bp_nodes() -> str:
    """Returns information about currently selected blueprint nodes in the editor."""
    try:
        nodes = unreal.MCPythonHelper.get_selected_blueprint_nodes()
        node_infos = []
        for node in nodes:
            node_info = {
                "name": node.get_name() if hasattr(node, 'get_name') else str(node),
                "class": node.get_class().get_name() if hasattr(node, 'get_class') else str(type(node)),
                "object_path": node.get_path_name() if hasattr(node, 'get_path_name') else None
            }
            node_infos.append(node_info)
        return json.dumps({
            "success": True,
            "selected_nodes_count": len(node_infos),
            "selected_nodes": node_infos
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_selected_bp_node_infos() -> str:
    """Returns compact blueprint node info optimized for LLM token efficiency."""
    try:
        node_infos = unreal.MCPythonHelper.get_selected_blueprint_node_infos()

        name_to_id = {}
        for i, n in enumerate(node_infos):
            name_to_id[n.node_name] = i

        def link_to_dict(link):
            d = {}
            if link.node_name in name_to_id:
                d["node"] = name_to_id[link.node_name]
            else:
                d["node"] = link.node_title
            if link.pin_name:
                d["pin"] = link.pin_name
            return d

        def pin_to_dict(pin):
            name = pin.friendly_name if pin.friendly_name else pin.pin_name
            d = {"name": name, "dir": pin.direction}
            ptype = pin.pin_type
            if pin.pin_sub_type:
                ptype += ":" + pin.pin_sub_type
            d["type"] = ptype
            if pin.default_value:
                d["default"] = pin.default_value
            linked = list(pin.linked_to)
            if linked:
                d["linked"] = [link_to_dict(l) for l in linked]
            return d

        def node_to_dict(node, idx):
            d = {"id": idx, "title": node.node_title}
            if node.node_comment:
                d["comment"] = node.node_comment
            d["pins"] = [pin_to_dict(p) for p in node.pins]
            return d

        nodes = [node_to_dict(n, i) for i, n in enumerate(node_infos)]
        return json.dumps({
            "success": True,
            "nodes": nodes
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_blueprint_graph_info(asset_path: str = None, graph_name: str = "EventGraph") -> str:
    """Returns the full graph info for a Blueprint graph."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.get_blueprint_graph_info(bp, graph_name)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_callable_functions(asset_path: str = None, filter: str = "") -> str:
    """Lists callable functions available in a Blueprint context."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.list_callable_functions(bp, filter)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_blueprint_variables(asset_path: str = None) -> str:
    """Lists all variables defined in a Blueprint."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.list_blueprint_variables(bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# ─── Write Actions ────────────────────────────────────────────────────────────

def ue_add_blueprint_node(asset_path: str = None, graph_name: str = "EventGraph",
                          node_json: dict = None) -> str:
    """Adds a single node to a Blueprint graph."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if node_json is None:
        return json.dumps({"success": False, "message": "Required parameter 'node_json' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        node_json_str = json.dumps(node_json)
        result_json = unreal.MCPythonHelper.add_blueprint_node(bp, graph_name, node_json_str)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_connect_blueprint_pins(asset_path: str = None, graph_name: str = "EventGraph",
                              source_node: str = None, source_pin: str = None,
                              target_node: str = None, target_pin: str = None) -> str:
    """Connects two pins in a Blueprint graph."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    for name, val in [("source_node", source_node), ("source_pin", source_pin),
                      ("target_node", target_node), ("target_pin", target_pin)]:
        if val is None:
            return json.dumps({"success": False, "message": f"Required parameter '{name}' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.connect_blueprint_pins(
            bp, graph_name, source_node, source_pin, target_node, target_pin)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_blueprint_node(asset_path: str = None, graph_name: str = "EventGraph",
                             node_name: str = None) -> str:
    """Removes a node from a Blueprint graph."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if node_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'node_name' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.remove_blueprint_node(bp, graph_name, node_name)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_build_blueprint_graph(asset_path: str = None, graph_name: str = "EventGraph",
                             graph_structure: dict = None) -> str:
    """Builds a Blueprint graph from JSON adjacency list."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if graph_structure is None:
        return json.dumps({"success": False, "message": "Required parameter 'graph_structure' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        graph_json_str = json.dumps(graph_structure)
        result_json = unreal.MCPythonHelper.build_blueprint_graph(bp, graph_name, graph_json_str)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_compile_blueprint(asset_path: str = None) -> str:
    """Compiles a Blueprint and returns the result."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result_json = unreal.MCPythonHelper.compile_blueprint(bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# ─── Component Management ──────────────────────────────────────────────────────

def ue_list_blueprint_components(asset_path: str = None) -> str:
    """Lists all SCS components on a Blueprint."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        return unreal.MCPythonHelper.list_blueprint_components(bp)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_component_to_blueprint(asset_path: str = None,
                                   component_class_path: str = None,
                                   component_name: str = None,
                                   location_x: float = 0.0, location_y: float = 0.0, location_z: float = 0.0,
                                   rotation_pitch: float = 0.0, rotation_yaw: float = 0.0, rotation_roll: float = 0.0,
                                   parent_component_name: str = "") -> str:
    """Adds a component to a Blueprint's SCS."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if component_class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'component_class_path' is missing."})
    if component_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'component_name' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result = unreal.MCPythonHelper.add_component_to_blueprint(
            bp, component_class_path, component_name,
            location_x, location_y, location_z,
            rotation_pitch, rotation_yaw, rotation_roll,
            parent_component_name or ""
        )
        unreal.EditorAssetLibrary.save_asset(bp.get_path_name(), only_if_is_dirty=False)
        return result
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_component_from_blueprint(asset_path: str = None, component_name: str = None) -> str:
    """Removes a component by variable name from a Blueprint's SCS."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if component_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'component_name' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result = unreal.MCPythonHelper.remove_component_from_blueprint(bp, component_name)
        unreal.EditorAssetLibrary.save_asset(bp.get_path_name(), only_if_is_dirty=False)
        return result
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_component_property(asset_path: str = None, component_name: str = None,
                               property_name: str = None, value: str = None) -> str:
    """Sets a property on a component template in a Blueprint's SCS."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if component_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'component_name' is missing."})
    if property_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'property_name' is missing."})
    if value is None:
        return json.dumps({"success": False, "message": "Required parameter 'value' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        result = unreal.MCPythonHelper.set_component_property(bp, component_name, property_name, value)
        unreal.EditorAssetLibrary.save_asset(bp.get_path_name(), only_if_is_dirty=False)
        return result
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# ─── Graph Auto-Layout ─────────────────────────────────────────────────────────

def ue_set_blueprint_node_position(asset_path: str = None, graph_name: str = "EventGraph",
                                    node_name: str = None, pos_x: float = 0.0, pos_y: float = 0.0) -> str:
    """Sets the canvas position of a node in a Blueprint graph."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if node_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'node_name' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err
        return unreal.MCPythonHelper.set_blueprint_node_position(bp, graph_name, node_name, pos_x, pos_y)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_auto_layout_graph(asset_path: str = None, graph_name: str = "EventGraph",
                          x_step: float = 380.0, y_step: float = 200.0) -> str:
    """Auto-lays out all nodes in a Blueprint graph using DAG topological sort."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, err = _load_asset(asset_path, unreal.Blueprint)
        if err:
            return err

        graph_info_str = unreal.MCPythonHelper.get_blueprint_graph_info(bp, graph_name)
        graph_info = json.loads(graph_info_str)
        if not graph_info.get("success"):
            return graph_info_str

        nodes = graph_info.get("nodes", [])
        if not nodes:
            return json.dumps({"success": True, "message": "No nodes to lay out.", "positioned": 0})

        node_names = [n["node_name"] for n in nodes]
        name_set = set(node_names)

        in_degree = {n: 0 for n in node_names}
        successors = {n: [] for n in node_names}

        ENTRY_TYPES = {"K2Node_Event", "K2Node_CustomEvent", "K2Node_InputKey",
                       "K2Node_InputAction", "K2Node_FunctionEntry"}

        for node in nodes:
            node_name = node["node_name"]
            for pin in node.get("pins", []):
                if pin.get("direction") != "Output":
                    continue
                pin_type = pin.get("type", "")
                if pin_type not in ("exec", ""):
                    continue
                for link in pin.get("linked_to", []):
                    target = link.get("node_name", "")
                    if target in name_set and target != node_name:
                        if target not in successors[node_name]:
                            successors[node_name].append(target)
                            in_degree[target] += 1

        forced_entry = set()
        for node in nodes:
            node_class = node.get("node_class", node.get("node_name", ""))
            for et in ENTRY_TYPES:
                if et in node_class or et in node.get("node_name", ""):
                    forced_entry.add(node["node_name"])
                    break
        for node in nodes:
            n = node["node_name"]
            if in_degree[n] == 0:
                for pin in node.get("pins", []):
                    if pin.get("direction") == "Output" and pin.get("type") in ("exec", ""):
                        forced_entry.add(n)
                        break

        column = {}
        queue = deque()
        for n in node_names:
            if in_degree[n] == 0 or n in forced_entry:
                column[n] = 0
                queue.append(n)

        while queue:
            n = queue.popleft()
            for s in successors[n]:
                if column.get(s, -1) < column[n] + 1:
                    column[s] = column[n] + 1
                in_degree[s] -= 1
                if in_degree[s] <= 0 and s not in column:
                    queue.append(s)

        for n in node_names:
            if n not in column:
                column[n] = 0

        col_row = {}
        positions = {}
        for node in nodes:
            n = node["node_name"]
            c = column[n]
            r = col_row.get(c, 0)
            positions[n] = (c * x_step, r * y_step)
            col_row[c] = r + 1

        errors = []
        positioned = 0
        for n, (px, py) in positions.items():
            result_str = unreal.MCPythonHelper.set_blueprint_node_position(bp, graph_name, n, px, py)
            result = json.loads(result_str)
            if result.get("success"):
                positioned += 1
            else:
                errors.append(f"{n}: {result.get('message', '?')}")

        return json.dumps({
            "success": True,
            "positioned": positioned,
            "total": len(node_names),
            "errors": errors,
            "message": f"Auto-layout complete: {positioned}/{len(node_names)} nodes positioned.",
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_create_blueprint(asset_path: str = None, parent_class_path: str = "/Script/Engine.Actor") -> str:
    """Creates a Blueprint asset with the given parent class (default Actor)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        parent = unreal.load_class(None, parent_class_path)
        if not parent:
            return json.dumps({"success": False, "message": f"Parent class not found: {parent_class_path}"})
        asset_path = asset_path.rstrip("/")
        idx = asset_path.rfind("/")
        name, package = asset_path[idx + 1:], asset_path[:idx]
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", parent)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package, unreal.Blueprint, factory)
        if not bp:
            return json.dumps({"success": False, "message": f"Failed to create Blueprint at {asset_path}."})
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path, "parent_class": parent_class_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


_BP_VAR_TYPES = {"int", "byte", "bool", "real", "name", "string", "text"}


def ue_add_variable(asset_path: str = None, variable_name: str = None, variable_type: str = "real") -> str:
    """Adds a member variable to a Blueprint. variable_type: int, byte, bool, real (float), name, string, text."""
    if asset_path is None or variable_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, variable_name."})
    vt = (variable_type or "real").lower()
    if vt == "float":
        vt = "real"
    if vt not in _BP_VAR_TYPES:
        return json.dumps({"success": False, "message": f"Unsupported variable_type '{variable_type}'.",
                           "valid_types": sorted(_BP_VAR_TYPES | {"float"})})
    try:
        bp = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not bp or not isinstance(bp, unreal.Blueprint):
            return json.dumps({"success": False, "message": f"Not a Blueprint: {asset_path}"})
        bel = unreal.BlueprintEditorLibrary
        pin = bel.get_basic_type_by_name(unreal.Name(vt))
        ok = bel.add_member_variable(bp, unreal.Name(variable_name), pin)
        if not ok:
            return json.dumps({"success": False, "message": f"add_member_variable failed for '{variable_name}'."})
        bel.compile_blueprint(bp)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "variable_name": variable_name, "variable_type": vt})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_variable_flags(asset_path: str = None, variable_name: str = None,
                          instance_editable: bool = None, expose_on_spawn: bool = None) -> str:
    """Sets a Blueprint variable's 'Instance Editable' and/or 'Expose On Spawn' flags."""
    if asset_path is None or variable_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, variable_name."})
    if instance_editable is None and expose_on_spawn is None:
        return json.dumps({"success": False, "message": "Provide instance_editable and/or expose_on_spawn."})
    try:
        bp = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not bp or not isinstance(bp, unreal.Blueprint):
            return json.dumps({"success": False, "message": f"Not a Blueprint: {asset_path}"})
        bel = unreal.BlueprintEditorLibrary
        name = unreal.Name(variable_name)
        applied = {}
        if instance_editable is not None:
            bel.set_blueprint_variable_instance_editable(bp, name, bool(instance_editable))
            applied["instance_editable"] = bool(instance_editable)
        if expose_on_spawn is not None:
            bel.set_blueprint_variable_expose_on_spawn(bp, name, bool(expose_on_spawn))
            applied["expose_on_spawn"] = bool(expose_on_spawn)
        bel.compile_blueprint(bp)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "variable_name": variable_name, "applied": applied})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
