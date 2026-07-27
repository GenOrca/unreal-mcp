# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback

BT_ACTIONS_MODULE = "behavior_tree_actions"

# ─── Helpers ──────────────────────────────────────────────────────────────────

# Blackboard key type string → full class path for load_class fallback
_BB_KEY_TYPE_MAP = {
    "Bool":     "/Script/AIModule.BlackboardKeyType_Bool",
    "Int":      "/Script/AIModule.BlackboardKeyType_Int",
    "Float":    "/Script/AIModule.BlackboardKeyType_Float",
    "String":   "/Script/AIModule.BlackboardKeyType_String",
    "Name":     "/Script/AIModule.BlackboardKeyType_Name",
    "Vector":   "/Script/AIModule.BlackboardKeyType_Vector",
    "Rotator":  "/Script/AIModule.BlackboardKeyType_Rotator",
    "Object":   "/Script/AIModule.BlackboardKeyType_Object",
    "Class":    "/Script/AIModule.BlackboardKeyType_Class",
    "Enum":     "/Script/AIModule.BlackboardKeyType_Enum",
}


def _bt_node_info_to_dict(info):
    """Convert FMCPythonBTNodeInfo (C++ USTRUCT) to a Python dict."""
    d = {
        "node_name": str(info.node_name),
        "node_class": str(info.node_class),
    }
    if info.decorator_classes:
        d["decorators"] = [
            {"class": str(info.decorator_classes[i]), "name": str(info.decorator_names[i])}
            for i in range(len(info.decorator_classes))
        ]
    if info.service_classes:
        d["services"] = [
            {"class": str(info.service_classes[i]), "name": str(info.service_names[i])}
            for i in range(len(info.service_classes))
        ]
    if info.children:
        d["children"] = [_bt_node_info_to_dict(child) for child in info.children]
    return d


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


def _get_bt_blackboard(bt):
    """Get the Blackboard asset linked to a BehaviorTree (read-only)."""
    try:
        return bt.get_blackboard_asset()
    except Exception:
        pass
    for name in ['blackboard_asset', 'BlackboardAsset']:
        try:
            return bt.get_editor_property(name)
        except Exception:
            pass
    return None


def _get_node_class_name(node):
    """Get a readable class name for a BT node."""
    if node is None:
        return "None"
    return type(node).__name__


def _get_bb_key_type_name(key_type_obj):
    """Extract a human-readable type name from a Blackboard key type object."""
    if key_type_obj is None:
        return "Unknown"
    prefix = "BlackboardKeyType_"

    # Try type(obj).__name__
    class_name = type(key_type_obj).__name__
    if class_name.startswith(prefix) and len(class_name) > len(prefix):
        return class_name[len(prefix):]

    # Try get_class().get_name() (UE reflection)
    try:
        ue_class = key_type_obj.get_class()
        if ue_class:
            ue_name = str(ue_class.get_name())
            if ue_name.startswith(prefix) and len(ue_name) > len(prefix):
                return ue_name[len(prefix):]
            if ue_name != "BlackboardKeyType":
                return ue_name
    except Exception:
        pass

    # Try get_name()
    try:
        obj_name = str(key_type_obj.get_name())
        if obj_name.startswith(prefix):
            return obj_name[len(prefix):]
        if obj_name and obj_name != "None":
            return obj_name
    except Exception:
        pass

    return class_name


