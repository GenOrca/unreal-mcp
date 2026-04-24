# Copyright (c) 2025 GenOrca. All Rights Reserved.

import unreal
import json
import traceback

VISIBILITY_MAP = {
    "visible": unreal.SlateVisibility.VISIBLE,
    "collapsed": unreal.SlateVisibility.COLLAPSED,
    "hidden": unreal.SlateVisibility.HIDDEN,
    "hit_test_invisible": unreal.SlateVisibility.HIT_TEST_INVISIBLE,
    "self_hit_test_invisible": unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE,
}

SUPPORTED_WIDGET_TYPES = [
    "CanvasPanel", "TextBlock", "Button", "Image",
    "HorizontalBox", "VerticalBox", "Border", "Overlay",
    "ScrollBox", "SizeBox", "CheckBox", "EditableText",
    "EditableTextBox", "ProgressBar", "Slider",
]


def _load_widget_blueprint(asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if asset is None:
        return None, json.dumps({"success": False, "message": f"Asset not found: {asset_path}"})
    if not isinstance(asset, unreal.WidgetBlueprint):
        return None, json.dumps({
            "success": False,
            "message": f"Asset at '{asset_path}' is {type(asset).__name__}, expected WidgetBlueprint."
        })
    return asset, None


# ─── Actions ──────────────────────────────────────────────────────────────────

def ue_create_widget_blueprint(name: str = None, path: str = None, parent_class: str = "UserWidget") -> str:
    if name is None:
        return json.dumps({"success": False, "message": "Required parameter 'name' is missing."})
    if path is None:
        return json.dumps({"success": False, "message": "Required parameter 'path' is missing."})
    try:
        parent_cls = unreal.load_class(None, f"/Script/UMG.{parent_class}")
        if parent_cls is None:
            parent_cls = unreal.UserWidget

        factory = unreal.WidgetBlueprintFactory()
        factory.set_editor_property("parent_class", parent_cls)

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        widget_bp = asset_tools.create_asset(name, path, unreal.WidgetBlueprint, factory)

        if widget_bp is None:
            return json.dumps({"success": False, "message": f"Failed to create Widget Blueprint '{name}' at '{path}'."})

        unreal.EditorAssetLibrary.save_asset(widget_bp.get_path_name())

        return json.dumps({
            "success": True,
            "asset_path": widget_bp.get_path_name(),
            "message": f"Widget Blueprint '{name}' created successfully."
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_widget_blueprint_info(asset_path: str = None) -> str:
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        widget_bp, err = _load_widget_blueprint(asset_path)
        if err:
            return err

        result_json = unreal.MCPythonHelper.umg_get_widget_info(widget_bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_widget(asset_path: str = None, widget_type: str = None,
                  widget_name: str = None, parent_name: str = None) -> str:
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if widget_type is None:
        return json.dumps({"success": False, "message": "Required parameter 'widget_type' is missing."})
    if widget_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'widget_name' is missing."})

    if widget_type not in SUPPORTED_WIDGET_TYPES:
        return json.dumps({
            "success": False,
            "message": f"Unknown widget type '{widget_type}'. Supported: {SUPPORTED_WIDGET_TYPES}"
        })

    try:
        widget_bp, err = _load_widget_blueprint(asset_path)
        if err:
            return err

        result_json = unreal.MCPythonHelper.umg_add_widget(
            widget_bp, widget_type, widget_name, parent_name or ""
        )

        # Save after successful add
        parsed = json.loads(result_json)
        if parsed.get("success"):
            unreal.EditorAssetLibrary.save_asset(widget_bp.get_path_name())

        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_widget_properties(asset_path: str = None, widget_name: str = None, properties: dict = None) -> str:
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if widget_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'widget_name' is missing."})
    if properties is None:
        return json.dumps({"success": False, "message": "Required parameter 'properties' is missing."})

    try:
        widget_bp, err = _load_widget_blueprint(asset_path)
        if err:
            return err

        widget = unreal.MCPythonHelper.umg_find_widget(widget_bp, widget_name)
        if widget is None:
            return json.dumps({"success": False, "message": f"Widget '{widget_name}' not found in blueprint."})

        set_ok = {}
        errors = {}

        for key, value in properties.items():
            if key.startswith("slot_"):
                continue
            try:
                if key == "text":
                    widget.set_editor_property("text", unreal.Text.cast(str(value)))
                elif key == "hint_text":
                    widget.set_editor_property("hint_text", unreal.Text.cast(str(value)))
                elif key == "tool_tip_text":
                    widget.set_editor_property("tool_tip_text", unreal.Text.cast(str(value)))
                elif key == "visibility":
                    vis = VISIBILITY_MAP.get(str(value).lower())
                    if vis is None:
                        errors[key] = f"Unknown visibility '{value}'. Valid: {list(VISIBILITY_MAP.keys())}"
                        continue
                    widget.set_editor_property("visibility", vis)
                elif key in ("color_and_opacity", "background_color") and isinstance(value, list):
                    r, g, b = float(value[0]), float(value[1]), float(value[2])
                    a = float(value[3]) if len(value) > 3 else 1.0
                    slate_color = unreal.SlateColor()
                    slate_color.set_editor_property("specified_color", unreal.LinearColor(r=r, g=g, b=b, a=a))
                    widget.set_editor_property(key, slate_color)
                elif key == "font_size" and isinstance(widget, unreal.TextBlock):
                    font_info = widget.get_editor_property("font")
                    font_info.set_editor_property("size", int(value))
                    widget.set_editor_property("font", font_info)
                elif key == "percent":
                    widget.set_editor_property("percent", float(value))
                elif key == "value":
                    widget.set_editor_property("value", float(value))
                else:
                    widget.set_editor_property(key, value)
                set_ok[key] = "ok"
            except Exception as prop_err:
                errors[key] = str(prop_err)

        # Slot properties
        slot_props = {k[5:]: v for k, v in properties.items() if k.startswith("slot_")}
        if slot_props:
            parent = widget.get_parent()
            slot = getattr(widget, "slot", None)
            if slot is None or parent is None:
                for k in slot_props:
                    errors[f"slot_{k}"] = "Widget has no parent slot."
            else:
                is_canvas_slot = isinstance(slot, unreal.CanvasPanelSlot)
                for slot_key, slot_val in slot_props.items():
                    try:
                        if slot_key in ("position", "size", "alignment", "z_order") and not is_canvas_slot:
                            errors[f"slot_{slot_key}"] = (
                                f"'{slot.get_class().get_name()}' does not support slot_{slot_key}. "
                                "These properties only apply to CanvasPanel children."
                            )
                            continue
                        if slot_key == "position" and isinstance(slot_val, list):
                            slot.set_position(unreal.Vector2D(float(slot_val[0]), float(slot_val[1])))
                        elif slot_key == "size" and isinstance(slot_val, list):
                            slot.set_size(unreal.Vector2D(float(slot_val[0]), float(slot_val[1])))
                        elif slot_key == "alignment" and isinstance(slot_val, list):
                            slot.set_alignment(unreal.Vector2D(float(slot_val[0]), float(slot_val[1])))
                        elif slot_key == "z_order":
                            slot.set_z_order(int(slot_val))
                        else:
                            slot.set_editor_property(slot_key, slot_val)
                        set_ok[f"slot_{slot_key}"] = "ok"
                    except Exception as slot_err:
                        errors[f"slot_{slot_key}"] = str(slot_err)

        if len(errors) == 0:
            unreal.EditorAssetLibrary.save_asset(widget_bp.get_path_name())

        return json.dumps({
            "success": len(errors) == 0,
            "set": set_ok,
            "errors": errors
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_remove_widget(asset_path: str = None, widget_name: str = None) -> str:
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    if widget_name is None:
        return json.dumps({"success": False, "message": "Required parameter 'widget_name' is missing."})
    try:
        widget_bp, err = _load_widget_blueprint(asset_path)
        if err:
            return err

        result_json = unreal.MCPythonHelper.umg_remove_widget(widget_bp, widget_name)

        parsed = json.loads(result_json)
        if parsed.get("success"):
            unreal.EditorAssetLibrary.save_asset(widget_bp.get_path_name())

        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_compile_widget_blueprint(asset_path: str = None) -> str:
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        widget_bp, err = _load_widget_blueprint(asset_path)
        if err:
            return err
        result_json = unreal.MCPythonHelper.compile_blueprint(widget_bp)
        return result_json
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
