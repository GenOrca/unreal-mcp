<p align="center">
  <img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/logo.png" width="600" alt="Unreal MCP Logo">
</p>

<h1 align="center">Unreal MCP</h1>

<p align="center">
  <strong>Connect AI assistants directly to the Unreal Editor via MCP</strong>
</p>

<p align="center">
  <a href="https://github.com/GenOrca/unreal-mcp/releases"><img src="https://img.shields.io/github/v/release/GenOrca/unreal-mcp?style=flat-square&color=blue" alt="Release"></a>
  <a href="LICENSE.txt"><img src="https://img.shields.io/badge/license-Apache--2.0-green?style=flat-square" alt="License"></a>
  <a href="https://www.unrealengine.com/"><img src="https://img.shields.io/badge/Unreal_Engine-5.6+-black?style=flat-square&logo=unrealengine" alt="Unreal Engine 5.6+"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-purple?style=flat-square" alt="MCP Compatible"></a>
  <a href="https://fab.com/s/aed5f75d50b2"><img src="https://img.shields.io/badge/Fab-Marketplace-orange?style=flat-square" alt="Fab"></a>
</p>

<p align="center">
  <a href="#features">Features</a> &middot;
  <a href="#how-tools-work">How Tools Work</a> &middot;
  <a href="#extending">Extending</a> &middot;
  <a href="#installation">Installation</a> &middot;
  <a href="#usage">Usage</a> &middot;
  <a href="#tools-reference">Tools Reference</a> &middot;
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

