#!/usr/bin/env python3
# Copyright (c) 2025 GenOrca. All Rights Reserved.

"""Generate the legacy dispatcher catalog and rich Action Registry v2.

Function signatures and docstrings come from the Unreal plugin action modules.
Safety and capability declarations come from their literal ACTION_METADATA maps.
Both generated files are checked in CI so runtime routing and LLM discovery
cannot silently drift apart.
"""

import ast
import json
from pathlib import Path
from pprint import pformat
import sys
from typing import Any

from jsonschema import Draft202012Validator

from unreal_mcp.contracts import ActionSpec, ToolResult


MCP_SERVER_DIR = Path(__file__).parent
PLUGIN_DIR = (
    MCP_SERVER_DIR.parent
    / "Plugins"
    / "UnrealMCPython"
    / "Content"
    / "Python"
    / "UnrealMCPython"
)
CATALOG_OUTPUT = MCP_SERVER_DIR / "src" / "unreal_mcp" / "dispatchers" / "_catalog.py"
REGISTRY_OUTPUT = MCP_SERVER_DIR / "src" / "unreal_mcp" / "dispatchers" / "_registry.py"
SPECIAL_SPECS_FILE = MCP_SERVER_DIR / "src" / "unreal_mcp" / "special_action_specs.py"

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

# Dispatcher-only actions still need their exact legacy parameter strings.
EXTRA_ACTIONS = {
    "util": {
        "execute_python": {
            "params": "code",
            "doc": "Runs arbitrary Unreal Python code. Full API access; fastest path to prototype new actions.",
        },
        "livecoding_compile": {
            "params": "",
            "doc": "Triggers C++ Live Coding and waits for the compile result.",
        },
        "search_actions": {
            "params": "query='', domain='', effect='', risk='', required_plugin='', limit=20, cursor=''",
            "doc": "Searches Action Registry v2 using text, safety filters, and cursor pagination.",
        },
        "describe_action": {
            "params": "domain, action",
            "doc": "Returns the complete schema and safety contract for one action.",
        },
        "get_capabilities": {
            "params": "",
            "doc": "Reports MCP server, Unreal editor, plugin, and safety capabilities.",
        },
    }
}

_MISSING = object()
_DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"success": {"type": "boolean"}},
    "required": ["success"],
    "additionalProperties": True,
}


def _params(fn: ast.FunctionDef) -> str:
    args = fn.args
    defaults = args.defaults
    pad = len(args.args) - len(defaults)
    parts = []
    for index, arg in enumerate(args.args):
        if index >= pad:
            default_node = defaults[index - pad]
            try:
                value = ast.literal_eval(default_node)
            except Exception:
                value = "..."
            # None is this repository's "required, validated inside" sentinel.
            parts.append(arg.arg if value is None else f"{arg.arg}={value!r}")
        else:
            parts.append(arg.arg)
    return ", ".join(parts)


def _doc(fn: ast.FunctionDef) -> str:
    docstring = ast.get_docstring(fn)
    return docstring.splitlines()[0].strip() if docstring else ""


def _action_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name[3:]: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("ue_")
    }


def _literal_assignment(tree: ast.Module, name: str) -> dict:
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value = node.value
        if value is not None:
            result = ast.literal_eval(value)
            if not isinstance(result, dict):
                raise ValueError(f"{name} must be a literal dict")
            return result
    raise ValueError(f"Missing literal {name}")


def _load_action_module(domain: str) -> tuple[dict[str, ast.FunctionDef], dict]:
    path = PLUGIN_DIR / f"{domain}_actions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodes = _action_nodes(tree)
    metadata = _literal_assignment(tree, "ACTION_METADATA")
    missing = sorted(set(nodes) - set(metadata))
    extra = sorted(set(metadata) - set(nodes))
    if missing or extra:
        raise ValueError(
            f"{path.name} ACTION_METADATA mismatch: missing={missing}, extra={extra}"
        )
    return nodes, metadata


def _extract(domain: str) -> dict:
    path = PLUGIN_DIR / f"{domain}_actions.py"
    actions: dict[str, dict] = {}
    if path.exists():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for action, node in _action_nodes(tree).items():
            actions[action] = {"params": _params(node), "doc": _doc(node)}
    actions.update(EXTRA_ACTIONS.get(domain, {}))
    return dict(sorted(actions.items()))


def build() -> dict:
    """Build the immutable legacy catalog view."""
    return {domain: _extract(domain) for domain in DOMAINS}


def _literal_default(node: ast.expr | None) -> Any:
    if node is None:
        return _MISSING
    try:
        value = ast.literal_eval(node)
    except Exception:
        return _MISSING
    if isinstance(value, tuple):
        return list(value)
    return value


