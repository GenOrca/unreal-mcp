# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Vision: capture the active level viewport as a PNG.

Uses a transient SceneCapture2D placed at the viewport camera, rendered to an
RGBA8 render target and exported to PNG. This works regardless of editor focus
(unlike take_high_res_screenshot, which only fires when the viewport renders a
frame), and captures the 3D scene only — no editor UI.

The action returns the PNG base64-encoded in 'image_data'; the dispatcher's
vision handler decodes it into an MCP Image.
"""
import unreal
import json
import os
import base64
import tempfile
import traceback


def ue_capture_viewport(width: int = 1280, height: int = 720, fov: float = 90.0) -> str:
    """Captures the active level viewport (3D scene only) as a PNG, returned base64 in 'image_data'."""
    cap_actor = None
    out_path = None
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = ues.get_editor_world()
        if not world:
            return json.dumps({"success": False, "message": "No editor world is open."})

        info = ues.get_level_viewport_camera_info()
        if info:
            loc, rot = info
        else:
            loc, rot = unreal.Vector(0, 0, 300), unreal.Rotator(0, 0, 0)

        width = max(64, min(int(width), 4096))
        height = max(64, min(int(height), 4096))

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
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        return json.dumps({
            "success": True,
            "image_data": image_b64,
            "width": width,
            "height": height,
            "camera_location": [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)],
            "camera_rotation": [round(rot.pitch, 2), round(rot.yaw, 2), round(rot.roll, 2)],
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
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
