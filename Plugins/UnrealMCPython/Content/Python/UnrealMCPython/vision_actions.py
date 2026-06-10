# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Vision: capture the level viewport / scene as a PNG.

Captures use a transient SceneCapture2D rendered to an RGBA8 render target and
exported to PNG. This works regardless of editor focus (unlike
take_high_res_screenshot, which only fires when the viewport renders a frame),
and captures the 3D scene only — no editor UI. Because the capture uses its own
camera, capture_from / capture_actors can look anywhere without disturbing the
user's viewport.

Actions return the PNG base64-encoded in 'image_data'; the dispatcher's vision
handler decodes it into an MCP Image.
"""
import unreal
import json
import os
import math
import base64
import tempfile
import traceback


def _capture_scene(world, loc, rot, width, height, fov):
    """Render the scene from (loc, rot) to a PNG and return its base64 string."""
    width = max(64, min(int(width), 4096))
    height = max(64, min(int(height), 4096))
    cap_actor = None
    out_path = None
    try:
        rt = unreal.RenderingLibrary.create_render_target2d(
            world, width, height, unreal.TextureRenderTargetFormat.RTF_RGBA8)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        cap_actor = eas.spawn_actor_from_class(unreal.SceneCapture2D, loc, rot)
        comp = cap_actor.capture_component2d
        comp.set_editor_property("texture_target", rt)
        comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
        comp.set_editor_property("fov_angle", float(fov))
        comp.capture_scene()
        out_dir = tempfile.gettempdir()
        out_name = f"mcp_viewport_{os.getpid()}.png"
        unreal.RenderingLibrary.export_render_target(world, rt, out_dir, out_name)
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8"), width, height
    finally:
        try:
            if cap_actor:
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(cap_actor)
        except Exception:
            pass
        try:
            if out_path and os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass


def _actor_by_label(label):
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in sub.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def ue_capture_viewport(width: int = 1280, height: int = 720, fov: float = 90.0) -> str:
    """Captures the active level viewport (3D scene only) as a PNG, returned base64 in 'image_data'."""
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = ues.get_editor_world()
        if not world:
            return json.dumps({"success": False, "message": "No editor world is open."})
        info = ues.get_level_viewport_camera_info()
        loc, rot = info if info else (unreal.Vector(0, 0, 300), unreal.Rotator(0, 0, 0))
        img, w, h = _capture_scene(world, loc, rot, width, height, fov)
        return json.dumps({"success": True, "image_data": img, "width": w, "height": h,
                           "camera_location": [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)],
                           "camera_rotation": [round(rot.pitch, 2), round(rot.yaw, 2), round(rot.roll, 2)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_capture_from(location: list = None, rotation: list = None,
                    width: int = 1280, height: int = 720, fov: float = 90.0) -> str:
    """Captures the scene from an explicit camera pose. location=[x,y,z], rotation=[pitch,yaw,roll]."""
    if location is None or rotation is None:
        return json.dumps({"success": False, "message": "Required parameters: location, rotation."})
    if len(location) != 3 or len(rotation) != 3:
        return json.dumps({"success": False, "message": "location and rotation must be lists of 3 floats."})
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if not world:
            return json.dumps({"success": False, "message": "No editor world is open."})
        loc = unreal.Vector(float(location[0]), float(location[1]), float(location[2]))
        rot = unreal.Rotator(float(rotation[0]), float(rotation[1]), float(rotation[2]))
        img, w, h = _capture_scene(world, loc, rot, width, height, fov)
        return json.dumps({"success": True, "image_data": img, "width": w, "height": h,
                           "camera_location": location, "camera_rotation": rotation})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_capture_actors(actor_labels: list = None, width: int = 1280, height: int = 720,
                      fov: float = 60.0, padding: float = 1.6) -> str:
    """Frames the given actors (by label) from an elevated 3/4 view and captures them as a PNG."""
    if not actor_labels:
        return json.dumps({"success": False, "message": "Required parameter 'actor_labels' is missing."})
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if not world:
            return json.dumps({"success": False, "message": "No editor world is open."})

        mins = [None, None, None]
        maxs = [None, None, None]
        found = []
        for label in actor_labels:
            actor = _actor_by_label(label)
            if not actor:
                continue
            found.append(label)
            origin, extent = actor.get_actor_bounds(False)
            lo = [origin.x - extent.x, origin.y - extent.y, origin.z - extent.z]
            hi = [origin.x + extent.x, origin.y + extent.y, origin.z + extent.z]
            for i in range(3):
                mins[i] = lo[i] if mins[i] is None else min(mins[i], lo[i])
                maxs[i] = hi[i] if maxs[i] is None else max(maxs[i], hi[i])
        if not found:
            return json.dumps({"success": False, "message": f"No actors found: {actor_labels}"})

        center = unreal.Vector((mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2, (mins[2] + maxs[2]) / 2)
        radius = max(8.0, 0.5 * math.sqrt(
            (maxs[0] - mins[0]) ** 2 + (maxs[1] - mins[1]) ** 2 + (maxs[2] - mins[2]) ** 2))
        dist = (radius / math.tan(math.radians(fov) / 2.0)) * float(padding)

        d = unreal.Vector(1.0, -1.0, 0.7)
        d = d.normal()
        cam = unreal.Vector(center.x + d.x * dist, center.y + d.y * dist, center.z + d.z * dist)
        rot = unreal.MathLibrary.find_look_at_rotation(cam, center)

        img, w, h = _capture_scene(world, cam, rot, width, height, fov)
        return json.dumps({"success": True, "image_data": img, "width": w, "height": h,
                           "framed_actors": found,
                           "camera_location": [round(cam.x, 2), round(cam.y, 2), round(cam.z, 2)],
                           "camera_rotation": [round(rot.pitch, 2), round(rot.yaw, 2), round(rot.roll, 2)]})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