def _annotation_schema(annotation: ast.expr | None, default: Any) -> dict[str, Any]:
    text = ast.unparse(annotation).replace("typing.", "") if annotation else ""
    simple_types = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "dict": "object",
        "Dict": "object",
        "list": "array",
        "List": "array",
    }
    if text in simple_types:
        schema = {"type": simple_types[text]}
        if schema["type"] == "array":
            schema["items"] = {}
        return schema
    if text.startswith(("list[", "List[")):
        inner = text[text.find("[") + 1 : -1]
        return {"type": "array", "items": _annotation_schema_from_text(inner)}
    if text.startswith("Optional["):
        return _annotation_schema_from_text(text[9:-1])
    if " | None" in text:
        return _annotation_schema_from_text(text.replace(" | None", ""))
    if default is not _MISSING and default is not None:
        if isinstance(default, bool):
            return {"type": "boolean"}
        if isinstance(default, int):
            return {"type": "integer"}
        if isinstance(default, float):
            return {"type": "number"}
        if isinstance(default, str):
            return {"type": "string"}
        if isinstance(default, list):
            return {"type": "array", "items": {}}
        if isinstance(default, dict):
            return {"type": "object"}
    return {}


def _annotation_schema_from_text(text: str) -> dict[str, Any]:
    scalar = {
        "str": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "bool": {"type": "boolean"},
    }
    return dict(scalar.get(text.strip(), {}))


