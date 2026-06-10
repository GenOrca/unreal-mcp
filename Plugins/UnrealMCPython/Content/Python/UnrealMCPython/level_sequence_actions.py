# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Python action functions for Level Sequence (cinematic) editing in Unreal Engine.

Bindings are referenced by name (the World Outliner / display name). Several
LevelSequence methods are deprecated in favor of the Level Sequence Editor
Subsystem, but the direct methods work headlessly and return properly-named
bindings, whereas the subsystem variants require a focused editor sequence and
return unnamed bindings. We use the direct methods and suppress the Python
DeprecationWarning so it never corrupts the JSON response.
"""
import unreal
import json
import traceback
import warnings
import contextlib


@contextlib.contextmanager
def _suppress():
    """Suppress the DeprecationWarning that some LevelSequence methods emit
    (it would otherwise corrupt the JSON response on the wire)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


def _load_sequence(asset_path: str):
    if not asset_path:
        raise ValueError("Sequence path cannot be empty.")
    seq = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not seq:
        raise FileNotFoundError(f"Level Sequence not found at path: {asset_path}")
    if not isinstance(seq, unreal.LevelSequence):
        raise TypeError(f"Asset at {asset_path} is not a LevelSequence, but {type(seq).__name__}")
    return seq


def _fps(seq) -> float:
    rate = seq.get_display_rate()
    return float(rate.numerator) / float(rate.denominator or 1)


def _find_binding(seq, binding_name: str):
    binding = seq.find_binding_by_name(binding_name)
    if not binding or not binding.is_valid():
        names = [b.get_name() for b in seq.get_bindings()]
        raise ValueError(f"Binding '{binding_name}' not found. Available: {names}")
    return binding


def _spawnable_names(seq):
    return {b.get_name() for b in seq.get_spawnables()}


def _split_asset_path(asset_path: str):
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


def _get_or_create_transform_section(seq, binding):
    """
    Return the first MovieScene3DTransformTrack section on a binding, creating it
    if needed. A freshly created section is zero-length, so ensure it spans at
    least the sequence's playback range — otherwise keys land outside the section
    and are invisible/unusable in Sequencer.
    """
    section = None
    for track in binding.get_tracks():
        if isinstance(track, unreal.MovieScene3DTransformTrack):
            sections = track.get_sections()
            section = sections[0] if sections else track.add_section()
            break
    if section is None:
        track = binding.add_track(unreal.MovieScene3DTransformTrack)
        section = track.add_section()

    start = seq.get_playback_start_seconds()
    end = seq.get_playback_end_seconds()
    if section.get_end_frame_seconds() - section.get_start_frame_seconds() < (end - start):
        section.set_range_seconds(start, end)
    return section


# --- Actions ------------------------------------------------------------------

