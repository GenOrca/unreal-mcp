"""Generated Action Registry v2 completeness and safety tests."""

import sys
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parents[1]))

from generate_catalog import build_registry
from unreal_mcp.contracts import ToolResult


def test_every_catalog_action_has_complete_registry_spec():
    registry = build_registry()
    for domain, actions in registry.items():
        for action, spec in actions.items():
            assert spec["domain"] == domain
            assert spec["action"] == action
            assert spec["effect"] in {"read", "write", "destructive"}
            assert spec["risk"] in {"low", "medium", "high"}
            assert spec["result_kind"] in {"json", "image", "text", "mixed"}
            assert spec["input_schema"]["type"] == "object"
            assert spec["examples"], f"{domain}.{action} has no valid-call example"
            assert spec["error_examples"], f"{domain}.{action} has no error example"
            for example in spec["examples"]:
                assert example["action"] == action
                Draft202012Validator(spec["input_schema"]).validate(example["params"])
            for error_example in spec["error_examples"]:
                ToolResult.model_validate(error_example)


def test_destructive_actions_require_confirmation():
    registry = build_registry()
    destructive = [
        spec
        for actions in registry.values()
        for spec in actions.values()
        if spec["effect"] == "destructive"
    ]
    assert destructive
    assert all(spec["requires_confirmation"] for spec in destructive)


def test_opaque_saves_compiles_and_project_config_do_not_claim_undo_or_preview():
    registry = build_registry()
    opaque_actions = [
        ("asset", "save_asset"),
        ("blueprint", "compile_blueprint"),
        ("control_rig", "recompile_control_rig"),
        ("gas", "add_gameplay_tag"),
        ("level", "save_all_levels"),
        ("level", "save_current_level"),
        ("level", "set_world_settings"),
        ("material", "recompile"),
        ("umg", "compile_widget_blueprint"),
        ("util", "save_all_dirty"),
    ]
    for domain, action in opaque_actions:
        spec = registry[domain][action]
        assert spec["supports_preview"] is False, f"{domain}.{action}"
        assert spec["supports_undo"] is False, f"{domain}.{action}"

    project_config = registry["gas"]["add_gameplay_tag"]
    assert project_config["effect"] == "destructive"
    assert project_config["risk"] == "high"


def test_whole_structure_replacements_are_classified_as_destructive():
    registry = build_registry()
    replacements = [
        ("anim_blueprint", "build_anim_state_machine"),
        ("behavior_tree", "build_behavior_tree"),
        ("blueprint", "build_blueprint_graph"),
        ("data_table", "set_rows_from_json"),
        ("gas", "clear_effect_modifiers"),
    ]
    for domain, action in replacements:
        spec = registry[domain][action]
        assert spec["effect"] == "destructive", f"{domain}.{action}"
        assert spec["risk"] == "high", f"{domain}.{action}"
        assert spec["requires_confirmation"] is True, f"{domain}.{action}"