def _serialize_value(value):
    """Convert a UE value to a JSON-safe Python type."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, unreal.Vector):
        return [value.x, value.y, value.z]
    if isinstance(value, unreal.Rotator):
        return [value.pitch, value.yaw, value.roll]
    if isinstance(value, unreal.Name):
        return str(value)
    return str(value)


def _split_asset_path(asset_path):
    """Split '/Game/AI/BT_Enemy' into ('/Game/AI', 'BT_Enemy')."""
    parts = asset_path.rsplit('/', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return '/Game', asset_path


def _create_bb_key_type_instance(key_type):
    """Create a BlackboardKeyType instance via direct class or load_class fallback."""
    class_simple_name = "BlackboardKeyType_" + key_type
    class_path = _BB_KEY_TYPE_MAP.get(key_type)

    # Direct class access
    try:
        cls = getattr(unreal, class_simple_name, None)
        if cls is not None:
            return cls(), None
    except Exception:
        pass

    # load_class + new_object
    if class_path:
        try:
            cls = unreal.load_class(None, class_path)
            if cls is not None:
                return unreal.new_object(cls), None
        except Exception:
            pass

    return None, (
        f"Cannot create key type '{key_type}': "
        f"class '{class_simple_name}' is not accessible in this UE version's Python API."
    )


# ─── Read Actions ─────────────────────────────────────────────────────────────

def ue_list_behavior_trees() -> str:
    """Lists all Behavior Tree assets under /Game."""
    try:
        all_assets = unreal.EditorAssetLibrary.list_assets('/Game', recursive=True)

        results = []
        for asset_path in all_assets:
            try:
                asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            except Exception:
                continue

            if asset is None or not isinstance(asset, unreal.BehaviorTree):
                continue

            asset_name = str(asset_path).rsplit('/', 1)[-1].split('.')[0]
            entry = {
                "asset_path": str(asset_path),
                "asset_name": asset_name,
            }

            try:
                bb = _get_bt_blackboard(asset)
                if bb is not None:
                    entry["blackboard_path"] = bb.get_path_name()
            except Exception:
                pass
            results.append(entry)

        return json.dumps({
            "success": True,
            "behavior_trees": results,
            "count": len(results),
            "message": f"Found {len(results)} Behavior Tree asset(s)."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_list_behavior_trees: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_get_behavior_tree_structure(asset_path: str = None) -> str:
    """Returns the full tree structure of a Behavior Tree asset as JSON."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})

    try:
        bt, err = _load_asset(asset_path, unreal.BehaviorTree)
        if err:
            return err

        # Get blackboard info
        bb_path = None
        try:
            bb = _get_bt_blackboard(bt)
            if bb is not None:
                bb_path = bb.get_path_name()
        except Exception:
            pass

        # Call C++ helper — returns JSON string with full tree
        result_json = unreal.MCPythonHelper.get_behavior_tree_structure(bt)
        result = json.loads(result_json)

        if not result.get("success", False):
            return result_json

        # Merge blackboard info into the result
        result["asset_path"] = asset_path
        result["blackboard_path"] = bb_path
        result["tree"] = [result.pop("root")] if "root" in result else []
        result["message"] = f"Behavior Tree structure retrieved ({len(result['tree'])} root node(s))."

        return json.dumps(result)
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_get_behavior_tree_structure: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_get_blackboard_data(asset_path: str = None) -> str:
    """Reads all keys from a Blackboard asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})

    try:
        bb, err = _load_asset(asset_path, unreal.BlackboardData)
        if err:
            return err

        # Get parent blackboard
        parent_path = None
        for pp in ['parent', 'Parent']:
            try:
                parent = bb.get_editor_property(pp)
                if parent is not None:
                    parent_path = parent.get_path_name()
                    break
            except Exception:
                pass

        # Read keys
        keys_data = []
        for kp in ['keys', 'Keys']:
            try:
                keys = bb.get_editor_property(kp)
                if keys is not None:
                    for key in keys:
                        key_info = {}
                        for enp in ['entry_name', 'EntryName']:
                            try:
                                key_info["key_name"] = str(key.get_editor_property(enp))
                                break
                            except Exception:
                                pass

                        for ktp in ['key_type', 'KeyType']:
                            try:
                                key_type = key.get_editor_property(ktp)
                                if key_type is not None:
                                    key_info["key_type"] = _get_bb_key_type_name(key_type)
                                    break
                            except Exception:
                                pass
                        if "key_type" not in key_info:
                            key_info["key_type"] = "Unknown"

                        for isp in ['is_instance_synced', 'bIsInstanceSynced', 'instance_synced']:
                            try:
                                key_info["instance_synced"] = bool(key.get_editor_property(isp))
                                break
                            except Exception:
                                pass

                        keys_data.append(key_info)
                    break
            except Exception as keys_err:
                unreal.log_warning(f"Could not read keys with prop '{kp}': {keys_err}")

        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "parent_path": parent_path,
            "keys": keys_data,
            "key_count": len(keys_data),
            "message": f"Blackboard has {len(keys_data)} key(s)."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_get_blackboard_data: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_get_bt_node_details(asset_path: str = None, node_name: str = None) -> str:
    """Retrieves detailed properties of a specific node in a Behavior Tree."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if node_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'node_name' is missing."})

    try:
        bt, err = _load_asset(asset_path, unreal.BehaviorTree)
        if err:
            return err

        # Call C++ helper — returns JSON string with node details
        details_json = unreal.MCPythonHelper.get_behavior_tree_node_details(bt, node_name)
        return details_json
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_get_bt_node_details: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_get_selected_bt_nodes() -> str:
    """Returns details of selected nodes in the currently open BT editor."""
    try:
        result_json = unreal.MCPythonHelper.get_selected_bt_nodes()
        return result_json
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_get_selected_bt_nodes: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