def ue_create_level_sequence(asset_path: str = None, fps: float = 30.0, duration_seconds: float = 5.0) -> str:
    """Creates a Level Sequence asset with the given frame rate and playback duration."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        name, package = _split_asset_path(asset_path)
        with _suppress():
            tools = unreal.AssetToolsHelpers.get_asset_tools()
            seq = tools.create_asset(name, package, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
            if not seq:
                return json.dumps({"success": False, "message": f"Failed to create level sequence at '{asset_path}'."})
            seq.set_display_rate(unreal.FrameRate(int(fps), 1))
            seq.set_playback_start_seconds(0.0)
            seq.set_playback_end_seconds(float(duration_seconds))
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "fps": fps,
                           "duration_seconds": duration_seconds,
                           "message": f"Level Sequence created at '{asset_path}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_sequence_info(asset_path: str = None) -> str:
    """Returns frame rate, playback range (seconds), and the bindings of a Level Sequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            spawnable = _spawnable_names(seq)
            bindings = [{"name": b.get_name(),
                         "type": "spawnable" if b.get_name() in spawnable else "possessable",
                         "track_count": len(b.get_tracks())}
                        for b in seq.get_bindings()]
            info = {
                "success": True,
                "asset_path": asset_path,
                "fps": _fps(seq),
                "playback_start_seconds": seq.get_playback_start_seconds(),
                "playback_end_seconds": seq.get_playback_end_seconds(),
                "bindings": bindings,
            }
        return json.dumps(info)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_playback_range(asset_path: str = None, start_seconds: float = None, end_seconds: float = None) -> str:
    """Sets the playback range (in seconds) of a Level Sequence."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if start_seconds is None or end_seconds is None:
        return json.dumps({"success": False, "message": "Required parameters 'start_seconds' and 'end_seconds' are missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            seq.set_playback_start_seconds(float(start_seconds))
            seq.set_playback_end_seconds(float(end_seconds))
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "playback_start_seconds": float(start_seconds),
                           "playback_end_seconds": float(end_seconds)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_spawnable_from_class(asset_path: str = None, class_path: str = None) -> str:
    """Adds a spawnable binding from a class path (e.g. '/Script/CinematicCamera.CineCameraActor'). Returns the binding name."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'class_path' is missing."})
    try:
        actor_class = unreal.load_class(None, class_path)
        if not actor_class:
            return json.dumps({"success": False, "message": f"Could not load class: {class_path}"})
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = seq.add_spawnable_from_class(actor_class)
            if not binding or not binding.is_valid():
                return json.dumps({"success": False, "message": f"Failed to add spawnable for {class_path}."})
            binding_name = binding.get_name()
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "binding_name": binding_name,
                           "message": f"Added spawnable '{binding_name}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_possessable(asset_path: str = None, actor_label: str = None) -> str:
    """Adds a possessable binding for an existing level actor (by World Outliner label). Returns the binding name."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if actor_label is None:
        return json.dumps({"success": False, "message": "Required parameter 'actor_label' is missing."})
    try:
        es = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = next((a for a in es.get_all_level_actors() if a.get_actor_label() == actor_label), None)
        if not actor:
            return json.dumps({"success": False, "message": f"Actor not found in level: '{actor_label}'."})
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = seq.add_possessable(actor)
            if not binding or not binding.is_valid():
                return json.dumps({"success": False, "message": f"Failed to add possessable for '{actor_label}'."})
            binding_name = binding.get_name()
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "binding_name": binding_name,
                           "message": f"Added possessable '{binding_name}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_binding(asset_path: str = None, binding_name: str = None) -> str:
    """Removes a binding (spawnable or possessable) from a Level Sequence by name."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if binding_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'binding_name' is missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = _find_binding(seq, binding_name)
            binding.remove()
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
            remaining = [b.get_name() for b in seq.get_bindings()]
        return json.dumps({"success": True, "asset_path": asset_path,
                           "removed": binding_name, "remaining_bindings": remaining})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_transform_track(asset_path: str = None, binding_name: str = None) -> str:
    """Adds a 3D transform track (with one section) to a binding."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if binding_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'binding_name' is missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = _find_binding(seq, binding_name)
            _get_or_create_transform_section(seq, binding)
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "binding_name": binding_name,
                           "message": f"Added transform track to '{binding_name}'."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_transform_keyframe(asset_path: str = None, binding_name: str = None, time_seconds: float = None,
                              location: list = None, rotation: list = None, scale: list = None) -> str:
    """
    Adds a keyframe at time_seconds on a binding's transform track. Provide any of
    location [x,y,z], rotation [pitch,yaw,roll], scale [x,y,z]. A transform track
    is created if the binding doesn't have one.
    """
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if binding_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'binding_name' is missing."})
    if time_seconds is None:
        return json.dumps({"success": False, "message": "Required parameter 'time_seconds' is missing."})
    if location is None and rotation is None and scale is None:
        return json.dumps({"success": False, "message": "Provide at least one of location / rotation / scale."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = _find_binding(seq, binding_name)
            section = _get_or_create_transform_section(seq, binding)
            # Extend the section so the key is inside it (otherwise it's not visible).
            if float(time_seconds) > section.get_end_frame_seconds():
                section.set_range_seconds(section.get_start_frame_seconds(), float(time_seconds))
            elif float(time_seconds) < section.get_start_frame_seconds():
                section.set_range_seconds(float(time_seconds), section.get_end_frame_seconds())
            frame = unreal.FrameNumber(int(round(float(time_seconds) * _fps(seq))))
            # Channel order is fixed: 0-2 Location XYZ, 3-5 Rotation XYZ, 6-8 Scale XYZ.
            chans = section.get_all_channels()
            keyed = []
            for offset, values, label in ((0, location, "location"), (3, rotation, "rotation"), (6, scale, "scale")):
                if values is None:
                    continue
                if len(values) != 3:
                    return json.dumps({"success": False, "message": f"{label} must be a list of 3 floats."})
                for i in range(3):
                    chans[offset + i].add_key(frame, float(values[i]))
                keyed.append(label)
            section_range = [round(section.get_start_frame_seconds(), 4),
                             round(section.get_end_frame_seconds(), 4)]
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "binding_name": binding_name,
                           "frame": int(round(float(time_seconds) * _fps(seq))), "keyed": keyed,
                           "section_range_seconds": section_range})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Sequencer editor (camera, anim tracks, open/close) ------------------------

def ue_open_in_sequencer(asset_path: str = None) -> str:
    """Opens a Level Sequence in the Sequencer editor (and focuses it)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            ok = unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
        return json.dumps({"success": bool(ok), "asset_path": asset_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_close_sequencer() -> str:
    """Closes the Sequencer editor if one is open."""
    try:
        unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_camera(asset_path: str = None, spawnable: bool = True) -> str:
    """Adds a CineCamera to a Level Sequence with a Camera Cut track bound to it (official create_camera path)."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            lsb = unreal.LevelSequenceEditorBlueprintLibrary
            if not lsb.open_level_sequence(seq):
                return json.dumps({"success": False, "message": "Could not open the sequence in Sequencer (create_camera requires a focused sequence)."})
            try:
                sub = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
                binding, _cam_actor = sub.create_camera(spawnable=bool(spawnable))
                binding_name = binding.get_name()
                # Make sure the camera-cut section spans the playback range.
                start = seq.get_playback_start_seconds()
                end = seq.get_playback_end_seconds()
                for track in seq.get_tracks():
                    if isinstance(track, unreal.MovieSceneCameraCutTrack):
                        for sec in track.get_sections():
                            sec.set_range_seconds(start, end)
                unreal.EditorAssetLibrary.save_loaded_asset(seq)
            finally:
                lsb.close_level_sequence()
        return json.dumps({"success": True, "asset_path": asset_path,
                           "camera_binding": binding_name, "camera_cut_track": True,
                           "spawnable": bool(spawnable)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_anim_track(asset_path: str = None, binding_name: str = None, anim_path: str = None,
                      start_seconds: float = None, end_seconds: float = None) -> str:
    """Adds a skeletal-animation track playing anim_path on a binding (defaults to the playback range)."""
    if asset_path is None or binding_name is None or anim_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, binding_name, anim_path."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = _find_binding(seq, binding_name)
            anim = unreal.EditorAssetLibrary.load_asset(anim_path)
            if not anim or not isinstance(anim, unreal.AnimSequenceBase):
                return json.dumps({"success": False, "message": f"Not an animation asset: {anim_path}"})
            track = binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
            sec = track.add_section()
            s = seq.get_playback_start_seconds() if start_seconds is None else float(start_seconds)
            e = seq.get_playback_end_seconds() if end_seconds is None else float(end_seconds)
            sec.set_range_seconds(s, e)
            params = sec.get_editor_property("params")
            params.set_editor_property("animation", anim)
            sec.set_editor_property("params", params)
            unreal.EditorAssetLibrary.save_loaded_asset(seq)
        return json.dumps({"success": True, "asset_path": asset_path, "binding_name": binding_name,
                           "anim_path": anim_path, "range_seconds": [round(s, 3), round(e, 3)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_convert_binding(asset_path: str = None, binding_name: str = None, to: str = "spawnable") -> str:
    """Converts a binding between possessable and spawnable. to='spawnable' or 'possessable'."""
    if asset_path is None or binding_name is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, binding_name."})
    mode = (to or "").lower()
    if mode not in ("spawnable", "possessable"):
        return json.dumps({"success": False, "message": "Parameter 'to' must be 'spawnable' or 'possessable'."})
    try:
        with _suppress():
            seq = _load_sequence(asset_path)
            binding = _find_binding(seq, binding_name)
            lsb = unreal.LevelSequenceEditorBlueprintLibrary
            if not lsb.open_level_sequence(seq):
                return json.dumps({"success": False, "message": "Could not open the sequence in Sequencer (conversion requires a focused sequence)."})
            try:
                sub = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
                if mode == "spawnable":
                    result = sub.convert_to_spawnable(binding)
                    names = [b.get_name() for b in (result or [])]
                else:
                    result = sub.convert_to_possessable(binding)
                    names = [result.get_name()] if result else []
                unreal.EditorAssetLibrary.save_loaded_asset(seq)
            finally:
                lsb.close_level_sequence()
        if not names:
            return json.dumps({"success": False, "message": f"Conversion to {mode} returned no binding."})
        return json.dumps({"success": True, "asset_path": asset_path, "converted_to": mode, "bindings": names})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