Unreal MCP connects AI assistants to the Unreal Editor through the [Model Context Protocol](https://modelcontextprotocol.io/). Spawn actors, build Blueprint graphs, construct Behavior Trees, design UMG widgets, edit materials, author cinematics — all from natural language.

**191 actions across 16 domains**, plus `execute_python` as an escape hatch — run any BlueprintCallable function or editor subsystem the engine exposes to Python, on the fly.

**Easy to extend.** Adding an action is a Python function plus a catalog regen — no C++ and no editor rebuild on the Python path. When you need something Python doesn't expose (e.g. reference-skeleton bones), an optional C++ helper layer is there too. See [CLAUDE.md](CLAUDE.md) for the step-by-step workflow.

<p align="center">
  <a href="https://youtu.be/V7KyjzFlBLk?si=QaqVqmt6YL59DHg4">
    <img src="https://img.youtube.com/vi/V7KyjzFlBLk/hqdefault.jpg" width="600" alt="Watch the demo">
  </a>
  <br>
  <sub>Click to watch the demo on YouTube</sub>
</p>

## Features

Each row is one **namespace tool**. The action set is large but the tool list stays small, so it never bloats the model's context.

| Domain | Capabilities | Actions |
|---|---|:---:|
| **actor** | Spawn (class/object/surface raycast), transform get/set, properties, live component properties, hierarchy (attach/detach), folders, tags, layers, bounds, selection, duplication, class queries. | 36 |
| **material** | Create materials & instances, author expression graphs, connect to material properties, MI parameters (scalar/vector/texture/switch), reparent, auto-layout, introspection. | 20 |
| **blueprint** | Create Blueprints, read/build graphs, add/connect/remove nodes, member variables (+ flags), SCS components, compile, auto-layout. | 19 |
| **animation** | AnimSequence info, notify tracks, sync markers, float curves; SkeletalMesh sockets & bones (C++-backed); skeleton info. | 17 |
| **asset** | Duplicate/rename/delete/save, list, dependencies & referencers, metadata tags, directories, search. | 16 |
| **util** | Run arbitrary Unreal Python, console commands & CVars, viewport camera, PIE control, project info, class/enum reflection, output log, LiveCoding compile. | 15 |
| **behavior_tree** | Create & read Behavior Trees, Blackboard keys, build complete BT hierarchies. | 12 |
| **umg** | Create Widget Blueprints, add/remove widgets (15 types), properties, slot layout, text style, compile. | 10 |
| **level_sequence** | Create cinematics, spawnable/possessable bindings, transform tracks & keyframes, playback range. | 8 |
| **data_table** | Create DataTables, read/write rows (JSON/CSV), columns, row management. | 8 |
| **level** | Create/open levels, list actors, world settings, current-level path, save. | 7 |
| **layer** | Create/delete layers, assign actors, list layer contents. | 6 |
| **editor** | Selection, material/mesh replacement, Blueprint-based replacement. | 6 |
| **static_mesh** | Mesh info (LODs/tris/verts), materials, collision (info + simple primitives). | 5 |
| **game** | Game mode, Enhanced Input actions & mappings. | 3 |
| **texture** | Texture info, sRGB and compression settings. | 3 |

## How Tools Work

Each domain is a single MCP tool. You call it with an `action` name and a `params` object:

```jsonc
// tool: "actor"
{ "action": "spawn_from_class",
  "params": { "class_path": "/Script/Engine.PointLight", "location": [0, 0, 200] } }
```

To discover what a domain can do and the exact parameters each action takes, pass `list_actions`:

```jsonc
// tool: "material"
{ "action": "list_actions" }
// → { "actions": { "create_expression": { "params": "...", "doc": "..." }, ... } }
```

Need something not covered by a built-in action? Use `util / execute_python` to run any Unreal Python directly — the full engine API is available with no C++ build.

## Extending

Adding a tool is intentionally low-friction — anyone comfortable with Python can do it:

1. Add a `ue_<name>(...)` function (returning a JSON string) to a domain module in
   `Plugins/UnrealMCPython/Content/Python/UnrealMCPython/<domain>_actions.py`.
2. Run `python generate_catalog.py` — the action is now exposed by its domain tool.
3. (Optional) add an in-editor test in `tests/test_<domain>.py`.

The Python path needs no C++ and no editor rebuild. New domain? Drop in a
`<domain>_actions.py` and list it in the generator. For an API that Python doesn't
expose, an optional C++ helper (`MCPythonHelper`) is available. Full details in
[CLAUDE.md](CLAUDE.md).

## Installation

### Prerequisites

- **Unreal Engine** 5.6+
- **Python** 3.11+
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- An **MCP client** (Claude Desktop, VS Code, Cursor, etc.)

### Step 1 — Install the Plugin

**Option A: Download from GitHub Releases (Recommended)**

Download the latest zip from [Releases](https://github.com/GenOrca/unreal-mcp/releases) and extract it anywhere. Then copy `Plugins/UnrealMCPython/` into your project's `Plugins/` folder:

```
YourProject/
└── Plugins/
    └── UnrealMCPython/
        ├── Source/
        ├── Content/
        └── UnrealMCPython.uplugin
```

Keep the `mcp-server/` folder from the zip in a convenient location — you'll need its path in Step 3.

**Option B: Install from [Fab](https://fab.com/s/aed5f75d50b2)**

> [!NOTE]
> The Fab version may lag behind the latest GitHub release. After installing from Fab, you still need the `mcp-server/` folder from this repository.

### Step 2 — Enable Plugins in Unreal

1. Open your project in Unreal Engine
2. **Edit > Plugins** — enable **Unreal-MCPython** and **Python Editor Script Plugin**
3. Restart the editor

### Step 3 — Configure your MCP Client

Add the server to your MCP client config:

```json
{
  "mcpServers": {
    "unreal-mcpython": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/absolute/path/to/unreal-mcp/mcp-server",
        "run",
        "src/unreal_mcp/main.py"
      ]
    }
  }
}
```

> [!IMPORTANT]
> Replace the path with the actual absolute path to your `mcp-server` folder.

<details>
<summary>Config file locations by client</summary>

| Client | Path |
|---|---|
| **Claude Desktop** (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Claude Desktop** (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **VS Code / Cursor** | `.vscode/mcp.json` in your workspace |

</details>

### Step 4 — Connect

1. Restart your MCP client
2. The MCP server starts automatically
3. Verify — you should see the 16 Unreal-MCPython domain tools listed in your client

## Usage

Just describe what you want in natural language:

```
"Place 10 trees randomly on the terrain surface"
"Find all static meshes with 'rock' in the name"
"Create M_Ground, add a Constant3Vector for base color, and connect it"
"Explain what the selected Blueprint nodes do"
"Create BP_Door from Actor, add a bool 'IsOpen' variable exposed on spawn"
"Build a Behavior Tree with a Selector root and MoveTo/Wait tasks"
"Create a HUD widget with a health bar and a 'Score: 0' label"
"Make a 6-second level sequence with a CineCamera flying from (0,0,200) to (1200,600,500)"
"Tag all PointLights in the level and move them to a 'Lighting' layer"
```

## Tools Reference

Pass any action below to its domain tool. Use `{ "action": "list_actions" }` on a domain to see each action's parameters and docs.

<details>
<summary><strong>actor</strong> (36)</summary>

`spawn_from_class` · `spawn_from_object` · `spawn_on_surface_raycast` · `duplicate_actor` · `duplicate_selected` · `delete_by_label` · `rename_actor` · `set_actor_hidden` · `select_actors` · `select_all` · `invert_selection` · `get_selected_actors` · `list_all_with_locations` · `get_all_details` · `get_actors_of_class` · `get_in_view_frustum` · `get_transform` · `set_transform` · `set_location` · `set_rotation` · `set_scale` · `get_property` · `set_property` · `get_component_property` · `set_component_property` · `list_actor_components` · `attach_actor` · `detach_actor` · `get_attached_actors` · `set_actor_folder` · `get_actor_folder` · `add_actor_tag` · `remove_actor_tag` · `get_actor_tags` · `get_actor_bounds` · `line_trace`

</details>

<details>
<summary><strong>material</strong> (20)</summary>

`create_material` · `create_material_instance` · `set_instance_parent` · `create_expression` · `set_expression_property` · `delete_expression` · `connect_expressions` · `connect_property` · `layout_expressions` · `recompile` · `get_material_info` · `list_parameters` · `get_mi_scalar_param` · `set_mi_scalar_param` · `get_mi_vector_param` · `set_mi_vector_param` · `get_mi_texture_param` · `set_mi_texture_param` · `get_mi_static_switch` · `set_mi_static_switch`

</details>

<details>
<summary><strong>blueprint</strong> (19)</summary>

`create_blueprint` · `get_blueprint_graph_info` · `list_callable_functions` · `list_blueprint_variables` · `add_variable` · `set_variable_flags` · `add_blueprint_node` · `connect_blueprint_pins` · `remove_blueprint_node` · `set_blueprint_node_position` · `build_blueprint_graph` · `auto_layout_graph` · `compile_blueprint` · `get_selected_bp_nodes` · `get_selected_bp_node_infos` · `list_blueprint_components` · `add_component_to_blueprint` · `remove_component_from_blueprint` · `set_component_property`

</details>

<details>
<summary><strong>animation</strong> (17)</summary>

`get_anim_sequence_info` · `list_notify_tracks` · `add_notify_track` · `remove_notify_track` · `list_notifies` · `list_sync_markers` · `add_sync_marker` · `list_curves` · `add_float_curve` · `remove_curve` · `get_skeletal_mesh_info` · `list_sockets` · `find_socket` · `add_socket` · `remove_socket` · `list_bones` · `get_skeleton_info`

</details>

<details>
<summary><strong>asset</strong> (16)</summary>

`find_by_query` · `get_asset_info` · `asset_exists` · `list_assets` · `duplicate_asset` · `rename_asset` · `delete_asset` · `save_asset` · `get_dependencies` · `find_referencers` · `get_metadata_tag` · `set_metadata_tag` · `remove_metadata_tag` · `make_directory` · `delete_directory` · `get_static_mesh_details`

</details>

<details>
<summary><strong>util</strong> (15)</summary>

`execute_python` · `execute_console_command` · `get_cvar` · `get_output_log` · `print_message` · `get_project_info` · `list_class_properties` · `list_enum_values` · `get_viewport_camera` · `set_viewport_camera` · `is_in_pie` · `start_pie` · `stop_pie` · `save_all_dirty` · `livecoding_compile`

</details>

<details>
<summary><strong>behavior_tree</strong> (12)</summary>

`list_behavior_trees` · `create_behavior_tree` · `get_behavior_tree_structure` · `build_behavior_tree` · `list_bt_node_classes` · `get_bt_node_details` · `get_selected_bt_nodes` · `create_blackboard` · `get_blackboard_data` · `add_blackboard_key` · `remove_blackboard_key` · `set_blackboard_to_behavior_tree`

</details>

<details>
<summary><strong>umg</strong> (10)</summary>

`create_widget_blueprint` · `get_widget_blueprint_info` · `add_widget` · `remove_widget` · `set_widget_properties` · `set_widget_property` · `get_widget_property` · `set_slot_layout` · `set_text_style` · `compile_widget_blueprint`

**Widget types:** CanvasPanel, TextBlock, Button, Image, HorizontalBox, VerticalBox, Border, Overlay, ScrollBox, SizeBox, CheckBox, EditableText, EditableTextBox, ProgressBar, Slider

</details>

<details>
<summary><strong>level_sequence</strong> (8)</summary>

`create_level_sequence` · `get_sequence_info` · `set_playback_range` · `add_spawnable_from_class` · `add_possessable` · `remove_binding` · `add_transform_track` · `add_transform_keyframe`

</details>

<details>
<summary><strong>data_table</strong> (8)</summary>

`create_data_table` · `get_row_names` · `get_column_names` · `get_rows_as_json` · `export_to_csv` · `does_row_exist` · `remove_row` · `set_rows_from_json`

</details>

<details>
<summary><strong>level</strong> (7)</summary>

`create_level` · `load_level` · `get_current_level_path` · `save_current_level` · `save_all_levels` · `list_level_actors` · `set_world_settings`

</details>

<details>
<summary><strong>layer</strong> (6)</summary>

`list_layers` · `create_layer` · `delete_layer` · `add_actor_to_layer` · `remove_actor_from_layer` · `get_actors_in_layer`

</details>

<details>
<summary><strong>editor</strong> (6)</summary>

`get_selected_assets` · `replace_mtl_on_selected` · `replace_mtl_on_specified` · `replace_mesh_on_selected` · `replace_mesh_on_specified` · `replace_selected_with_bp`

</details>

<details>
<summary><strong>static_mesh</strong> (5)</summary>

`get_static_mesh_info` · `list_static_mesh_materials` · `set_static_mesh_material` · `get_collision_info` · `add_simple_collision`

</details>

<details>
<summary><strong>game</strong> (3) &amp; <strong>texture</strong> (3)</summary>

**game:** `set_game_mode` · `add_input_action` · `add_input_mapping`

**texture:** `get_texture_info` · `set_texture_srgb` · `set_texture_compression`

</details>

## Troubleshooting

| Problem | Solution |
|---|---|
| MCP server not starting | Verify Python 3.11+ and `uv` are installed |
| Path errors | Check the absolute path in your client config |
| Plugin not visible | Restart UE and confirm both plugins are enabled |
| Tools not showing | Restart your MCP client and verify the config |
| An action errors on params | Call `{ "action": "list_actions" }` on that domain to see exact parameter names |

## Contributing

Issues, feature requests, and pull requests are welcome on [GitHub](https://github.com/GenOrca/unreal-mcp). See [CLAUDE.md](CLAUDE.md) for the architecture and the workflow for adding new actions.

## License

[Apache-2.0](LICENSE.txt)