# ─── Write Actions ────────────────────────────────────────────────────────────

def ue_create_behavior_tree(asset_path: str = None, blackboard_path: str = None) -> str:
    """Creates a new empty Behavior Tree asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})

    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists at '{asset_path}'."})

        package_path, asset_name = _split_asset_path(asset_path)

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        bt = None
        try:
            factory = unreal.BehaviorTreeFactory()
            bt = asset_tools.create_asset(asset_name, package_path, unreal.BehaviorTree, factory)
        except Exception:
            try:
                bt = asset_tools.create_asset(asset_name, package_path, unreal.BehaviorTree, None)
            except Exception:
                pass

        if bt is None:
            return json.dumps({"success": False, "message": f"Failed to create Behavior Tree at '{asset_path}'."})

        unreal.EditorAssetLibrary.save_asset(bt.get_path_name())

        result = {
            "success": True,
            "asset_path": bt.get_path_name(),
            "message": f"Behavior Tree created at '{bt.get_path_name()}'.",
        }

        # Link Blackboard via C++ helper
        if blackboard_path is not None:
            try:
                bb = unreal.EditorAssetLibrary.load_asset(blackboard_path)
                if bb is not None and isinstance(bb, unreal.BlackboardData):
                    linked = unreal.MCPythonHelper.set_behavior_tree_blackboard(bt, bb)
                    if linked:
                        result["blackboard_linked"] = True
                        result["blackboard_path"] = bb.get_path_name()
                        unreal.EditorAssetLibrary.save_asset(bt.get_path_name())
                    else:
                        result["blackboard_linked"] = False
                        result["blackboard_link_note"] = "Failed to link Blackboard via C++ helper."
                else:
                    result["blackboard_linked"] = False
                    result["blackboard_link_note"] = f"Blackboard not found at '{blackboard_path}'."
            except Exception as bb_err:
                result["blackboard_linked"] = False
                result["blackboard_link_note"] = f"Error linking Blackboard: {str(bb_err)}"

        return json.dumps(result)
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_create_behavior_tree: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_create_blackboard(asset_path: str = None, parent_path: str = None) -> str:
    """Creates a new Blackboard Data asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})

    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists at '{asset_path}'."})

        package_path, asset_name = _split_asset_path(asset_path)

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        bb = None
        try:
            factory = unreal.BlackboardDataFactory()
            bb = asset_tools.create_asset(asset_name, package_path, unreal.BlackboardData, factory)
        except Exception:
            try:
                bb = asset_tools.create_asset(asset_name, package_path, unreal.BlackboardData, None)
            except Exception:
                pass

        if bb is None:
            return json.dumps({"success": False, "message": f"Failed to create Blackboard at '{asset_path}'."})

        if parent_path is not None:
            try:
                parent_bb = unreal.EditorAssetLibrary.load_asset(parent_path)
                if parent_bb is not None and isinstance(parent_bb, unreal.BlackboardData):
                    for pp in ['parent', 'Parent']:
                        try:
                            bb.set_editor_property(pp, parent_bb)
                            break
                        except Exception:
                            pass
                else:
                    unreal.log_warning(f"Parent Blackboard not found or invalid: {parent_path}")
            except Exception as parent_err:
                unreal.log_warning(f"Could not set parent blackboard: {parent_err}")

        unreal.EditorAssetLibrary.save_asset(bb.get_path_name())

        return json.dumps({
            "success": True,
            "asset_path": bb.get_path_name(),
            "message": f"Blackboard created at '{bb.get_path_name()}'."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_create_blackboard: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_add_blackboard_key(asset_path: str = None, key_name: str = None,
                          key_type: str = None, instance_synced: bool = False) -> str:
    """Adds a new key to a Blackboard asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if key_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'key_name' is missing."})
    if key_type is None:
        return json.dumps({"success": False, "message": "Required parameter 'key_type' is missing."})

    if key_type not in _BB_KEY_TYPE_MAP:
        return json.dumps({
            "success": False,
            "message": f"Invalid key_type '{key_type}'. Supported types: {', '.join(_BB_KEY_TYPE_MAP.keys())}"
        })

    try:
        bb, err = _load_asset(asset_path, unreal.BlackboardData)
        if err:
            return err

        # Check if key already exists
        existing_keys = None
        for kp in ['keys', 'Keys']:
            try:
                existing_keys = bb.get_editor_property(kp)
                break
            except Exception:
                pass

        if existing_keys is not None:
            for key in existing_keys:
                for enp in ['entry_name', 'EntryName']:
                    try:
                        if str(key.get_editor_property(enp)) == key_name:
                            return json.dumps({
                                "success": False,
                                "message": f"Key '{key_name}' already exists in Blackboard."
                            })
                        break
                    except Exception:
                        pass

        # Create the new key entry
        new_entry = unreal.BlackboardEntry()

        name_set = False
        for enp in ['entry_name', 'EntryName']:
            try:
                new_entry.set_editor_property(enp, key_name)
                name_set = True
                break
            except Exception:
                pass
        if not name_set:
            return json.dumps({"success": False, "message": "Failed to set entry name on BlackboardEntry."})

        key_type_obj, key_err = _create_bb_key_type_instance(key_type)
        if key_err:
            return json.dumps({"success": False, "message": key_err})

        type_set = False
        for ktp in ['key_type', 'KeyType']:
            try:
                new_entry.set_editor_property(ktp, key_type_obj)
                type_set = True
                break
            except Exception:
                pass
        if not type_set:
            return json.dumps({
                "success": False,
                "message": f"Failed to set key type on BlackboardEntry. Key type object: {type(key_type_obj).__name__}"
            })

        for isp in ['is_instance_synced', 'bIsInstanceSynced', 'instance_synced']:
            try:
                new_entry.set_editor_property(isp, instance_synced)
                break
            except Exception:
                pass

        # Add to keys array
        added = False
        for kp in ['keys', 'Keys']:
            try:
                keys = list(bb.get_editor_property(kp) or [])
                keys.append(new_entry)
                bb.set_editor_property(kp, keys)
                added = True
                break
            except Exception:
                pass

        if not added:
            return json.dumps({"success": False, "message": "Failed to add key to Blackboard keys array."})

        unreal.EditorAssetLibrary.save_asset(bb.get_path_name())

        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "key_name": key_name,
            "key_type": key_type,
            "instance_synced": instance_synced,
            "message": f"Key '{key_name}' ({key_type}) added to Blackboard."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_add_blackboard_key: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_remove_blackboard_key(asset_path: str = None, key_name: str = None) -> str:
    """Removes a key from a Blackboard asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if key_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'key_name' is missing."})

    try:
        bb, err = _load_asset(asset_path, unreal.BlackboardData)
        if err:
            return err

        removed = False
        for kp in ['keys', 'Keys']:
            try:
                keys = bb.get_editor_property(kp)
                if keys is None or len(keys) == 0:
                    return json.dumps({"success": False, "message": "Blackboard has no keys to remove."})

                new_keys = []
                found = False
                for key in keys:
                    existing_name = None
                    for enp in ['entry_name', 'EntryName']:
                        try:
                            existing_name = str(key.get_editor_property(enp))
                            break
                        except Exception:
                            pass
                    if existing_name == key_name:
                        found = True
                    else:
                        new_keys.append(key)

                if not found:
                    return json.dumps({"success": False, "message": f"Key '{key_name}' not found in Blackboard."})

                bb.set_editor_property(kp, new_keys)
                removed = True
                break
            except Exception:
                pass

        if not removed:
            return json.dumps({"success": False, "message": "Failed to modify Blackboard keys array."})

        unreal.EditorAssetLibrary.save_asset(bb.get_path_name())

        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "key_name": key_name,
            "message": f"Key '{key_name}' removed from Blackboard."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_remove_blackboard_key: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_set_blackboard_to_behavior_tree(bt_path: str = None, bb_path: str = None) -> str:
    """Links a Blackboard asset to a Behavior Tree."""
    if bt_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'bt_path' is missing."})
    if bb_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'bb_path' is missing."})

    try:
        bt, err = _load_asset(bt_path, unreal.BehaviorTree)
        if err:
            return err

        bb, err = _load_asset(bb_path, unreal.BlackboardData)
        if err:
            return err

        # Call C++ helper to set BlackboardAsset directly
        success = unreal.MCPythonHelper.set_behavior_tree_blackboard(bt, bb)

        if success:
            unreal.EditorAssetLibrary.save_asset(bt_path)
            return json.dumps({
                "success": True,
                "bt_path": bt_path,
                "bb_path": bb_path,
                "message": "Blackboard linked to Behavior Tree successfully."
            })
        else:
            return json.dumps({
                "success": False,
                "message": "Failed to set Blackboard on Behavior Tree."
            })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_set_blackboard_to_behavior_tree: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_build_behavior_tree(asset_path: str = None, tree_structure: dict = None) -> str:
    """Builds a complete Behavior Tree from a JSON structure."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if tree_structure is None:
        return json.dumps({"success": False, "message": "Required parameter 'tree_structure' is missing."})

    try:
        bt, err = _load_asset(asset_path, unreal.BehaviorTree)
        if err:
            return err

        # Convert dict to JSON string for C++ helper
        tree_json = json.dumps(tree_structure)

        # Call C++ helper to build the tree
        result_json = unreal.MCPythonHelper.build_behavior_tree(bt, tree_json)
        return result_json
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_build_behavior_tree: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_list_bt_node_classes() -> str:
    """Lists all available BT node classes (composites, tasks, decorators, services)."""
    try:
        result_json = unreal.MCPythonHelper.list_bt_node_classes()
        return result_json
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_list_bt_node_classes: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


# Literal metadata consumed by mcp-server/generate_catalog.py.
ACTION_METADATA = {'add_blackboard_key': {'asset_path_params': ['asset_path'],
                        'description': 'Adds a new key to a Blackboard asset.',
                        'effect': 'write',
                        'idempotent': False,
                        'required_plugins': [],
                        'requires_confirmation': True,
                        'result_kind': 'json',
                        'risk': 'medium',
                        'supports_preview': True,
                        'supports_undo': True,
                        'title': 'Add Blackboard Key',
                        'ue_versions': ['5.6', '5.7', '5.8']},
 'build_behavior_tree': {'asset_path_params': ['asset_path'],
                         'description': 'Builds a complete Behavior Tree from a JSON structure.',
                         'effect': 'destructive',
                         'idempotent': False,
                         'required_plugins': [],
                         'requires_confirmation': True,
                         'result_kind': 'json',
                         'risk': 'high',
                         'supports_preview': True,
                         'supports_undo': False,
                         'title': 'Build Behavior Tree',
                         'ue_versions': ['5.6', '5.7', '5.8']},
 'create_behavior_tree': {'asset_path_params': ['asset_path', 'blackboard_path'],
                          'description': 'Creates a new empty Behavior Tree asset.',
                          'effect': 'write',
                          'idempotent': False,
                          'required_plugins': [],
                          'requires_confirmation': True,
                          'result_kind': 'json',
                          'risk': 'medium',
                          'supports_preview': True,
                          'supports_undo': True,
                          'title': 'Create Behavior Tree',
                          'ue_versions': ['5.6', '5.7', '5.8']},
 'create_blackboard': {'asset_path_params': ['asset_path', 'parent_path'],
                       'description': 'Creates a new Blackboard Data asset.',
                       'effect': 'write',
                       'idempotent': False,
                       'required_plugins': [],
                       'requires_confirmation': True,
                       'result_kind': 'json',
                       'risk': 'medium',
                       'supports_preview': True,
                       'supports_undo': True,
                       'title': 'Create Blackboard',
                       'ue_versions': ['5.6', '5.7', '5.8']},
 'get_behavior_tree_structure': {'asset_path_params': ['asset_path'],
                                 'description': 'Returns the full tree structure of a Behavior '
                                                'Tree asset as JSON.',
                                 'effect': 'read',
                                 'idempotent': True,
                                 'required_plugins': [],
                                 'requires_confirmation': False,
                                 'result_kind': 'json',
                                 'risk': 'low',
                                 'supports_preview': False,
                                 'supports_undo': False,
                                 'title': 'Get Behavior Tree Structure',
                                 'ue_versions': ['5.6', '5.7', '5.8']},
 'get_blackboard_data': {'asset_path_params': ['asset_path'],
                         'description': 'Reads all keys from a Blackboard asset.',
                         'effect': 'read',
                         'idempotent': True,
                         'required_plugins': [],
                         'requires_confirmation': False,
                         'result_kind': 'json',
                         'risk': 'low',
                         'supports_preview': False,
                         'supports_undo': False,
                         'title': 'Get Blackboard Data',
                         'ue_versions': ['5.6', '5.7', '5.8']},
 'get_bt_node_details': {'asset_path_params': ['asset_path'],
                         'description': 'Retrieves detailed properties of a specific node in a '
                                        'Behavior Tree.',
                         'effect': 'read',
                         'idempotent': True,
                         'required_plugins': [],
                         'requires_confirmation': False,
                         'result_kind': 'json',
                         'risk': 'low',
                         'supports_preview': False,
                         'supports_undo': False,
                         'title': 'Get Bt Node Details',
                         'ue_versions': ['5.6', '5.7', '5.8']},
 'get_selected_bt_nodes': {'description': 'Returns details of selected nodes in the currently open '
                                          'BT editor.',
                           'effect': 'read',
                           'idempotent': True,
                           'required_plugins': [],
                           'requires_confirmation': False,
                           'result_kind': 'json',
                           'risk': 'low',
                           'supports_preview': False,
                           'supports_undo': False,
                           'title': 'Get Selected Bt Nodes',
                           'ue_versions': ['5.6', '5.7', '5.8']},
 'list_behavior_trees': {'description': 'Lists all Behavior Tree assets under /Game.',
                         'effect': 'read',
                         'idempotent': True,
                         'required_plugins': [],
                         'requires_confirmation': False,
                         'result_kind': 'json',
                         'risk': 'low',
                         'supports_preview': False,
                         'supports_undo': False,
                         'title': 'List Behavior Trees',
                         'ue_versions': ['5.6', '5.7', '5.8']},
 'list_bt_node_classes': {'description': 'Lists all available BT node classes (composites, tasks, '
                                         'decorators, services).',
                          'effect': 'read',
                          'idempotent': True,
                          'required_plugins': [],
                          'requires_confirmation': False,
                          'result_kind': 'json',
                          'risk': 'low',
                          'supports_preview': False,
                          'supports_undo': False,
                          'title': 'List Bt Node Classes',
                          'ue_versions': ['5.6', '5.7', '5.8']},
 'remove_blackboard_key': {'asset_path_params': ['asset_path'],
                           'description': 'Removes a key from a Blackboard asset.',
                           'effect': 'destructive',
                           'idempotent': False,
                           'required_plugins': [],
                           'requires_confirmation': True,
                           'result_kind': 'json',
                           'risk': 'high',
                           'supports_preview': True,
                           'supports_undo': False,
                           'title': 'Remove Blackboard Key',
                           'ue_versions': ['5.6', '5.7', '5.8']},
 'set_blackboard_to_behavior_tree': {'asset_path_params': ['bt_path', 'bb_path'],
                                     'description': 'Links a Blackboard asset to a Behavior Tree.',
                                     'effect': 'write',
                                     'idempotent': False,
                                     'required_plugins': [],
                                     'requires_confirmation': True,
                                     'result_kind': 'json',
                                     'risk': 'medium',
                                     'supports_preview': True,
                                     'supports_undo': True,
                                     'title': 'Set Blackboard To Behavior Tree',
                                     'ue_versions': ['5.6', '5.7', '5.8']}}
