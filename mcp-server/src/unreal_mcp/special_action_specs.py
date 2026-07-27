"""Literal registry metadata for actions implemented by the MCP dispatcher."""

SPECIAL_ACTION_SPECS = {
    "util": {
        "execute_python": {
            "title": "Execute Unreal Python",
            "description": "Execute arbitrary Python in the Unreal editor.",
            "effect": "destructive",
            "risk": "high",
            "result_kind": "json",
            "idempotent": False,
            "supports_preview": False,
            "supports_undo": False,
            "requires_confirmation": True,
            "ue_versions": ["5.6", "5.7", "5.8"],
            "required_plugins": ["PythonScriptPlugin"],
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string", "minLength": 1}},
                "required": ["code"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"success": {"type": "boolean"}},
                "required": ["success"],
                "additionalProperties": True,
            },
        },
        "livecoding_compile": {
            "title": "Compile C++ with Live Coding",
            "description": "Run one Live Coding compilation and return diagnostics.",
            "effect": "write",
            "risk": "high",
            "result_kind": "json",
            "idempotent": False,
            "supports_preview": False,
            "supports_undo": False,
            "requires_confirmation": True,
            "ue_versions": ["5.6", "5.7", "5.8"],
            "required_plugins": [],
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"success": {"type": "boolean"}},
                "required": ["success"],
                "additionalProperties": True,
            },
        },
    }
}
