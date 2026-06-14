# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import os
import glob
import traceback
from collections import deque

def ue_print_message(message: str = None) -> str:
    """
    Logs a message to the Unreal log and returns a JSON success response.
    """
    if message is None:
        return json.dumps({"success": False, "message": "Required parameter 'message' is missing."})

    unreal.log(f"MCP Message: {message}")
    return json.dumps({
        "received_message": message,
        "success": True,
        "source": "ue_print_message"
    })

def _tail_log(path: str, line_count: int):
    """Last line_count lines via backward block reads (never loads the whole file)."""
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        pos = file_size
        data = b""
        while pos > 0 and data.count(b"\n") <= line_count:
            step = min(65536, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
        # total_lines: cheap forward newline count (no decode, no line list)
        f.seek(0)
        total = 0
        last_byte = b"\n"
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            total += chunk.count(b"\n")
            last_byte = chunk[-1:]
        if file_size and last_byte != b"\n":
            total += 1
    lines = data.decode('utf-8', errors='replace').splitlines(keepends=True)
    if pos > 0:
        lines = lines[1:]  # the first decoded line may start mid-line — drop it
    lines = lines[-line_count:]
    return "".join(lines), total, len(lines)


def _grep_log(path: str, keyword: str, line_count: int, context_lines: int):
    """Stream-scan for keyword; keep the last line_count matched blocks with context."""
    kw = keyword.lower()
    prev = deque(maxlen=context_lines) if context_lines else None
    blocks = deque(maxlen=line_count)  # each block: [(line_no, line), ...]
    pending_after = 0
    total = 0
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            total = i + 1
            if kw in line.lower():
                if pending_after > 0 and blocks:
                    blocks[-1].append((i, line))  # within a previous match's context: merge
                else:
                    block = list(prev) if prev else []
                    block.append((i, line))
                    blocks.append(block)
                pending_after = context_lines
                if prev is not None:
                    prev.clear()
            elif pending_after > 0:
                blocks[-1].append((i, line))
                pending_after -= 1
            elif prev is not None:
                prev.append((i, line))

    parts = []
    returned = 0
    last_no = None
    for block in blocks:
        if context_lines and last_no is not None and block[0][0] > last_no + 1:
            parts.append("--\n")
        parts.extend(l for _, l in block)
        returned += len(block)
        last_no = block[-1][0]
    return "".join(parts), total, returned


def ue_get_output_log(line_count: int = 50, keyword: str = None, context_lines: int = 0) -> str:
    """Returns recent lines from the UE output log file; optional keyword filter with context_lines around each match."""
    try:
        log_dir = unreal.Paths.project_log_dir()
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        if not log_files:
            return json.dumps({"success": False, "message": "No log files found"})

        latest_log = max(log_files, key=os.path.getmtime)
        line_count = max(1, int(line_count))
        context_lines = max(0, int(context_lines))

        if keyword:
            log_text, total, returned = _grep_log(latest_log, keyword, line_count, context_lines)
        else:
            log_text, total, returned = _tail_log(latest_log, line_count)

        return json.dumps({
            "success": True,
            "log_file": os.path.basename(latest_log),
            "total_lines": total,
            "returned_lines": returned,
            "log": log_text
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- Editor control -----------------------------------------------------------

def ue_execute_console_command(command: str = None) -> str:
    """Executes an editor console command (e.g. 'stat fps', 'r.ScreenPercentage 50')."""
    if command is None:
        return json.dumps({"success": False, "message": "Required parameter 'command' is missing."})
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.SystemLibrary.execute_console_command(world, command)
        return json.dumps({"success": True, "command": command})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_save_all_dirty() -> str:
    """Saves all dirty packages (modified maps and content)."""
    try:
        ok = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
        return json.dumps({"success": bool(ok), "message": "Saved dirty packages." if ok else "save_dirty_packages returned False."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_viewport_camera() -> str:
    """Returns the level viewport camera location and rotation."""
    try:
        info = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_level_viewport_camera_info()
        if not info:
            return json.dumps({"success": False, "message": "No active level viewport."})
        loc, rot = info
        return json.dumps({
            "success": True,
            "location": [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3)],
            "rotation": [round(rot.pitch, 3), round(rot.yaw, 3), round(rot.roll, 3)],
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_viewport_camera(location: list = None, rotation: list = None) -> str:
    """Sets the level viewport camera. location=[x,y,z], rotation=[pitch,yaw,roll]."""
    if location is None or rotation is None:
        return json.dumps({"success": False, "message": "Required parameters: location, rotation."})
    if len(location) != 3 or len(rotation) != 3:
        return json.dumps({"success": False, "message": "location and rotation must be lists of 3 floats."})
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        ues.set_level_viewport_camera_info(
            unreal.Vector(float(location[0]), float(location[1]), float(location[2])),
            unreal.Rotator(float(rotation[0]), float(rotation[1]), float(rotation[2])))
        return json.dumps({"success": True, "location": location, "rotation": rotation})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_world_to_screen(location: list = None) -> str:
    """Projects a world location to active level-viewport pixel coords (editor viewport, no PIE needed)."""
    if location is None or len(location) != 3:
        return json.dumps({"success": False, "message": "Required parameter 'location' must be a list of 3 floats."})
    try:
        loc = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
        return unreal.MCPythonHelper.world_to_screen(loc)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_screen_to_world(x: float = None, y: float = None, distance: float = 1000.0) -> str:
    """Deprojects a viewport pixel (x, y) to a world location at 'distance' along the view ray."""
    if x is None or y is None:
        return json.dumps({"success": False, "message": "Required parameters: x, y."})
    try:
        return unreal.MCPythonHelper.screen_to_world(float(x), float(y), float(distance))
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_is_in_pie() -> str:
    """Returns whether Play-In-Editor is currently active."""
    try:
        active = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
        return json.dumps({"success": True, "in_pie": bool(active)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_start_pie() -> str:
    """Starts Play-In-Editor (asynchronous; begins on the next frame)."""
    try:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
        return json.dumps({"success": True, "message": "Requested PIE begin."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_stop_pie() -> str:
    """Stops Play-In-Editor."""
    try:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
        return json.dumps({"success": True, "message": "Requested PIE end."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_class_properties(class_path: str = None) -> str:
    """Lists the editor-settable property names of a UClass (for discovering what set_property accepts)."""
    if class_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'class_path' is missing."})
    try:
        cls = unreal.load_class(None, class_path)
        if not cls:
            return json.dumps({"success": False, "message": f"Class not found: {class_path}"})
        cdo = unreal.get_default_object(cls)
        props = sorted(p for p in dir(cdo)
                       if not p.startswith("_") and not callable(getattr(type(cdo), p, None)))
        return json.dumps({"success": True, "class_path": class_path,
                           "count": len(props), "properties": props})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_cvar(name: str = None) -> str:
    """Reads the current value of a console variable (CVar) as a string, e.g. 'r.ScreenPercentage'."""
    if name is None:
        return json.dumps({"success": False, "message": "Required parameter 'name' is missing."})
    try:
        value = unreal.SystemLibrary.get_console_variable_string_value(name)
        return json.dumps({"success": True, "name": name, "value": value})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_cvar(name: str = None, value: str = None) -> str:
    """Sets a console variable, e.g. name='r.ScreenPercentage', value='75'. Reads it back to confirm."""
    if name is None or value is None:
        return json.dumps({"success": False, "message": "Required parameters: name, value."})
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.SystemLibrary.execute_console_command(world, f"{name} {value}")
        new_value = unreal.SystemLibrary.get_console_variable_string_value(name)
        return json.dumps({"success": True, "name": name, "requested": str(value), "value": new_value})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


_LOG_VERBOSITIES = {"NoLogging", "Fatal", "Error", "Warning", "Display",
                    "Log", "Verbose", "VeryVerbose", "All", "Default"}


def ue_set_log_verbosity(category: str = None, verbosity: str = None) -> str:
    """Sets a log category's verbosity via the 'Log' console command (e.g. 'LogBlueprint', 'Verbose')."""
    if category is None or verbosity is None:
        return json.dumps({"success": False, "message": "Required parameters: category, verbosity."})
    if verbosity not in _LOG_VERBOSITIES:
        return json.dumps({"success": False, "message": f"Invalid verbosity '{verbosity}'.",
                           "valid": sorted(_LOG_VERBOSITIES)})
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        unreal.SystemLibrary.execute_console_command(world, f"Log {category} {verbosity}")
        return json.dumps({"success": True, "category": category, "verbosity": verbosity})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_project_info() -> str:
    """Returns project name, directories, and engine version."""
    try:
        return json.dumps({
            "success": True,
            "project_name": unreal.SystemLibrary.get_game_name(),
            "project_dir": unreal.Paths.project_dir(),
            "content_dir": unreal.Paths.project_content_dir(),
            "engine_version": unreal.SystemLibrary.get_engine_version(),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_list_enum_values(enum_name: str = None) -> str:
    """Lists the values of an Unreal enum by name (e.g. 'TextureCompressionSettings', 'CollisionTraceFlag')."""
    if enum_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'enum_name' is missing."})
    try:
        short = enum_name.split(".")[-1]
        cls = getattr(unreal, short, None)
        if cls is None:
            return json.dumps({"success": False, "message": f"Enum '{enum_name}' not found in 'unreal' module."})
        values = [v for v in dir(cls) if not v.startswith("_") and isinstance(getattr(cls, v, None), cls)]
        if not values:
            return json.dumps({"success": False, "message": f"'{enum_name}' is not an enum or has no values."})
        return json.dumps({"success": True, "enum": short, "count": len(values), "values": values})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
