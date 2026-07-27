#!/usr/bin/env python3
"""One-shot bootstrap for literal ACTION_METADATA maps in Unreal action modules.

The generated maps are intentionally committed and reviewed. This script refuses
to overwrite any module that already owns an ACTION_METADATA assignment.
"""

import ast
from pathlib import Path
from pprint import pformat


MCP_SERVER_DIR = Path(__file__).parent
PLUGIN_DIR = (
    MCP_SERVER_DIR.parent
    / "Plugins"
    / "UnrealMCPython"
    / "Content"
    / "Python"
    / "UnrealMCPython"
)

DOMAINS = [
    "actor",
    "anim_blueprint",
    "animation",
    "asset",
    "behavior_tree",
    "blueprint",
    "control_rig",
    "data_table",
    "editor",
    "game",
    "gas",
    "layer",
    "level",
    "level_sequence",
    "material",
    "retarget",
    "static_mesh",
    "texture",
    "umg",
    "util",
    "vision",
]

READ_PREFIXES = ("get_", "list_", "find_", "is_", "capture_", "project_")
DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "rename_")
READ_ACTIONS = {
    "actor.line_trace",
    "asset.asset_exists",
    "data_table.does_row_exist",
    "util.screen_to_world",
    "util.world_to_screen",
}
DESTRUCTIVE_ACTIONS = {
    "anim_blueprint.build_anim_state_machine",
    "behavior_tree.build_behavior_tree",
    "blueprint.build_blueprint_graph",
    "data_table.set_rows_from_json",
    "editor.join_actors",
    "editor.merge_actors",
    "editor.replace_selected_with_bp",
    "game.set_game_mode",
    "gas.add_gameplay_tag",
    "gas.clear_effect_modifiers",
    "level.create_level",
    "level.load_level",
    "util.execute_console_command",
    "util.set_cvar",
}
HIGH_RISK_WRITES = {
    "blueprint.compile_blueprint",
    "control_rig.recompile_control_rig",
    "level.save_all_levels",
    "level.save_current_level",
    "level.set_world_settings",
    "material.recompile",
    "umg.compile_widget_blueprint",
    "util.save_all_dirty",
}
NO_PREVIEW_OR_UNDO = {
    "asset.export_fbx",
    "asset.import_fbx",
    "asset.import_gltf",
    "asset.import_texture",
    "data_table.export_to_csv",
    "editor.close_asset_editor",
    "editor.open_editor_for_asset",
    "level_sequence.close_sequencer",
    "level_sequence.open_in_sequencer",
    "util.execute_console_command",
    "util.print_message",
    "util.save_all_dirty",
    "util.set_cvar",
    "util.set_log_verbosity",
    "util.set_viewport_camera",
    "util.start_pie",
    "util.stop_pie",
} | HIGH_RISK_WRITES | {"asset.save_asset", "gas.add_gameplay_tag"}
NO_UNDO = NO_PREVIEW_OR_UNDO | HIGH_RISK_WRITES | {
    "level.create_level",
    "level.load_level",
    "level.save_all_levels",
    "level.save_current_level",
}
PLUGIN_REQUIREMENTS = {
    "control_rig": ["ControlRig"],
    "gas": ["GameplayAbilities"],
    "retarget": ["IKRig"],
}


def classify(domain: str, action: str) -> dict:
    qualified = f"{domain}.{action}"
    if action.startswith(READ_PREFIXES) or qualified in READ_ACTIONS:
        effect, risk = "read", "low"
    elif action.startswith(DESTRUCTIVE_PREFIXES) or qualified in DESTRUCTIVE_ACTIONS:
        effect, risk = "destructive", "high"
    else:
        effect, risk = "write", "medium"
    if qualified in HIGH_RISK_WRITES:
        effect, risk = "write", "high"

    supports_preview = effect != "read" and qualified not in NO_PREVIEW_OR_UNDO
    supports_undo = effect == "write" and qualified not in NO_UNDO
    return {
        "effect": effect,
        "risk": risk,
        "result_kind": (
            "image" if domain == "vision" and action.startswith("capture_") else "json"
        ),
        "idempotent": effect == "read",
        "supports_preview": supports_preview,
        "supports_undo": supports_undo,
        "requires_confirmation": effect != "read",
        "ue_versions": ["5.6", "5.7", "5.8"],
        "required_plugins": list(PLUGIN_REQUIREMENTS.get(domain, [])),
    }


def _is_string_or_list_annotation(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    text = ast.unparse(annotation).replace("typing.", "")
    return text in {"str", "list", "List[str]", "list[str]", "Optional[str]"}


def _asset_path_params(fn: ast.FunctionDef) -> list[str]:
    excluded = {"actor_paths", "file_path", "folder_path"}
    return [
        arg.arg
        for arg in fn.args.args
        if _is_string_or_list_annotation(arg.annotation)
        and arg.arg not in excluded
        and (arg.arg == "path" or arg.arg.endswith("_path") or arg.arg.endswith("_paths"))
    ]


def _metadata_for(domain: str, fn: ast.FunctionDef) -> dict:
    action = fn.name[3:]
    description = (ast.get_docstring(fn) or "").splitlines()
    first_line = description[0].strip() if description else ""
    metadata = {
        "title": action.replace("_", " ").title(),
        "description": first_line or action.replace("_", " ").capitalize() + ".",
        **classify(domain, action),
    }
    asset_path_params = _asset_path_params(fn)
    if asset_path_params:
        metadata["asset_path_params"] = asset_path_params
    if domain == "game" and action in {"add_input_action", "add_input_mapping"}:
        metadata["required_plugins"] = ["EnhancedInput"]
    return metadata


def _action_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("ue_")
    ]


def _has_metadata(tree: ast.Module) -> bool:
    return any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and (
            any(isinstance(target, ast.Name) and target.id == "ACTION_METADATA" for target in node.targets)
            if isinstance(node, ast.Assign)
            else isinstance(node.target, ast.Name) and node.target.id == "ACTION_METADATA"
        )
        for node in tree.body
    )


def main() -> None:
    pending: list[tuple[Path, str, dict]] = []
    for domain in DOMAINS:
        path = PLUGIN_DIR / f"{domain}_actions.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        if _has_metadata(tree):
            raise SystemExit(f"Refusing to overwrite ACTION_METADATA in {path}")
        metadata = {
            fn.name[3:]: _metadata_for(domain, fn) for fn in _action_functions(tree)
        }
        pending.append((path, source, metadata))

    for path, source, metadata in pending:
        rendered = pformat(metadata, width=100, sort_dicts=True)
        path.write_text(
            source.rstrip() + "\n\n\n# Literal metadata consumed by mcp-server/generate_catalog.py.\n"
            f"ACTION_METADATA = {rendered}\n",
            encoding="utf-8",
        )
        print(f"Wrote {path.name}: {len(metadata)} actions")


if __name__ == "__main__":
    main()
