# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Python action functions for Texture assets (info + import settings)."""
import unreal
import json
import traceback


def _load_texture(asset_path: str):
    if not asset_path:
        raise ValueError("Texture path cannot be empty.")
    tex = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not tex:
        raise FileNotFoundError(f"Texture not found at path: {asset_path}")
    if not isinstance(tex, unreal.Texture2D):
        raise TypeError(f"Asset at {asset_path} is not a Texture2D, but {type(tex).__name__}")
    return tex


def _save(tex):
    if hasattr(tex, "update_resource"):
        tex.update_resource()
    unreal.EditorAssetLibrary.save_loaded_asset(tex)


def ue_get_texture_info(asset_path: str = None) -> str:
    """Returns size, memory, sRGB, and compression settings of a Texture2D."""
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        tex = _load_texture(asset_path)
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "width": tex.blueprint_get_size_x(),
            "height": tex.blueprint_get_size_y(),
            "memory_size": tex.blueprint_get_memory_size(),
            "srgb": bool(tex.get_editor_property("srgb")),
            "compression_settings": str(tex.get_editor_property("compression_settings")).split(".")[-1].split(":")[0].rstrip(">").strip(),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_texture_srgb(asset_path: str = None, srgb: bool = None) -> str:
    """Sets the sRGB flag on a Texture2D."""
    if asset_path is None or srgb is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, srgb."})
    try:
        tex = _load_texture(asset_path)
        tex.set_editor_property("srgb", bool(srgb))
        _save(tex)
        return json.dumps({"success": True, "asset_path": asset_path, "srgb": bool(srgb)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_texture_compression(asset_path: str = None, compression: str = None) -> str:
    """Sets the compression settings of a Texture2D (e.g. 'TC_DEFAULT', 'TC_NORMALMAP', 'TC_MASKS', 'TC_GRAYSCALE')."""
    if asset_path is None or compression is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, compression."})
    key = compression.upper()
    if not key.startswith("TC_"):
        key = "TC_" + key
    enum_val = getattr(unreal.TextureCompressionSettings, key, None)
    if enum_val is None:
        valid = [v for v in dir(unreal.TextureCompressionSettings) if v.startswith("TC_")]
        return json.dumps({"success": False, "message": f"Unknown compression '{compression}'.", "valid": valid})
    try:
        tex = _load_texture(asset_path)
        tex.set_editor_property("compression_settings", enum_val)
        _save(tex)
        return json.dumps({"success": True, "asset_path": asset_path, "compression": key})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