def _input_schema(fn: ast.FunctionDef, metadata: dict) -> dict[str, Any]:
    if "input_schema" in metadata:
        return metadata["input_schema"]

    defaults = [None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
    no_default_count = len(fn.args.args) - len(fn.args.defaults)
    path_params = set(metadata.get("asset_path_params", []))
    overrides = metadata.get("parameter_schemas", {})
    properties: dict[str, dict] = {}
    required: list[str] = []

    for index, (arg, default_node) in enumerate(zip(fn.args.args, defaults)):
        default = _literal_default(default_node)
        schema = dict(overrides.get(arg.arg, _annotation_schema(arg.annotation, default)))
        if arg.arg in path_params:
            if schema.get("type") == "array":
                schema.setdefault("items", {})["format"] = "unreal-asset-path"
            else:
                schema["format"] = "unreal-asset-path"
        if index < no_default_count or default is None:
            required.append(arg.arg)
        elif default is not _MISSING:
            schema["default"] = default
        properties[arg.arg] = schema

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _example_value(schema: dict[str, Any]) -> Any:
    if schema.get("enum"):
        return schema["enum"][0]
    if schema.get("format") == "unreal-asset-path":
        return "/Game/Example"
    value_type = schema.get("type")
    if value_type == "string":
        return "example"
    if value_type == "integer":
        return 0
    if value_type == "number":
        return 0
    if value_type == "boolean":
        return False
    if value_type == "array":
        return []
    if value_type == "object":
        return {}
    return "example"


def _valid_example(action: str, schema: dict[str, Any]) -> dict[str, Any]:
    params = {
        name: _example_value(schema["properties"][name])
        for name in schema.get("required", [])
    }
    return {"action": action, "params": params}


def _error_example(domain: str, action: str, schema: dict[str, Any]) -> dict[str, Any]:
    required = schema.get("required", [])
    if required:
        parameter = required[0]
        message = f"{parameter} is required"
        path = f"params.{parameter}"
        hint = f"Provide params.{parameter} and retry."
    else:
        parameter = "unexpected"
        message = "unexpected is not an allowed parameter"
        path = "params.unexpected"
        hint = "Remove params.unexpected and retry."
    return {
        "success": False,
        "status": "failed",
        "summary": message,
        "data": {},
        "changes": [],
        "warnings": [],
        "errors": [
            {
                "code": "INVALID_INPUT",
                "path": path,
                "message": message,
                "retryable": True,
                "hint": hint,
                "details": {},
                "trace_id": "example-trace",
            }
        ],
        "next_actions": [
            {
                "domain": "util",
                "action": "describe_action",
                "params": {"domain": domain, "action": action},
            }
        ],
        "trace_id": "example-trace",
    }


def _complete_spec(
    domain: str,
    action: str,
    metadata: dict,
    fn: ast.FunctionDef | None = None,
) -> dict[str, Any]:
    input_schema = metadata.get("input_schema")
    if input_schema is None:
        if fn is None:
            raise ValueError(f"{domain}.{action} has no input_schema")
        input_schema = _input_schema(fn, metadata)

    examples = metadata.get("examples") or [_valid_example(action, input_schema)]
    error_examples = metadata.get("error_examples") or [
        _error_example(domain, action, input_schema)
    ]
    result_kind = metadata["result_kind"]
    output_schema = metadata.get("output_schema")
    if output_schema is None and result_kind == "json":
        output_schema = json.loads(json.dumps(_DEFAULT_OUTPUT_SCHEMA))

    raw_spec = {
        "domain": domain,
        "action": action,
        "title": metadata["title"],
        "description": metadata["description"],
        "result_kind": result_kind,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "effect": metadata["effect"],
        "risk": metadata["risk"],
        "idempotent": metadata["idempotent"],
        "supports_preview": metadata["supports_preview"],
        "supports_undo": metadata["supports_undo"],
        "requires_confirmation": metadata["requires_confirmation"],
        "ue_versions": metadata["ue_versions"],
        "required_plugins": metadata.get("required_plugins", []),
        "examples": examples,
        "error_examples": error_examples,
    }

    Draft202012Validator.check_schema(input_schema)
    if output_schema is not None:
        Draft202012Validator.check_schema(output_schema)
    validator = Draft202012Validator(input_schema)
    for example in examples:
        if example.get("action") != action:
            raise ValueError(f"{domain}.{action} example names another action")
        validator.validate(example.get("params", {}))
    for example in error_examples:
        ToolResult.model_validate(example)
    return ActionSpec.model_validate(raw_spec).model_dump(mode="json")


def _special_specs() -> dict:
    tree = ast.parse(
        SPECIAL_SPECS_FILE.read_text(encoding="utf-8"), filename=str(SPECIAL_SPECS_FILE)
    )
    return _literal_assignment(tree, "SPECIAL_ACTION_SPECS")


def build_registry() -> dict:
    """Build complete, validated Action Registry v2 records."""
    special = _special_specs()
    registry: dict[str, dict[str, dict]] = {}
    for domain in DOMAINS:
        nodes, metadata = _load_action_module(domain)
        actions = {
            action: _complete_spec(domain, action, metadata[action], node)
            for action, node in nodes.items()
        }
        for action, spec in special.get(domain, {}).items():
            if action in actions:
                raise ValueError(f"Duplicate registry action {domain}.{action}")
            actions[action] = _complete_spec(domain, action, spec)
        registry[domain] = dict(sorted(actions.items()))
    return registry


def render(catalog: dict) -> str:
    lines = [
        "# Copyright (c) 2025 GenOrca. All Rights Reserved.",
        "#",
        "# AUTO-GENERATED by generate_catalog.py — do not edit by hand.",
        "# Regenerate: python generate_catalog.py",
        "",
        "CATALOG = {",
    ]
    for domain, actions in catalog.items():
        lines.append(f"    {domain!r}: {{")
        for action, info in actions.items():
            lines.append(f"        {action!r}: {{")
            lines.append(f"            {'params'!r}: {info['params']!r},")
            lines.append(f"            {'doc'!r}: {info['doc']!r},")
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def render_registry(registry: dict) -> str:
    return "\n".join(
        [
            "# Copyright (c) 2025 GenOrca. All Rights Reserved.",
            "#",
            "# AUTO-GENERATED by generate_catalog.py — do not edit by hand.",
            "# Regenerate: python generate_catalog.py",
            "",
            f"ACTION_SPECS = {pformat(registry, width=100, sort_dicts=True)}",
            "",
        ]
    )


def _check_file(path: Path, rendered: str) -> bool:
    return path.exists() and path.read_text(encoding="utf-8").strip() == rendered.strip()


def main() -> None:
    catalog = build()
    registry = build_registry()
    rendered_catalog = render(catalog)
    rendered_registry = render_registry(registry)
    total = sum(len(actions) for actions in catalog.values())
    registry_total = sum(len(actions) for actions in registry.values())
    if registry_total != total:
        raise SystemExit(
            f"FAIL: catalog has {total} actions but registry has {registry_total}"
        )

    if "--check" in sys.argv:
        stale = []
        if not _check_file(CATALOG_OUTPUT, rendered_catalog):
            stale.append("_catalog.py")
        if not _check_file(REGISTRY_OUTPUT, rendered_registry):
            stale.append("_registry.py")
        if stale:
            print(f"FAIL: {', '.join(stale)} stale. Run: python generate_catalog.py")
            raise SystemExit(1)
        print(f"OK: catalog and registry in sync ({total} actions across {len(catalog)} domains).")
        return

    CATALOG_OUTPUT.write_text(rendered_catalog, encoding="utf-8")
    REGISTRY_OUTPUT.write_text(rendered_registry, encoding="utf-8")
    print(
        f"Wrote {CATALOG_OUTPUT.name} and {REGISTRY_OUTPUT.name} "
        f"({total} actions across {len(catalog)} domains)."
    )


if __name__ == "__main__":
    main()
