# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback


def _split_asset_path(asset_path):
    """Split '/Game/Input/IA_Jump' into ('/Game/Input', 'IA_Jump')."""
    parts = asset_path.rsplit('/', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return '/Game', asset_path


def ue_set_game_mode(game_mode_class_path: str = None) -> str:
    """Sets the GameMode Override on the current level's World Settings."""
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        if world is None:
            return json.dumps({"success": False, "message": "No editor world available."})

        world_settings = world.get_world_settings()
        if world_settings is None:
            return json.dumps({"success": False, "message": "Could not get WorldSettings."})

        GAME_MODE_PROPS = ['default_game_mode', 'game_mode_override', 'GameModeOverride']

        # Clear override if path is None or empty
        if not game_mode_class_path:
            set_ok = False
            for prop_name in GAME_MODE_PROPS:
                try:
                    world_settings.set_editor_property(prop_name, None)
                    set_ok = True
                    break
                except Exception:
                    pass

            if not set_ok:
                return json.dumps({
                    "success": False,
                    "message": "Failed to clear GameMode. Property name may differ in this UE version."
                })

            return json.dumps({
                "success": True,
                "message": "GameMode cleared.",
                "game_mode": None
            })

        # Load the class
        loaded_class = unreal.load_class(None, game_mode_class_path)
        if loaded_class is None:
            return json.dumps({
                "success": False,
                "message": f"Could not load class: {game_mode_class_path}. "
                           "Ensure the path is correct (Blueprint paths need '_C' suffix)."
            })

        # Set the GameMode
        set_ok = False
        used_prop = None
        for prop_name in GAME_MODE_PROPS:
            try:
                world_settings.set_editor_property(prop_name, loaded_class)
                set_ok = True
                used_prop = prop_name
                break
            except Exception:
                pass

        if not set_ok:
            return json.dumps({
                "success": False,
                "message": "Failed to set GameMode. Property name may differ in this UE version."
            })

        # Verify
        verified_name = None
        try:
            current = world_settings.get_editor_property(used_prop)
            if current:
                verified_name = str(current.get_name())
        except Exception:
            pass

        return json.dumps({
            "success": True,
            "message": f"GameMode set to '{game_mode_class_path}'.",
            "game_mode": game_mode_class_path,
            "verified_class_name": verified_name
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_set_game_mode: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_add_input_action(asset_path: str = None, value_type: str = "Bool") -> str:
    """Creates a new Enhanced Input Action asset."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})

    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists at '{asset_path}'."})

        package_path, asset_name = _split_asset_path(asset_path)
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

        # Try to create InputAction asset
        ia = None

        # Attempt 1: With factory
        try:
            factory = unreal.InputActionFactory()
            ia = asset_tools.create_asset(asset_name, package_path, unreal.InputAction, factory)
        except Exception:
            pass

        # Attempt 2: Without factory
        if ia is None:
            try:
                ia = asset_tools.create_asset(asset_name, package_path, unreal.InputAction, None)
            except Exception:
                pass

        if ia is None:
            return json.dumps({
                "success": False,
                "message": f"Failed to create InputAction at '{asset_path}'. "
                           "Enhanced Input plugin may not be enabled or InputAction "
                           "class may not be accessible via Python."
            })

        # Set value type if not default Bool
        if value_type and value_type != "Bool":
            type_set = False
            # Try multiple approaches to set value type
            for prop_name in ['value_type', 'ValueType']:
                for enum_name in [value_type.upper(), value_type, value_type.lower()]:
                    try:
                        enum_val = getattr(unreal.InputActionValueType, enum_name, None)
                        if enum_val is not None:
                            ia.set_editor_property(prop_name, enum_val)
                            type_set = True
                            break
                    except Exception:
                        pass
                if type_set:
                    break

            if not type_set:
                unreal.log_warning(
                    f"InputAction created but could not set value_type to '{value_type}'. "
                    "Defaulting to Bool."
                )

        unreal.EditorAssetLibrary.save_asset(ia.get_path_name())

        return json.dumps({
            "success": True,
            "asset_path": ia.get_path_name(),
            "value_type": value_type,
            "message": f"InputAction created at '{ia.get_path_name()}'."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_add_input_action: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


def ue_add_input_mapping(mapping_context_path: str = None,
                         action_path: str = None,
                         key_name: str = None) -> str:
    """Creates/updates an InputMappingContext with a key-to-action mapping."""
    if mapping_context_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'mapping_context_path' is missing."})
    if action_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'action_path' is missing."})
    if key_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'key_name' is missing."})

    try:
        # Load or create the InputMappingContext
        imc = None
        created_imc = False

        if unreal.EditorAssetLibrary.does_asset_exist(mapping_context_path):
            imc = unreal.EditorAssetLibrary.load_asset(mapping_context_path)
            if imc is None:
                return json.dumps({
                    "success": False,
                    "message": f"Failed to load asset at '{mapping_context_path}'."
                })
        else:
            # Create new IMC
            package_path, asset_name = _split_asset_path(mapping_context_path)
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

            try:
                factory = unreal.InputMappingContextFactory()
                imc = asset_tools.create_asset(asset_name, package_path, unreal.InputMappingContext, factory)
            except Exception:
                pass

            if imc is None:
                try:
                    imc = asset_tools.create_asset(asset_name, package_path, unreal.InputMappingContext, None)
                except Exception:
                    pass

            if imc is None:
                return json.dumps({
                    "success": False,
                    "message": f"Failed to create InputMappingContext at '{mapping_context_path}'. "
                               "Enhanced Input plugin may not be enabled."
                })
            created_imc = True

        # Load the InputAction
        ia = unreal.EditorAssetLibrary.load_asset(action_path)
        if ia is None:
            return json.dumps({
                "success": False,
                "message": f"InputAction not found at '{action_path}'."
            })

        # Create Key object (UE 5.7+: Key() takes no args, set key_name via property)
        key = unreal.Key()
        key.set_editor_property('key_name', key_name)

        mapping_added = False

        # Construct EnhancedActionKeyMapping and append to mappings array
        try:
            mapping = unreal.EnhancedActionKeyMapping()
            for prop_name in ['action', 'Action']:
                try:
                    mapping.set_editor_property(prop_name, ia)
                    break
                except Exception:
                    pass
            for prop_name in ['key', 'Key']:
                try:
                    mapping.set_editor_property(prop_name, key)
                    break
                except Exception:
                    pass

            # Try DefaultKeyMappings first (UE 5.7+), then mappings as fallback
            for mp in ['default_key_mappings', 'DefaultKeyMappings', 'mappings', 'Mappings']:
                try:
                    mappings = list(imc.get_editor_property(mp) or [])
                    mappings.append(mapping)
                    imc.set_editor_property(mp, mappings)
                    mapping_added = True
                    break
                except Exception:
                    pass
        except Exception:
            pass

        if not mapping_added:
            if created_imc:
                unreal.EditorAssetLibrary.save_asset(imc.get_path_name())
                return json.dumps({
                    "success": False,
                    "message": f"InputMappingContext created at '{imc.get_path_name()}' "
                               f"but failed to add key mapping '{key_name}' -> '{action_path}'. "
                               f"The Enhanced Input mapping API may not be fully exposed in Python. "
                               f"Use execute_python tool to explore available methods on the IMC object.",
                    "imc_created": True,
                    "imc_path": imc.get_path_name()
                })
            return json.dumps({
                "success": False,
                "message": f"Failed to add key mapping '{key_name}' -> '{action_path}' "
                           f"to '{mapping_context_path}'. "
                           "The Enhanced Input mapping API may not be fully exposed in Python."
            })

        unreal.EditorAssetLibrary.save_asset(imc.get_path_name())

        return json.dumps({
            "success": True,
            "mapping_context_path": imc.get_path_name(),
            "action_path": action_path,
            "key_name": key_name,
            "imc_created": created_imc,
            "message": f"Mapped '{key_name}' -> '{action_path}' in '{imc.get_path_name()}'."
        })
    except Exception as e:
        tb_str = traceback.format_exc()
        unreal.log_error(f"Error in ue_add_input_mapping: {str(e)}\n{tb_str}")
        return json.dumps({"success": False, "message": str(e), "traceback": tb_str})


# Literal metadata consumed by mcp-server/generate_catalog.py.
ACTION_METADATA = {'add_input_action': {'asset_path_params': ['asset_path'],
                      'description': 'Creates a new Enhanced Input Action asset.',
                      'effect': 'write',
                      'idempotent': False,
                      'required_plugins': ['EnhancedInput'],
                      'requires_confirmation': True,
                      'result_kind': 'json',
                      'risk': 'medium',
                      'supports_preview': True,
                      'supports_undo': True,
                      'title': 'Add Input Action',
                      'ue_versions': ['5.6', '5.7', '5.8']},
 'add_input_mapping': {'asset_path_params': ['mapping_context_path', 'action_path'],
                       'description': 'Creates/updates an InputMappingContext with a key-to-action '
                                      'mapping.',
                       'effect': 'write',
                       'idempotent': False,
                       'required_plugins': ['EnhancedInput'],
                       'requires_confirmation': True,
                       'result_kind': 'json',
                       'risk': 'medium',
                       'supports_preview': True,
                       'supports_undo': True,
                       'title': 'Add Input Mapping',
                       'ue_versions': ['5.6', '5.7', '5.8']},
 'set_game_mode': {'asset_path_params': ['game_mode_class_path'],
                   'description': "Sets the GameMode Override on the current level's World "
                                  'Settings.',
                   'effect': 'destructive',
                   'idempotent': False,
                   'required_plugins': [],
                   'requires_confirmation': True,
                   'result_kind': 'json',
                   'risk': 'high',
                   'supports_preview': True,
                   'supports_undo': False,
                   'title': 'Set Game Mode',
                   'ue_versions': ['5.6', '5.7', '5.8']}}
