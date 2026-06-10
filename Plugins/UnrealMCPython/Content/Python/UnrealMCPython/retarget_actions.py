# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""
IK Rig / IK Retargeter authoring and batch animation retargeting.

All actions require the IKRig plugin (a built-in engine plugin, usually enabled
by default). The dependency is soft: each action guards at call time and returns
an actionable error when the plugin is disabled.
"""
import unreal
import json
import traceback


def _plugin_missing():
    if not hasattr(unreal, "IKRigController"):
        return json.dumps({"success": False,
                           "message": "Requires the IKRig plugin. Enable it in Edit > Plugins and restart."})
    return None


def _load_typed(asset_path, cls, label):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        raise FileNotFoundError(f"{label} not found at path: {asset_path}")
    if not isinstance(asset, cls):
        raise TypeError(f"Asset at {asset_path} is not a {label}, but {type(asset).__name__}")
    return asset


def _split_asset_path(asset_path: str):
    asset_path = asset_path.rstrip("/")
    idx = asset_path.rfind("/")
    return asset_path[idx + 1:], asset_path[:idx]


def ue_create_ik_rig(asset_path: str = None, skeletal_mesh_path: str = None,
                     retarget_root: str = None) -> str:
    """Creates an IK Rig for a skeletal mesh, optionally setting the retarget root bone (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or skeletal_mesh_path is None:
        return json.dumps({"success": False, "message": "Required parameters: asset_path, skeletal_mesh_path."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        mesh = _load_typed(skeletal_mesh_path, unreal.SkeletalMesh, "SkeletalMesh")
        name, package = _split_asset_path(asset_path)
        rig = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, package, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
        if not rig:
            return json.dumps({"success": False, "message": f"Failed to create IK Rig at {asset_path}."})
        rc = unreal.IKRigController.get_controller(rig)
        if not rc.set_skeletal_mesh(mesh):
            return json.dumps({"success": False, "message": "set_skeletal_mesh failed (incompatible mesh?)."})
        root_set = None
        if retarget_root:
            root_set = bool(rc.set_retarget_root(retarget_root))
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "skeletal_mesh": skeletal_mesh_path, "retarget_root_set": root_set})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_add_retarget_chain(ik_rig_path: str = None, chain_name: str = None,
                          start_bone: str = None, end_bone: str = None, goal_name: str = "") -> str:
    """Adds a retarget chain (e.g. 'Spine': spine_01..spine_03) to an IK Rig (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if ik_rig_path is None or chain_name is None or start_bone is None or end_bone is None:
        return json.dumps({"success": False, "message": "Required: ik_rig_path, chain_name, start_bone, end_bone."})
    try:
        rig = _load_typed(ik_rig_path, unreal.IKRigDefinition, "IKRigDefinition")
        rc = unreal.IKRigController.get_controller(rig)
        created = rc.add_retarget_chain(chain_name, start_bone, end_bone, goal_name or "")
        if not str(created):
            return json.dumps({"success": False, "message": "add_retarget_chain returned an empty name (check bone names)."})
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        return json.dumps({"success": True, "ik_rig_path": ik_rig_path, "chain_name": str(created),
                           "chain_count": len(rc.get_retarget_chains())})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_get_ik_rig_info(ik_rig_path: str = None) -> str:
    """Returns the skeletal mesh, retarget root, and chains of an IK Rig (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if ik_rig_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'ik_rig_path' is missing."})
    try:
        rig = _load_typed(ik_rig_path, unreal.IKRigDefinition, "IKRigDefinition")
        rc = unreal.IKRigController.get_controller(rig)
        mesh = rc.get_skeletal_mesh()
        chains = []
        for ch in rc.get_retarget_chains():
            cname = str(getattr(ch, "chain_name", ""))
            chains.append({
                "name": cname,
                "start_bone": str(rc.get_retarget_chain_start_bone(cname)),
                "end_bone": str(rc.get_retarget_chain_end_bone(cname)),
            })
        return json.dumps({
            "success": True,
            "ik_rig_path": ik_rig_path,
            "skeletal_mesh": mesh.get_path_name() if mesh else None,
            "retarget_root": str(rc.get_retarget_root()),
            "chains": chains,
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_create_retargeter(asset_path: str = None, source_ik_rig_path: str = None,
                         target_ik_rig_path: str = None, auto_map: bool = True) -> str:
    """Creates an IK Retargeter wired to source/target IK Rigs, with optional fuzzy chain auto-mapping (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if asset_path is None or source_ik_rig_path is None or target_ik_rig_path is None:
        return json.dumps({"success": False, "message": "Required: asset_path, source_ik_rig_path, target_ik_rig_path."})
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return json.dumps({"success": False, "message": f"Asset already exists: {asset_path}"})
        src = _load_typed(source_ik_rig_path, unreal.IKRigDefinition, "IKRigDefinition")
        tgt = _load_typed(target_ik_rig_path, unreal.IKRigDefinition, "IKRigDefinition")
        name, package = _split_asset_path(asset_path)
        rtg = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, package, unreal.IKRetargeter, unreal.IKRetargetFactory())
        if not rtg:
            return json.dumps({"success": False, "message": f"Failed to create IK Retargeter at {asset_path}."})
        tc = unreal.IKRetargeterController.get_controller(rtg)
        tc.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src)
        tc.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, tgt)
        if auto_map:
            tc.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
        unreal.EditorAssetLibrary.save_loaded_asset(rtg)
        return json.dumps({"success": True, "asset_path": asset_path,
                           "source_ik_rig": source_ik_rig_path, "target_ik_rig": target_ik_rig_path,
                           "auto_mapped": bool(auto_map)})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_auto_map_chains(retargeter_path: str = None, mode: str = "FUZZY", force: bool = True) -> str:
    """Re-runs chain mapping on an IK Retargeter. mode: FUZZY, EXACT, or CLEAR (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if retargeter_path is None:
        return json.dumps({"success": False, "message": "Required parameter 'retargeter_path' is missing."})
    key = (mode or "FUZZY").upper()
    map_type = getattr(unreal.AutoMapChainType, key, None)
    if map_type is None:
        return json.dumps({"success": False, "message": f"Unknown mode '{mode}'.", "valid_modes": ["FUZZY", "EXACT", "CLEAR"]})
    try:
        rtg = _load_typed(retargeter_path, unreal.IKRetargeter, "IKRetargeter")
        tc = unreal.IKRetargeterController.get_controller(rtg)
        tc.auto_map_chains(map_type, bool(force))
        unreal.EditorAssetLibrary.save_loaded_asset(rtg)
        return json.dumps({"success": True, "retargeter_path": retargeter_path, "mode": key})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})


def ue_batch_retarget(retargeter_path: str = None, anim_paths: list = None,
                      source_mesh_path: str = None, target_mesh_path: str = None,
                      search: str = "", replace: str = "", prefix: str = "",
                      suffix: str = "_Retargeted") -> str:
    """Duplicates and retargets animations through an IK Retargeter; returns the new asset paths (requires the IKRig plugin)."""
    guard = _plugin_missing()
    if guard:
        return guard
    if retargeter_path is None or not anim_paths or source_mesh_path is None or target_mesh_path is None:
        return json.dumps({"success": False,
                           "message": "Required: retargeter_path, anim_paths (non-empty), source_mesh_path, target_mesh_path."})
    try:
        rtg = _load_typed(retargeter_path, unreal.IKRetargeter, "IKRetargeter")
        src_mesh = _load_typed(source_mesh_path, unreal.SkeletalMesh, "SkeletalMesh")
        tgt_mesh = _load_typed(target_mesh_path, unreal.SkeletalMesh, "SkeletalMesh")
        asset_data = []
        missing = []
        for p in anim_paths:
            ad = unreal.EditorAssetLibrary.find_asset_data(p)
            (asset_data.append(ad) if ad and ad.is_valid() else missing.append(p))
        if missing:
            return json.dumps({"success": False, "message": f"Animations not found: {missing}"})
        out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
            asset_data, src_mesh, tgt_mesh, rtg,
            search=search or "", replace=replace or "", prefix=prefix or "", suffix=suffix or "")
        paths = [str(a.package_name) for a in (out or [])]
        if not paths:
            return json.dumps({"success": False, "message": "duplicate_and_retarget produced no assets (check chain mapping)."})
        return json.dumps({"success": True, "retargeter_path": retargeter_path,
                           "count": len(paths), "retargeted_assets": paths})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e), "traceback": traceback.format_exc()})
