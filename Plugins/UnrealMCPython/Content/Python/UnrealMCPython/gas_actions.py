# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
Gameplay Ability System (GAS) authoring: GameplayAbility / GameplayEffect
blueprints, effect modifiers, ability tags & costs, and GameplayTags config.

All actions require the GameplayAbilities plugin (soft runtime dependency —
guarded per action). Property-level notes that shape the implementation:

- GameplayModifierInfo.attribute is edit-defaults-only, so modifiers are
  assembled through struct import_text (which bypasses per-property edit
  checks) and assigned to the CDO's `modifiers` array wholesale.
- GameplayTag/GameplayTagContainer import_text silently drops tags that are
  not registered in the project's tag table, so tag setters report which tags
  actually resolved.
- GameplayTagsManager is not exposed to Python; tag registration goes through
  Config/DefaultGameplayTags.ini and needs an editor restart to take effect.
"""
import unreal
import json
import os
import re
import traceback

_OP_MAP = {
    "add_base": "AddBase",
    "add_final": "AddFinal",
    "multiply_additive": "MultiplyAdditive",
    "multiply_compound": "MultiplyCompound",
    "divide_additive": "DivideAdditive",
    "override": "Override",
}

_DURATION_MAP = {
    "instant": "INSTANT",
    "has_duration": "HAS_DURATION",
    "infinite": "INFINITE",
}


def _plugin_missing():
    if not hasattr(unreal, "GameplayAbility"):
        return json.dumps({"success": False,
                           "message": "Requires the GameplayAbilities plugin. Enable it in Edit > Plugins and restart."})
    return None


def _split_asset_path(asset_path: str):
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


def _load_cdo(asset_path: str, expected_class, label: str):
    bp = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not bp:
        raise FileNotFoundError(f"Blueprint not found at path: {asset_path}")
    if not isinstance(bp, unreal.Blueprint):
        raise TypeError(f"Asset at {asset_path} is not a Blueprint, but {type(bp).__name__}")
    gen = bp.generated_class()
    cdo = unreal.get_default_object(gen)
    if not isinstance(cdo, expected_class):
        raise TypeError(f"Blueprint at {asset_path} is not a {label} (CDO is {type(cdo).__name__}).")
    return bp, cdo


def _create_gas_blueprint(asset_path: str, parent_class):
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise FileExistsError(f"Asset already exists: {asset_path}")
    name, package = _split_asset_path(asset_path)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package, unreal.Blueprint, factory)
    if not bp:
        raise RuntimeError(f"Failed to create blueprint at {asset_path}.")
    return bp


def _tag_container_from(tags):
    """Build a GameplayTagContainer from tag name strings.
    Returns (container, resolved, unresolved) — unregistered tags do not import."""
    container = unreal.GameplayTagContainer()
    resolved, unresolved = [], []
    for name in tags:
        tag = unreal.GameplayTag()
        tag.import_text(str(name))
        # Unregistered tags import with TagName 'None' (the literal string).
        imported = str(tag.get_editor_property("tag_name"))
        if imported and imported != "None":
            resolved.append(str(name))
        else:
            unresolved.append(str(name))
    if resolved:
        inner = ",".join(f'(TagName="{t}")' for t in resolved)
        container.import_text(f"(GameplayTags=({inner}))")
    return container, resolved, unresolved


def _tags_ini_path():
    return os.path.join(unreal.Paths.project_config_dir(), "DefaultGameplayTags.ini")


# --- GameplayAbility ------------------------------------------------------------

def ue_create_ability_blueprint(asset_path: str = None, parent_class_path: str = None) -> str:
    """Creates a GameplayAbility blueprint; parent_class_path may point at a custom GA subclass (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        parent = unreal.GameplayAbility
        if parent_class_path:
            parent = unreal.load_class(None, parent_class_path)
            if not parent:
                return json.dumps({"success": False, "message": f"Could not load class: {parent_class_path}"})
        bp = _create_gas_blueprint(asset_path, parent)
        cdo = unreal.get_default_object(bp.generated_class())
        if not isinstance(cdo, unreal.GameplayAbility):
            unreal.EditorAssetLibrary.delete_asset(asset_path)
            return json.dumps({"success": False, "message": f"{parent_class_path} is not a GameplayAbility subclass."})
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        parent_path = (parent.get_path_name() if isinstance(parent, unreal.Class)
                       else parent.static_class().get_path_name())
        return json.dumps({"success": True, "asset_path": asset_path,
                           "parent_class": parent_path})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_ability_info(asset_path: str = None) -> str:
    """Returns parent class, ability tags, and cost/cooldown effect classes of a GameplayAbility blueprint (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayAbility, "GameplayAbility")
        tags = re.findall(r'TagName="([^"]+)"', cdo.get_editor_property("ability_tags").export_text())
        cost = cdo.get_editor_property("cost_gameplay_effect_class")
        cooldown = cdo.get_editor_property("cooldown_gameplay_effect_class")
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "parent_class": bp.generated_class().get_path_name(),
            "ability_tags": tags,
            "cost_effect": cost.get_path_name() if cost else None,
            "cooldown_effect": cooldown.get_path_name() if cooldown else None,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_ability_tags(asset_path: str = None, tags: list = None) -> str:
    """Sets the AbilityTags container on a GameplayAbility; unregistered tags are reported, not silently dropped (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or tags is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, tags (list of tag names)."})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayAbility, "GameplayAbility")
        container, resolved, unresolved = _tag_container_from(tags)
        cdo.set_editor_property("ability_tags", container)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        result = {"success": True, "asset_path": asset_path,
                  "resolved_tags": resolved, "unresolved_tags": unresolved}
        if unresolved:
            result["message"] = ("Some tags are not registered in the project tag table "
                                 "(add them via add_gameplay_tag and restart the editor).")
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_ability_costs(asset_path: str = None, cost_effect_path: str = None,
                         cooldown_effect_path: str = None) -> str:
    """Wires cost and/or cooldown GameplayEffect blueprints onto a GameplayAbility (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or (cost_effect_path is None and cooldown_effect_path is None):
        return json.dumps({"success": False,
                           "message": "Required: asset_path and at least one of cost_effect_path / cooldown_effect_path."})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayAbility, "GameplayAbility")
        applied = {}
        for prop, path in (("cost_gameplay_effect_class", cost_effect_path),
                           ("cooldown_gameplay_effect_class", cooldown_effect_path)):
            if path:
                _, effect_cdo = _load_cdo(path, unreal.GameplayEffect, "GameplayEffect")
                cdo.set_editor_property(prop, effect_cdo.get_class())
                applied[prop] = path
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path, "applied": applied})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- GameplayEffect -------------------------------------------------------------

def ue_create_effect_blueprint(asset_path: str = None, duration_policy: str = "instant",
                               duration_seconds: float = None) -> str:
    """Creates a GameplayEffect blueprint with a duration policy: instant, has_duration (+seconds), or infinite (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    key = (duration_policy or "instant").lower()
    if key not in _DURATION_MAP:
        return json.dumps({"success": False, "message": f"Unknown duration_policy '{duration_policy}'.",
                           "valid_policies": list(_DURATION_MAP)})
    try:
        bp = _create_gas_blueprint(asset_path, unreal.GameplayEffect)
        cdo = unreal.get_default_object(bp.generated_class())
        cdo.set_editor_property("duration_policy",
                                getattr(unreal.GameplayEffectDurationType, _DURATION_MAP[key]))
        if key == "has_duration" and duration_seconds is not None:
            mm = unreal.GameplayEffectModifierMagnitude()
            mm.import_text(f"(MagnitudeCalculationType=ScalableFloat,"
                           f"ScalableFloatMagnitude=(Value={float(duration_seconds)}))")
            cdo.set_editor_property("duration_magnitude", mm)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "duration_policy": key, "duration_seconds": duration_seconds})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_effect_info(asset_path: str = None) -> str:
    """Returns duration policy/seconds and decoded modifiers of a GameplayEffect blueprint (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayEffect, "GameplayEffect")
        policy = cdo.get_editor_property("duration_policy")
        policy_name = getattr(policy, "name", str(policy)).lower()
        duration = None
        if policy_name == "has_duration":
            m = re.search(r"Value=([\d.]+)", cdo.get_editor_property("duration_magnitude").export_text())
            duration = float(m.group(1)) if m else None
        rev_op = {v: k for k, v in _OP_MAP.items()}
        modifiers = []
        for mod in cdo.get_editor_property("modifiers"):
            text = mod.export_text()
            attr = re.search(r'AttributeName="([^"]+)"', text)
            attr_set = re.search(r"Attribute=([^,)]+):", text)
            op = re.search(r"ModifierOp=(\w+)", text)
            mag = re.search(r"ScalableFloatMagnitude=\(Value=([\d.-]+)", text)
            modifiers.append({
                "attribute": attr.group(1) if attr else None,
                "attribute_set": attr_set.group(1) if attr_set else None,
                "op": rev_op.get(op.group(1), op.group(1)) if op else "add_base",
                "magnitude": float(mag.group(1)) if mag else None,
            })
        return json.dumps({
            "success": True,
            "asset_path": asset_path,
            "duration_policy": policy_name,
            "duration_seconds": duration,
            "modifiers": modifiers,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_set_effect_duration(asset_path: str = None, duration_policy: str = None,
                           duration_seconds: float = None) -> str:
    """Changes a GameplayEffect's duration policy (instant / has_duration+seconds / infinite) (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or duration_policy is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, duration_policy."})
    key = duration_policy.lower()
    if key not in _DURATION_MAP:
        return json.dumps({"success": False, "message": f"Unknown duration_policy '{duration_policy}'.",
                           "valid_policies": list(_DURATION_MAP)})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayEffect, "GameplayEffect")
        cdo.set_editor_property("duration_policy",
                                getattr(unreal.GameplayEffectDurationType, _DURATION_MAP[key]))
        if key == "has_duration" and duration_seconds is not None:
            mm = unreal.GameplayEffectModifierMagnitude()
            mm.import_text(f"(MagnitudeCalculationType=ScalableFloat,"
                           f"ScalableFloatMagnitude=(Value={float(duration_seconds)}))")
            cdo.set_editor_property("duration_magnitude", mm)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "duration_policy": key, "duration_seconds": duration_seconds})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_effect_modifier(asset_path: str = None, attribute_set_path: str = None,
                           attribute_name: str = None, op: str = "add_base",
                           magnitude: float = 1.0) -> str:
    """Appends an attribute modifier (e.g. Health add_base +25) to a GameplayEffect. attribute_set_path is the AttributeSet class path (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or attribute_set_path is None or attribute_name is None:
        return json.dumps({"success": False,
                           "message": "Required: asset_path, attribute_set_path, attribute_name."})
    op_key = (op or "add_base").lower()
    if op_key not in _OP_MAP:
        return json.dumps({"success": False, "message": f"Unknown op '{op}'.", "valid_ops": list(_OP_MAP)})
    try:
        attr_set_class = unreal.load_class(None, attribute_set_path)
        if not attr_set_class:
            return json.dumps({"success": False, "message": f"AttributeSet class not found: {attribute_set_path}"})
        try:
            unreal.get_default_object(attr_set_class).get_editor_property(attribute_name)
        except Exception:
            return json.dumps({"success": False,
                               "message": f"Attribute '{attribute_name}' not found on {attribute_set_path}."})
        bp, cdo = _load_cdo(asset_path, unreal.GameplayEffect, "GameplayEffect")
        # GameplayModifierInfo.attribute is edit-defaults-only, so the whole
        # struct is assembled via import_text instead of per-property setters.
        mod = unreal.GameplayModifierInfo()
        mod.import_text(
            f'(Attribute=(AttributeName="{attribute_name}",'
            f'Attribute={attribute_set_path}:{attribute_name}),'
            f'ModifierOp={_OP_MAP[op_key]},'
            f'ModifierMagnitude=(MagnitudeCalculationType=ScalableFloat,'
            f'ScalableFloatMagnitude=(Value={float(magnitude)})))')
        mods = list(cdo.get_editor_property("modifiers"))
        mods.append(mod)
        cdo.set_editor_property("modifiers", mods)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "attribute": attribute_name, "op": op_key,
                           "magnitude": float(magnitude), "modifier_count": len(mods)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_clear_effect_modifiers(asset_path: str = None) -> str:
    """Removes all modifiers from a GameplayEffect blueprint (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'asset_path' is missing."})
    try:
        bp, cdo = _load_cdo(asset_path, unreal.GameplayEffect, "GameplayEffect")
        cdo.set_editor_property("modifiers", [])
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return json.dumps({"success": True, "asset_path": asset_path, "modifier_count": 0})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


# --- GameplayTags ---------------------------------------------------------------

def ue_list_gameplay_tags(prefix: str = "") -> str:
    """Lists gameplay tags registered in Config/DefaultGameplayTags.ini, optionally filtered by prefix (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    try:
        ini = _tags_ini_path()
        tags = []
        if os.path.isfile(ini):
            with open(ini, "r", encoding="utf-8") as f:
                tags = re.findall(r'\+GameplayTagList=\(Tag="([^"]+)"', f.read())
        if prefix:
            tags = [t for t in tags if t.startswith(prefix)]
        return json.dumps({"success": True, "count": len(tags), "tags": sorted(tags),
                           "ini_path": ini})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_gameplay_tag(tag: str = None, comment: str = "") -> str:
    """Registers a gameplay tag in Config/DefaultGameplayTags.ini — takes effect after an editor restart (requires the GameplayAbilities plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if not tag:
        return json.dumps({"success": False, "message": "Required parameter 'tag' is missing."})
    if not re.fullmatch(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*", tag):
        return json.dumps({"success": False,
                           "message": f"Invalid tag '{tag}' (use Dot.Separated.Alphanumerics)."})
    try:
        ini = _tags_ini_path()
        section = "[/Script/GameplayTags.GameplayTagsSettings]"
        entry = f'+GameplayTagList=(Tag="{tag}",DevComment="{comment}")'
        content = ""
        if os.path.isfile(ini):
            with open(ini, "r", encoding="utf-8") as f:
                content = f.read()
        if f'Tag="{tag}"' in content:
            return json.dumps({"success": False, "message": f"Tag '{tag}' is already registered."})
        if section in content:
            content = content.replace(section, f"{section}\n{entry}", 1)
        else:
            content = (content.rstrip() + f"\n\n{section}\n{entry}\n") if content.strip() else f"{section}\n{entry}\n"
        with open(ini, "w", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"success": True, "tag": tag, "ini_path": ini,
                           "message": "Tag registered in config. Restart the editor for it to become usable."})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
