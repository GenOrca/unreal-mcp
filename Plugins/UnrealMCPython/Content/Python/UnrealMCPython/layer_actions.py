# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Python action functions for editor Layers (LayersSubsystem)."""
import unreal
import json
import traceback


def _layers():
    return unreal.get_editor_subsystem(unreal.LayersSubsystem)


def _actor_by_label(actor_label: str):
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in sub.get_all_level_actors():
        if a.get_actor_label() == actor_label:
            return a
    return None


def ue_list_layers() -> str:
    """Lists all layer names in the current world."""
    try:
        # add_all_layer_names_to() takes no args and returns the Array[Name].
        names = _layers().add_all_layer_names_to()
        return json.dumps({"success": True, "layers": [str(n) for n in names]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_create_layer(layer_name: str = None) -> str:
    """Creates a new (empty) layer."""
    if layer_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'layer_name' is missing."})
    try:
        _layers().create_layer(unreal.Name(layer_name))
        return json.dumps({"success": True, "layer_name": layer_name})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_delete_layer(layer_name: str = None) -> str:
    """Deletes a layer."""
    if layer_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'layer_name' is missing."})
    try:
        ls = _layers()
        if not ls.is_layer(unreal.Name(layer_name)):
            return json.dumps({"success": False, "message": f"Layer '{layer_name}' does not exist."})
        ls.delete_layer(unreal.Name(layer_name))
        return json.dumps({"success": True, "deleted": layer_name})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_actor_to_layer(actor_label: str = None, layer_name: str = None) -> str:
    """Adds an actor to a layer (creates the layer if needed)."""
    if actor_label is None or layer_name is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, layer_name."})
    try:
        actor = _actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        ok = _layers().add_actor_to_layer(actor, unreal.Name(layer_name))
        return json.dumps({"success": bool(ok), "actor_label": actor_label, "layer_name": layer_name})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_actor_from_layer(actor_label: str = None, layer_name: str = None) -> str:
    """Removes an actor from a layer."""
    if actor_label is None or layer_name is None:
        return json.dumps({"success": False, "message": "Required parameters: actor_label, layer_name."})
    try:
        actor = _actor_by_label(actor_label)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found: {actor_label}"})
        ok = _layers().remove_actor_from_layer(actor, unreal.Name(layer_name))
        return json.dumps({"success": bool(ok), "actor_label": actor_label, "layer_name": layer_name})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_actors_in_layer(layer_name: str = None) -> str:
    """Lists the labels of actors assigned to a layer."""
    if layer_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'layer_name' is missing."})
    try:
        actors = _layers().get_actors_from_layer(unreal.Name(layer_name))
        return json.dumps({"success": True, "layer_name": layer_name,
                           "actors": [a.get_actor_label() for a in actors]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# Literal metadata consumed by mcp-server/generate_catalog.py.
ACTION_METADATA = {'add_actor_to_layer': {'description': 'Adds an actor to a layer (creates the layer if needed).',
                        'effect': 'write',
                        'idempotent': False,
                        'required_plugins': [],
                        'requires_confirmation': True,
                        'result_kind': 'json',
                        'risk': 'medium',
                        'supports_preview': True,
                        'supports_undo': True,
                        'title': 'Add Actor To Layer',
                        'ue_versions': ['5.6', '5.7', '5.8']},
 'create_layer': {'description': 'Creates a new (empty) layer.',
                  'effect': 'write',
                  'idempotent': False,
                  'required_plugins': [],
                  'requires_confirmation': True,
                  'result_kind': 'json',
                  'risk': 'medium',
                  'supports_preview': True,
                  'supports_undo': True,
                  'title': 'Create Layer',
                  'ue_versions': ['5.6', '5.7', '5.8']},
 'delete_layer': {'description': 'Deletes a layer.',
                  'effect': 'destructive',
                  'idempotent': False,
                  'required_plugins': [],
                  'requires_confirmation': True,
                  'result_kind': 'json',
                  'risk': 'high',
                  'supports_preview': True,
                  'supports_undo': False,
                  'title': 'Delete Layer',
                  'ue_versions': ['5.6', '5.7', '5.8']},
 'get_actors_in_layer': {'description': 'Lists the labels of actors assigned to a layer.',
                         'effect': 'read',
                         'idempotent': True,
                         'required_plugins': [],
                         'requires_confirmation': False,
                         'result_kind': 'json',
                         'risk': 'low',
                         'supports_preview': False,
                         'supports_undo': False,
                         'title': 'Get Actors In Layer',
                         'ue_versions': ['5.6', '5.7', '5.8']},
 'list_layers': {'description': 'Lists all layer names in the current world.',
                 'effect': 'read',
                 'idempotent': True,
                 'required_plugins': [],
                 'requires_confirmation': False,
                 'result_kind': 'json',
                 'risk': 'low',
                 'supports_preview': False,
                 'supports_undo': False,
                 'title': 'List Layers',
                 'ue_versions': ['5.6', '5.7', '5.8']},
 'remove_actor_from_layer': {'description': 'Removes an actor from a layer.',
                             'effect': 'destructive',
                             'idempotent': False,
                             'required_plugins': [],
                             'requires_confirmation': True,
                             'result_kind': 'json',
                             'risk': 'high',
                             'supports_preview': True,
                             'supports_undo': False,
                             'title': 'Remove Actor From Layer',
                             'ue_versions': ['5.6', '5.7', '5.8']}}
