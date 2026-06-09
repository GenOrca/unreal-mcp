# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Defines Python action functions for material editing to be executed within Unreal Engine.
"""
import unreal
import json
import traceback
from typing import Optional

# --- Helper Functions for Material Editing ---

def _get_material_asset(material_path: str):
    """Helper to load a material asset."""
    if not material_path:
        raise ValueError("Material path cannot be empty.")
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    if not material:
        raise FileNotFoundError(f"Material asset not found at path: {material_path}")
    if not isinstance(material, unreal.Material):
        raise TypeError(f"Asset at {material_path} is not a Material, but {type(material).__name__}")
    return material

def _get_material_instance_asset(instance_path: str):
    """Helper to load a material instance constant asset."""
    if not instance_path:
        raise ValueError("Material instance path cannot be empty.")
    instance = unreal.EditorAssetLibrary.load_asset(instance_path)
    if not instance:
        raise FileNotFoundError(f"Material instance asset not found at path: {instance_path}")
    if not isinstance(instance, unreal.MaterialInstanceConstant):
        raise TypeError(f"Asset at {instance_path} is not a MaterialInstanceConstant, but {type(instance).__name__}")
    return instance

def _get_expression_class(class_name: str):
    """Helper to get an Unreal MaterialExpression class by name."""
    try:
        # Common prefix for many material expressions if not found directly
        if not hasattr(unreal, class_name) and not class_name.startswith("MaterialExpression"):
            full_class_name = f"MaterialExpression{class_name}"
        else:
            full_class_name = class_name
        
        expression_class = getattr(unreal, full_class_name)
        if not issubclass(expression_class, unreal.MaterialExpression):
            raise TypeError(f"{full_class_name} is not a MaterialExpression class.")
        return expression_class
    except AttributeError:
        raise ValueError(f"MaterialExpression class like '{class_name}' or '{full_class_name}' not found in 'unreal' module.")

def _find_material_expression_by_name_or_type(material: unreal.Material, expression_identifier: str, expression_class_name: str = None):
    """
    Finds a material expression within a material by its description (name) or by its class type.
    """
    
    if not material or not isinstance(material, unreal.Material):
        raise ValueError("Invalid material provided.")

    target_class = None
    if expression_class_name:
        try:
            target_class = _get_expression_class(expression_class_name)
        except (ValueError, TypeError):
            pass 

    it = unreal.ObjectIterator()
    for x in it:
        if isinstance(x, unreal.MaterialExpression) and x.get_path_name().startswith(material.get_path_name()):
            if hasattr(x, 'desc') and x.desc == expression_identifier:
                if target_class and not isinstance(x, target_class):
                    continue 
                return x
            
            if target_class and isinstance(x, target_class):
                if expression_identifier == expression_class_name or expression_identifier == target_class.__name__:
                    return x

            if expression_identifier == x.get_name():
                if target_class and not isinstance(x, target_class):
                    continue 
                return x

    raise ValueError(f"MaterialExpression identified by '{expression_identifier}' (intended class: {expression_class_name or 'any'}) not found in material '{material.get_path_name()}'.")
    
# Friendly material-property name → unreal.MaterialProperty enum
_MATERIAL_PROPERTY_MAP = {
    "BaseColor": "MP_BASE_COLOR",
    "Metallic": "MP_METALLIC",
    "Specular": "MP_SPECULAR",
    "Roughness": "MP_ROUGHNESS",
    "Anisotropy": "MP_ANISOTROPY",
    "EmissiveColor": "MP_EMISSIVE_COLOR",
    "Opacity": "MP_OPACITY",
    "OpacityMask": "MP_OPACITY_MASK",
    "Normal": "MP_NORMAL",
    "Tangent": "MP_TANGENT",
    "WorldPositionOffset": "MP_WORLD_POSITION_OFFSET",
    "SubsurfaceColor": "MP_SUBSURFACE_COLOR",
    "AmbientOcclusion": "MP_AMBIENT_OCCLUSION",
    "Refraction": "MP_REFRACTION",
}


def _split_asset_path(asset_path: str):
    """'/Game/Foo/MyAsset' → ('MyAsset', '/Game/Foo')."""
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


# --- Material Editing Actions ---

def ue_create_expression(material_path: str = None, expression_class_name: str = None, node_pos_x: int = 0, node_pos_y: int = 0) -> str:
    """
    Creates a new material expression node within the supplied material.
    Returns JSON string.
    """
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    if expression_class_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'expression_class_name' is missing."})

    transaction_description = "MCP: Create Material Expression"
    try:
        material = _get_material_asset(material_path)
        expression_class = _get_expression_class(expression_class_name)

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            new_expression = unreal.MaterialEditingLibrary.create_material_expression(
                material, expression_class, node_pos_x, node_pos_y
            )
            if not new_expression:
                return json.dumps({
                    "success": False,
                    "message": f"Failed to create MaterialExpression '{expression_class_name}' in '{material_path}'."
                })
            
            if hasattr(new_expression, 'desc') and not new_expression.desc:
                new_expression.desc = expression_class_name 

            unreal.MaterialEditingLibrary.recompile_material(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)
            
            return json.dumps({
                "success": True,
                "message": f"Successfully created MaterialExpression '{expression_class_name}' in '{material_path}'.",
                "expression_name": new_expression.get_name(), 
                "expression_desc": new_expression.desc if hasattr(new_expression, 'desc') else "N/A",
                "expression_class": new_expression.__class__.__name__
            })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Error creating material expression: {str(e)}",
            "traceback": traceback.format_exc()
        })

def ue_connect_expressions(
    material_path: str = None, 
    from_expression_identifier: str = None, 
    from_output_name: str = None, 
    to_expression_identifier: str = None, 
    to_input_name: str = None,
    from_expression_class_name: str = None,
    to_expression_class_name: str = None
) -> str:
    """
    Creates a connection between two material expressions.
    Returns JSON string.
    """
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    if from_expression_identifier is None:
        return json.dumps({"success": False, "message": "Required parameter 'from_expression_identifier' is missing."})
    if from_output_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'from_output_name' is missing."})
    if to_expression_identifier is None:
        return json.dumps({"success": False, "message": "Required parameter 'to_expression_identifier' is missing."})
    if to_input_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'to_input_name' is missing."})

    transaction_description = "MCP: Connect Material Expressions"
    try:
        material = _get_material_asset(material_path)
        
        from_expression = _find_material_expression_by_name_or_type(material, from_expression_identifier, from_expression_class_name)
        to_expression = _find_material_expression_by_name_or_type(material, to_expression_identifier, to_expression_class_name)

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            success = unreal.MaterialEditingLibrary.connect_material_expressions(
                from_expression, from_output_name, to_expression, to_input_name
            )
            if not success:
                return json.dumps({
                    "success": False,
                    "message": f"Failed to connect '{from_expression_identifier}(Output: {from_output_name})' to '{to_expression_identifier}(Input: {to_input_name})' in '{material_path}'. Check pin names and compatibility."
                })

            unreal.MaterialEditingLibrary.recompile_material(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)

            return json.dumps({
                "success": True,
                "message": f"Successfully connected '{from_expression_identifier}(Output: {from_output_name})' to '{to_expression_identifier}(Input: {to_input_name})' in '{material_path}'."
            })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Error connecting material expressions: {str(e)}",
            "traceback": traceback.format_exc()
        })

def ue_recompile(material_path: str = None) -> str:
    """
    Triggers a recompile of a material or material instance's parent. Saves the asset.
    Returns JSON string.
    """
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    try:
        asset_to_process = unreal.EditorAssetLibrary.load_asset(material_path)
        if not asset_to_process:
            raise FileNotFoundError(f"Asset not found at path: {material_path}")

        target_material_to_recompile = None
        asset_to_save = asset_to_process
        message_detail = ""

        if isinstance(asset_to_process, unreal.Material):
            target_material_to_recompile = asset_to_process
            message_detail = f"material '{material_path}'"
        elif isinstance(asset_to_process, unreal.MaterialInstance):
            parent_material = asset_to_process.parent 
            if parent_material: 
                target_material_to_recompile = parent_material
                message_detail = f"parent of material instance '{material_path}'"
            else: 
                 unreal.EditorAssetLibrary.save_loaded_asset(asset_to_process)
                 return json.dumps({
                    "success": True,
                    "message": f"Material instance '{material_path}' has no parent to recompile. Instance saved."
                 })
        else:
            raise TypeError(f"Asset at {material_path} is not a Material or MaterialInstance, but {type(asset_to_process).__name__}")

        if target_material_to_recompile:
            unreal.MaterialEditingLibrary.recompile_material(target_material_to_recompile)
            unreal.EditorAssetLibrary.save_loaded_asset(asset_to_save) 
        
        return json.dumps({
            "success": True,
            "message": f"Successfully recompiled {message_detail} and saved '{material_path}'."
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Error processing {message_detail} '{material_path}' for recompile: {str(e)}",
            "traceback": traceback.format_exc()
        })

def ue_get_mi_scalar_param(instance_path: str = None, parameter_name: str = None) -> str:
    """
    Gets the current scalar (float) parameter value from a Material Instance Constant.
    Returns JSON string.
    """
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        param_value = instance.get_scalar_parameter_value(ue_parameter_name)

        if param_value is None:
             return json.dumps({
                "success": False, 
                "message": f"Scalar parameter '{parameter_name}' not found in instance '{instance_path}'.",
                "parameter_name": parameter_name,
                "instance_path": instance_path,
                "value": None 
            })
        
        return json.dumps({
            "success": True,
            "parameter_name": parameter_name,
            "value": param_value,
            "instance_path": instance_path
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Error getting scalar parameter '{parameter_name}' from '{instance_path}': {str(e)}",
            "traceback": traceback.format_exc()
        })

def ue_set_mi_scalar_param(instance_path: str = None, parameter_name: str = None, value: float = None) -> str:
    """
    Sets the scalar (float) parameter value for a Material Instance Constant.
    Returns JSON string.
    """
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    if value is None:
        return json.dumps({"success": False, "message": "Required parameter 'value' is missing."})

    transaction_description = "MCP: Set Material Instance Scalar Parameter"
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)

        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, ue_parameter_name, float(value))
            unreal.MaterialEditingLibrary.update_material_instance(instance) 
            unreal.EditorAssetLibrary.save_loaded_asset(instance)

            return json.dumps({
                "success": True,
                "message": f"Successfully set scalar parameter '{parameter_name}' to {value} for instance '{instance_path}'.",
                "instance_path": instance_path,
                "parameter_name": parameter_name,
                "new_value": value
            })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": f"Error setting scalar parameter '{parameter_name}' for '{instance_path}': {str(e)}",
            "traceback": traceback.format_exc()
        })

def ue_get_mi_vector_param(instance_path: str = None, parameter_name: str = None) -> str:
    """Gets a vector parameter from a Material Instance. Returns JSON string."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        param_value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(instance, ue_parameter_name)
        
        value_list = [param_value.r, param_value.g, param_value.b, param_value.a]
        return json.dumps({"success": True, "parameter_name": parameter_name, "value": value_list, "instance_path": instance_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_set_mi_vector_param(instance_path: str = None, parameter_name: str = None, value: list = None) -> str:
    """Sets a vector parameter on a Material Instance. Expects value as [R,G,B,A]. Returns JSON string."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    if value is None:
        return json.dumps({"success": False, "message": "Required parameter 'value' is missing."})

    transaction_description = "MCP: Set Material Instance Vector Parameter"
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        if not isinstance(value, list) or len(value) != 4:
            raise ValueError("Vector value must be a list of 4 floats [R, G, B, A].")
        
        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            linear_color_value = unreal.LinearColor(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
            unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(instance, ue_parameter_name, linear_color_value)
            unreal.MaterialEditingLibrary.update_material_instance(instance)
            unreal.EditorAssetLibrary.save_loaded_asset(instance)
            return json.dumps({"success": True, "message": f"Vector parameter '{parameter_name}' set.", "new_value": value})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def ue_get_mi_texture_param(instance_path: str = None, parameter_name: str = None) -> str:
    """Gets a texture parameter from a Material Instance. Returns JSON string with texture path."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        param_value = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, ue_parameter_name)
        
        texture_path = param_value.get_path_name() if param_value else None
        return json.dumps({"success": True, "parameter_name": parameter_name, "value": texture_path, "instance_path": instance_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})

def _get_mi_texture_param_names(instance_path):
    """
    Gets all texture parameter names for a given material instance
    """
    try:
        instance = unreal.load_asset(instance_path)
        texture_param_names = unreal.MaterialEditingLibrary.get_texture_parameter_names(instance)
        return list(texture_param_names)
    except Exception as e:
        return []
    
def ue_set_mi_texture_param(instance_path: str = None, parameter_name: str = None, texture_path: Optional[str] = None) -> str:
    """Sets a texture parameter on a Material Instance. Provide texture asset path. Returns JSON string."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    
    try:
        instance = unreal.load_asset(instance_path)
        available_params = unreal.MaterialEditingLibrary.get_texture_parameter_names(instance)
        available_params = [str(name) for name in available_params]
    except Exception as e:
        available_params = []
    
    if parameter_name is None:
        return json.dumps({
            "success": False, 
            "message": "Required parameter 'parameter_name' is missing.", 
            "available_parameters": available_params
        })
    
    if parameter_name not in available_params:
        return json.dumps({
            "success": False, 
            "message": f"Texture parameter '{parameter_name}' does not exist.", 
            "available_parameters": available_params
        })
    
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        texture_asset = None
        if texture_path: 
            texture_asset = unreal.EditorAssetLibrary.load_asset(texture_path)
            if not texture_asset:
                return json.dumps({
                    "success": False, 
                    "message": f"Texture asset not found at path: {texture_path}",
                    "available_parameters": available_params
                })
            if not isinstance(texture_asset, unreal.Texture):
                return json.dumps({
                    "success": False, 
                    "message": f"Asset at {texture_path} is not a Texture, but {type(texture_asset).__name__}",
                    "available_parameters": available_params
                })

        with unreal.ScopedEditorTransaction("MCP: Set Material Instance Texture Parameter") as trans:
            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(instance, ue_parameter_name, texture_asset)
            unreal.MaterialEditingLibrary.update_material_instance(instance)
            unreal.EditorAssetLibrary.save_loaded_asset(instance)
            return json.dumps({
                "success": True, 
                "message": f"Texture parameter '{parameter_name}' set.", 
                "new_value": texture_path,
                "available_parameters": available_params
            })
    except Exception as e:
        return json.dumps({
            "success": False, 
            "message": str(e), 
            "traceback": traceback.format_exc(),
            "available_parameters": available_params
        })

def _get_mi_static_switch_params(instance_path):
    """
    Gets all available static switch parameter names for a material instance
    """
    try:
        instance = _get_material_instance_asset(instance_path)
        param_names = unreal.MaterialEditingLibrary.get_static_switch_parameter_names(instance)
        return [str(name) for name in param_names]
    except Exception as e:
        print(f"Error getting static switch parameters: {e}")
        return []

def ue_get_mi_static_switch(instance_path: str = None, parameter_name: str = None) -> str:
    """Gets a static switch parameter from a Material Instance. Returns JSON string."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    
    available_params = _get_mi_static_switch_params(instance_path)
    
    if parameter_name not in available_params:
        return json.dumps({
            "success": False, 
            "message": f"Static switch parameter '{parameter_name}' not found.", 
            "available_parameters": available_params
        })
    
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        param_value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(instance, ue_parameter_name)
        
        return json.dumps({
            "success": True, 
            "parameter_name": parameter_name, 
            "value": param_value, 
            "instance_path": instance_path,
            "available_parameters": available_params
        })
    except Exception as e:
        return json.dumps({
            "success": False, 
            "message": f"Error getting static switch parameter '{parameter_name}': {str(e)}", 
            "traceback": traceback.format_exc(),
            "available_parameters": available_params
        })

def ue_set_mi_static_switch(instance_path: str = None, parameter_name: str = None, value: bool = None) -> str:
    """Sets a static switch parameter on a Material Instance. Returns JSON string."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    if parameter_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'parameter_name' is missing."})
    if value is None:
        return json.dumps({"success": False, "message": "Required parameter 'value' is missing."})

    available_params = _get_mi_static_switch_params(instance_path)
    
    if parameter_name not in available_params:
        return json.dumps({
            "success": False, 
            "message": f"Static switch parameter '{parameter_name}' not found.", 
            "available_parameters": available_params
        })

    transaction_description = "MCP: Set Material Instance Static Switch Parameter"
    try:
        instance = _get_material_instance_asset(instance_path)
        ue_parameter_name = unreal.Name(parameter_name)
        
        with unreal.ScopedEditorTransaction(transaction_description) as trans:
            unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(instance, ue_parameter_name, bool(value))
            unreal.MaterialEditingLibrary.update_material_instance(instance)
            unreal.EditorAssetLibrary.save_loaded_asset(instance)
            return json.dumps({
                "success": True, 
                "message": f"Static switch parameter '{parameter_name}' set to {value}", 
                "new_value": value,
                "available_parameters": available_params
            })
            
    except Exception as e:
        return json.dumps({
            "success": False, 
            "message": f"Error setting static switch parameter '{parameter_name}': {str(e)}", 
            "traceback": traceback.format_exc(),
            "available_parameters": available_params
        })


# --- Asset creation -----------------------------------------------------------

def ue_create_material(material_path: str = None) -> str:
    """Creates a new Material asset at the given content-browser path."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(material_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {material_path}"})
        name, package = _split_asset_path(material_path)
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        mat = tools.create_asset(name, package, unreal.Material, unreal.MaterialFactoryNew())
        if not mat:
            return json.dumps({"success": False, "message": f"Failed to create material at '{material_path}'."})
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        return json.dumps({"success": True, "material_path": material_path,
                           "message": f"Material created at '{material_path}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_create_material_instance(instance_path: str = None, parent_path: str = None) -> str:
    """Creates a Material Instance Constant, optionally parented to parent_path."""
    if instance_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'instance_path' is missing."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(instance_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {instance_path}"})
        name, package = _split_asset_path(instance_path)
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        mi = tools.create_asset(name, package, unreal.MaterialInstanceConstant,
                                unreal.MaterialInstanceConstantFactoryNew())
        if not mi:
            return json.dumps({"success": False, "message": f"Failed to create material instance at '{instance_path}'."})
        if parent_path:
            parent = unreal.EditorAssetLibrary.load_asset(parent_path)
            if not parent or not isinstance(parent, unreal.MaterialInterface):
                return json.dumps({"success": False, "message": f"Parent is not a material: {parent_path}"})
            unreal.MaterialEditingLibrary.set_material_instance_parent(mi, parent)
        unreal.MaterialEditingLibrary.update_material_instance(mi)
        unreal.EditorAssetLibrary.save_loaded_asset(mi)
        return json.dumps({"success": True, "instance_path": instance_path, "parent_path": parent_path,
                           "message": f"Material instance created at '{instance_path}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Graph authoring ----------------------------------------------------------

def ue_connect_property(material_path: str = None, from_expression_identifier: str = None,
                        from_output_name: str = "", property_name: str = None,
                        from_expression_class_name: str = None) -> str:
    """Connects an expression output to a material property (e.g. BaseColor, Metallic, Roughness, Normal)."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    if from_expression_identifier is None:
        return json.dumps({"success": False, "message": "Required parameter 'from_expression_identifier' is missing."})
    if property_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'property_name' is missing.",
                           "valid_properties": list(_MATERIAL_PROPERTY_MAP)})
    if property_name not in _MATERIAL_PROPERTY_MAP:
        return json.dumps({"success": False, "message": f"Unknown property '{property_name}'.",
                           "valid_properties": list(_MATERIAL_PROPERTY_MAP)})
    try:
        material = _get_material_asset(material_path)
        from_expression = _find_material_expression_by_name_or_type(
            material, from_expression_identifier, from_expression_class_name)
        prop = getattr(unreal.MaterialProperty, _MATERIAL_PROPERTY_MAP[property_name])
        with unreal.ScopedEditorTransaction("MCP: Connect Material Property"):
            ok = unreal.MaterialEditingLibrary.connect_material_property(from_expression, from_output_name, prop)
            if not ok:
                return json.dumps({"success": False,
                                   "message": f"Failed to connect '{from_expression_identifier}' to '{property_name}'."})
            unreal.MaterialEditingLibrary.recompile_material(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)
        return json.dumps({"success": True,
                           "message": f"Connected '{from_expression_identifier}' (out '{from_output_name}') to '{property_name}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_delete_expression(material_path: str = None, expression_identifier: str = None,
                         expression_class_name: str = None) -> str:
    """Deletes a material expression node identified by name/desc/type."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    if expression_identifier is None:
        return json.dumps({"success": False, "message": "Required parameter 'expression_identifier' is missing."})
    try:
        material = _get_material_asset(material_path)
        expression = _find_material_expression_by_name_or_type(material, expression_identifier, expression_class_name)
        with unreal.ScopedEditorTransaction("MCP: Delete Material Expression"):
            # delete_material_expression returns None regardless of outcome, so
            # confirm by comparing the expression count before/after.
            before = unreal.MaterialEditingLibrary.get_num_material_expressions(material)
            unreal.MaterialEditingLibrary.delete_material_expression(material, expression)
            after = unreal.MaterialEditingLibrary.get_num_material_expressions(material)
            unreal.MaterialEditingLibrary.recompile_material(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)
        if after >= before:
            return json.dumps({"success": False,
                               "message": f"Expression '{expression_identifier}' was not removed (count {before}->{after})."})
        return json.dumps({"success": True,
                           "message": f"Deleted expression '{expression_identifier}' (count {before}->{after})."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_expression_property(material_path: str = None, expression_identifier: str = None,
                               property_name: str = None, value=None,
                               expression_class_name: str = None) -> str:
    """
    Sets an editor property on a material expression (e.g. 'r' on a Constant,
    'parameter_name'/'default_value' on a ScalarParameter). A 3/4-element list is
    coerced to a LinearColor; 'parameter_name' is coerced to an unreal.Name.
    """
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    if expression_identifier is None:
        return json.dumps({"success": False, "message": "Required parameter 'expression_identifier' is missing."})
    if property_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'property_name' is missing."})
    try:
        material = _get_material_asset(material_path)
        expression = _find_material_expression_by_name_or_type(material, expression_identifier, expression_class_name)
        coerced = value
        if property_name == "parameter_name":
            coerced = unreal.Name(str(value))
        elif isinstance(value, list) and len(value) in (3, 4):
            r, g, b = float(value[0]), float(value[1]), float(value[2])
            a = float(value[3]) if len(value) == 4 else 1.0
            coerced = unreal.LinearColor(r, g, b, a)
        with unreal.ScopedEditorTransaction("MCP: Set Material Expression Property"):
            expression.set_editor_property(property_name, coerced)
            unreal.MaterialEditingLibrary.recompile_material(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)
        return json.dumps({"success": True,
                           "message": f"Set '{property_name}' on '{expression_identifier}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_layout_expressions(material_path: str = None) -> str:
    """Auto-lays out all expression nodes in a material graph."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    try:
        material = _get_material_asset(material_path)
        with unreal.ScopedEditorTransaction("MCP: Layout Material Expressions"):
            unreal.MaterialEditingLibrary.layout_material_expressions(material)
            unreal.EditorAssetLibrary.save_loaded_asset(material)
        return json.dumps({"success": True, "message": f"Laid out expressions in '{material_path}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Read / introspection -----------------------------------------------------

def ue_get_material_info(material_path: str = None) -> str:
    """Returns expression count and a list of expressions (name, class, position) for a material."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    try:
        material = _get_material_asset(material_path)
        count = unreal.MaterialEditingLibrary.get_num_material_expressions(material)
        expressions = []
        mat_path = material.get_path_name()
        for x in unreal.ObjectIterator():
            if isinstance(x, unreal.MaterialExpression) and x.get_path_name().startswith(mat_path):
                try:
                    pos = unreal.MaterialEditingLibrary.get_material_expression_node_position(x)
                    pos_xy = [int(pos.x), int(pos.y)]
                except Exception:
                    pos_xy = None
                expressions.append({
                    "name": x.get_name(),
                    "desc": x.desc if hasattr(x, "desc") else "",
                    "class": x.__class__.__name__,
                    "position": pos_xy,
                })
        return json.dumps({"success": True, "material_path": material_path,
                           "expression_count": count, "expressions": expressions})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_parameters(material_path: str = None) -> str:
    """Lists scalar / vector / texture / static-switch parameter names for a material or material instance."""
    if material_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'material_path' is missing."})
    try:
        asset = unreal.EditorAssetLibrary.load_asset(material_path)
        if not asset or not isinstance(asset, unreal.MaterialInterface):
            return json.dumps({"success": False, "message": f"Asset is not a material/instance: {material_path}"})
        mel = unreal.MaterialEditingLibrary
        return json.dumps({
            "success": True,
            "material_path": material_path,
            "scalar": [str(n) for n in mel.get_scalar_parameter_names(asset)],
            "vector": [str(n) for n in mel.get_vector_parameter_names(asset)],
            "texture": [str(n) for n in mel.get_texture_parameter_names(asset)],
            "static_switch": [str(n) for n in mel.get_static_switch_parameter_names(asset)],
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_instance_parent(instance_path: str = None, parent_path: str = None) -> str:
    """Reparents a Material Instance Constant to a new parent material/instance."""
    if instance_path is None or parent_path is None:
        return json.dumps({"success": False, "message": "Required parameters: instance_path, parent_path."})
    try:
        instance = _get_material_instance_asset(instance_path)
        parent = unreal.EditorAssetLibrary.load_asset(parent_path)
        if not parent or not isinstance(parent, unreal.MaterialInterface):
            return json.dumps({"success": False, "message": f"Parent is not a material/instance: {parent_path}"})
        unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
        unreal.MaterialEditingLibrary.update_material_instance(instance)
        unreal.EditorAssetLibrary.save_loaded_asset(instance)
        return json.dumps({"success": True, "instance_path": instance_path, "parent_path": parent_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
