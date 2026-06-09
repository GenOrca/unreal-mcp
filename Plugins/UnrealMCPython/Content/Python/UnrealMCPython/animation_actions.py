# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Python action functions for Animation Sequence editing in Unreal Engine.

Covers AnimSequence introspection and authoring (notify tracks, sync markers,
float curves) via unreal.AnimationLibrary. AnimBlueprint graph editing and IK
retargeting need C++ / extra plugins and are out of scope here.
"""
import unreal
import json
import traceback

AL = unreal.AnimationLibrary
_RCT_FLOAT = unreal.RawCurveTrackTypes.RCT_FLOAT


def _load_anim_sequence(asset_path: str):
    if not asset_path:
        raise ValueError("AnimSequence path cannot be empty.")
    seq = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not seq:
        raise FileNotFoundError(f"AnimSequence not found at path: {asset_path}")
    if not isinstance(seq, unreal.AnimSequence):
        raise TypeError(f"Asset at {asset_path} is not an AnimSequence, but {type(seq).__name__}")
    return seq


# --- Introspection ------------------------------------------------------------

def ue_get_anim_sequence_info(asset_path: str = None) -> str:
    """Returns length, frame count, approximate fps, and skeleton path of an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        length = AL.get_sequence_length(seq)
        frames = AL.get_num_frames(seq)
        fps = round((frames - 1) / length, 2) if length > 0 and frames > 1 else None
        skel = seq.get_skeleton()
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "length_seconds": round(length, 4),
            "num_frames": frames,
            "fps": fps,
            "skeleton": skel.get_path_name() if skel else None,
            "notify_track_count": len(AL.get_animation_notify_track_names(seq)),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_notify_tracks(asset_path: str = None) -> str:
    """Lists the notify track names on an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "tracks": [str(n) for n in AL.get_animation_notify_track_names(seq)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_notifies(asset_path: str = None) -> str:
    """Lists notify event names on an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "notifies": [str(n) for n in AL.get_animation_notify_event_names(seq)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_curves(asset_path: str = None) -> str:
    """Lists float animation curve names on an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "curves": [str(n) for n in AL.get_animation_curve_names(seq, _RCT_FLOAT)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_sync_markers(asset_path: str = None) -> str:
    """Lists sync markers (name + time) on an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        markers = []
        for m in AL.get_animation_sync_markers(seq):
            markers.append({
                "name": str(getattr(m, "marker_name", "")),
                "time": round(float(getattr(m, "time", 0.0)), 4),
            })
        return json.dumps({"success": True, "asset_path": asset_path, "sync_markers": markers})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Notify tracks ------------------------------------------------------------

def ue_add_notify_track(asset_path: str = None, track_name: str = None) -> str:
    """Adds a notify track to an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if track_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'track_name' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        AL.add_animation_notify_track(seq, track_name)
        unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "track_name": track_name,
                           "tracks": [str(n) for n in AL.get_animation_notify_track_names(seq)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_notify_track(asset_path: str = None, track_name: str = None) -> str:
    """Removes a notify track (and its notifies) from an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if track_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'track_name' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        if not AL.is_valid_anim_notify_track_name(seq, track_name):
            return json.dumps({"success": False, "message": f"Notify track '{track_name}' does not exist.",
                               "tracks": [str(n) for n in AL.get_animation_notify_track_names(seq)]})
        AL.remove_animation_notify_track(seq, track_name)
        unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "removed": track_name,
                           "tracks": [str(n) for n in AL.get_animation_notify_track_names(seq)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Sync markers -------------------------------------------------------------

def ue_add_sync_marker(asset_path: str = None, track_name: str = None,
                       marker_name: str = None, time_seconds: float = None) -> str:
    """Adds a sync marker at a time (seconds) on a notify track. Creates the track if needed."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if track_name is None or marker_name is None or time_seconds is None:
        return json.dumps({"success": False, "message": "Required: track_name, marker_name, time_seconds."})
    try:
        seq = _load_anim_sequence(asset_path)
        if not AL.is_valid_anim_notify_track_name(seq, track_name):
            AL.add_animation_notify_track(seq, track_name)
        AL.add_animation_sync_marker(seq, marker_name, float(time_seconds), track_name)
        unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "track_name": track_name,
                           "marker_name": marker_name, "time_seconds": float(time_seconds)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Curves -------------------------------------------------------------------

def ue_add_float_curve(asset_path: str = None, curve_name: str = None,
                       time_seconds: float = None, value: float = None) -> str:
    """Adds a float curve to an AnimSequence, optionally with an initial key at time_seconds=value."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if curve_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'curve_name' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        if not AL.does_curve_exist(seq, curve_name, _RCT_FLOAT):
            AL.add_curve(seq, curve_name, _RCT_FLOAT, False)
        if time_seconds is not None and value is not None:
            AL.add_float_curve_key(seq, curve_name, float(time_seconds), float(value))
        unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "curve_name": curve_name,
                           "curves": [str(n) for n in AL.get_animation_curve_names(seq, _RCT_FLOAT)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_curve(asset_path: str = None, curve_name: str = None) -> str:
    """Removes a float curve from an AnimSequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if curve_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'curve_name' is missing."})
    try:
        seq = _load_anim_sequence(asset_path)
        if not AL.does_curve_exist(seq, curve_name, _RCT_FLOAT):
            return json.dumps({"success": False, "message": f"Curve '{curve_name}' does not exist.",
                               "curves": [str(n) for n in AL.get_animation_curve_names(seq, _RCT_FLOAT)]})
        AL.remove_curve(seq, curve_name, False)
        unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "removed": curve_name,
                           "curves": [str(n) for n in AL.get_animation_curve_names(seq, _RCT_FLOAT)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
