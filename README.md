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

**253 actions across 21 domains**, plus `execute_python` as an escape hatch — run any BlueprintCallable function or editor subsystem the engine exposes to Python, on the fly.

**Easy to extend.** Adding an action is a Python function plus a catalog regen — no C++ and no editor rebuild on the Python path. When you need something Python doesn't expose (e.g. reference-skeleton bones), an optional C++ helper layer is there too. See [CLAUDE.md](CLAUDE.md) for the step-by-step workflow.

<p align="center">
  <a href="https://youtu.be/V7KyjzFlBLk?si=QaqVqmt6YL59DHg4">
    <img src="https://img.youtube.com/vi/V7KyjzFlBLk/hqdefault.jpg" width="600" alt="Watch the demo">
  </a>
  <br>
  <sub>Click to watch the demo on YouTube</sub>
</p>

## Features

Each row is one **namespace tool**. The action set is large but the tool list stays small, so it never bloats the model's context. **253 actions across 21 domains.**

| Domain | Capabilities | Actions |
|---|---|:---:|
| **actor** | Spawn (class/object/surface raycast), transform get/set, properties, live component properties, hierarchy (attach/detach), folders, tags, bounds, selection, duplication, class queries. | 36 |
| **asset** | Duplicate/rename/delete/save, list, dependencies & referencers, metadata tags, directories, search, FBX import/export, texture import, glTF/glb import. | 21 |
| **material** | Create materials & instances, author expression graphs, connect to material properties, MI parameters (scalar/vector/texture/switch), reparent, auto-layout, introspection. | 20 |
| **blueprint** | Create Blueprints, read/build graphs, add/connect/remove nodes, member variables (+ flags), SCS components, compile, auto-layout. | 19 |
| **util** | Run arbitrary Unreal Python, console commands, CVar get/set, world↔screen projection, viewport camera, PIE control, project info, class/enum reflection, output log, log verbosity, LiveCoding compile. | 19 |
| **animation** | AnimSequence info, notify tracks, sync markers, float curves; SkeletalMesh sockets & bones (C++-backed); skeleton info. | 17 |
| **umg** | Create Widget Blueprints, add/remove widgets, reparent/wrap/replace, properties, slot layout, text style, event binding, compile. | 15 |
| **level_sequence** | Create cinematics, camera with Camera Cut track, spawnable/possessable bindings, transform & skeletal-anim tracks, keyframes, Sequencer open/close. | 13 |
| **behavior_tree** | Create & read Behavior Trees, Blackboard keys, build complete BT hierarchies. | 12 |
| **editor** | Selection, material/mesh replacement, Blueprint-based replacement, actor merge/join, Proxy Geometry baking, asset-editor open/get/close. | 12 |
| **static_mesh** | Mesh info (LODs/tris/verts), LOD generation & reuse, materials, collision (simple/convex/per-LOD). | 12 |
| **gas** | Gameplay Ability System: Ability/Effect Blueprint authoring, effect modifiers, costs & cooldowns, gameplay tags. | 11 |
| **data_table** | Create DataTables, read/write rows (JSON/CSV), columns, row management. | 8 |
| **level** | Create/open levels, list actors, world settings, current-level path, save. | 7 |
| **control_rig** | Create Control Rigs (bones imported from a mesh), hierarchy authoring, RigVM unit nodes, recompile. | 6 |
| **layer** | Create/delete layers, assign actors, list layer contents. | 6 |
| **retarget** | IK Rig & IK Retargeter authoring, chain auto-mapping, batch animation retargeting. | 6 |
| **anim_blueprint** | Create Animation Blueprints (skeleton-bound), AnimGraph sequence player + locomotion state machine authoring (C++-backed). | 4 |
| **game** | Game mode, Enhanced Input actions & mappings. | 3 |
| **texture** | Texture info, sRGB and compression settings. | 3 |
| **vision** | Capture the viewport / any pose / auto-framed actors as MCP Images with on-image actor labels — the assistant sees and identifies the scene. | 3 |

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

Each [release](https://github.com/GenOrca/unreal-mcp/releases) ships two kinds of plugin asset. **Most users want the precompiled one for their exact engine version:**

- ✅ **`UnrealMCPython_<engine>_<version>.zip`** (e.g. `UnrealMCPython_5.8_2.2.0.zip`) — **precompiled** for that exact UE version. No C++ toolchain, no rebuild — just drop it in and launch. **Pick the one matching your engine version.**
- 🛠️ **`UnrealMCPython-v<version>.zip`** — **source only**, for C++ developers (the CI release pipeline runs on Linux and does not compile the C++ module). Unreal tries to *compile* it on first open, which **requires Visual Studio with the "Game development with C++" workload**. Without that toolchain the build fails and the editor closes — so don't use this one unless you intend to compile.

Extract, then copy `Plugins/UnrealMCPython/` into your project's `Plugins/` folder:

```
YourProject/
└── Plugins/
    └── UnrealMCPython/
        ├── Binaries/   (precompiled zip only)
        ├── Source/
        ├── Content/
        └── UnrealMCPython.uplugin
```

Keep the `mcp-server/` folder from the zip in a convenient location — you'll need its path in Step 3.

> [!NOTE]
> Precompiled binaries are engine-version-specific. If there's no `_<your engine>_` zip for your version, either ask for one in an issue or use the source zip and let Unreal compile it on first open (Windows: Visual Studio with the "Game development with C++" workload). Maintainers build the per-version binaries locally with `tools/build-plugin.ps1` (the CI pipeline can't — GitHub-hosted runners have no Unreal Engine).

> [!WARNING]
> **Seeing `'UnrealMCPython' was designed for build 5.7.0 … load anyway?` or a rebuild that fails and closes the editor?** You downloaded the **source** zip (or a binary for a different engine version). Download the **`UnrealMCPython_<your engine>_<version>.zip`** that matches your engine instead — it loads without compiling. (Source builds from releases ≤ 2.2.0 also pin an old engine version; this is fixed on `main`.)

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
3. Verify — you should see the 19 Unreal-MCPython domain tools listed in your client

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

`add_actor_tag` · `attach_actor` · `delete_by_label` · `detach_actor` · `duplicate_actor` · `duplicate_selected` · `get_actor_bounds` · `get_actor_folder` · `get_actor_tags` · `get_actors_of_class` · `get_all_details` · `get_attached_actors` · `get_component_property` · `get_in_view_frustum` · `get_property` · `get_selected_actors` · `get_transform` · `invert_selection` · `line_trace` · `list_actor_components` · `list_all_with_locations` · `remove_actor_tag` · `rename_actor` · `select_actors` · `select_all` · `set_actor_folder` · `set_actor_hidden` · `set_component_property` · `set_location` · `set_property` · `set_rotation` · `set_scale` · `set_transform` · `spawn_from_class` · `spawn_from_object` · `spawn_on_surface_raycast`

</details>

<details>
<summary><strong>asset</strong> (21)</summary>

`asset_exists` · `delete_asset` · `delete_directory` · `duplicate_asset` · `export_fbx` · `find_by_query` · `find_referencers` · `get_asset_info` · `get_dependencies` · `get_gltf_import_status` · `get_metadata_tag` · `get_static_mesh_details` · `import_fbx` · `import_gltf` · `import_texture` · `list_assets` · `make_directory` · `remove_metadata_tag` · `rename_asset` · `save_asset` · `set_metadata_tag`

</details>

<details>
<summary><strong>material</strong> (20)</summary>

`connect_expressions` · `connect_property` · `create_expression` · `create_material` · `create_material_instance` · `delete_expression` · `get_material_info` · `get_mi_scalar_param` · `get_mi_static_switch` · `get_mi_texture_param` · `get_mi_vector_param` · `layout_expressions` · `list_parameters` · `recompile` · `set_expression_property` · `set_instance_parent` · `set_mi_scalar_param` · `set_mi_static_switch` · `set_mi_texture_param` · `set_mi_vector_param`

</details>

<details>
<summary><strong>blueprint</strong> (19)</summary>

`add_blueprint_node` · `add_component_to_blueprint` · `add_variable` · `auto_layout_graph` · `build_blueprint_graph` · `compile_blueprint` · `connect_blueprint_pins` · `create_blueprint` · `get_blueprint_graph_info` · `get_selected_bp_node_infos` · `get_selected_bp_nodes` · `list_blueprint_components` · `list_blueprint_variables` · `list_callable_functions` · `remove_blueprint_node` · `remove_component_from_blueprint` · `set_blueprint_node_position` · `set_component_property` · `set_variable_flags`

</details>

<details>
<summary><strong>util</strong> (19)</summary>

`execute_console_command` · `execute_python` · `get_cvar` · `get_output_log` · `get_project_info` · `get_viewport_camera` · `is_in_pie` · `list_class_properties` · `list_enum_values` · `livecoding_compile` · `print_message` · `save_all_dirty` · `screen_to_world` · `set_cvar` · `set_log_verbosity` · `set_viewport_camera` · `start_pie` · `stop_pie` · `world_to_screen`

</details>

<details>
<summary><strong>animation</strong> (17)</summary>

`add_float_curve` · `add_notify_track` · `add_socket` · `add_sync_marker` · `find_socket` · `get_anim_sequence_info` · `get_skeletal_mesh_info` · `get_skeleton_info` · `list_bones` · `list_curves` · `list_notifies` · `list_notify_tracks` · `list_sockets` · `list_sync_markers` · `remove_curve` · `remove_notify_track` · `remove_socket`

</details>

<details>
<summary><strong>umg</strong> (15)</summary>

`add_widget` · `bind_widget_event` · `compile_widget_blueprint` · `create_widget_blueprint` · `get_widget_blueprint_info` · `get_widget_property` · `list_widget_events` · `remove_widget` · `reparent_widget` · `replace_widget` · `set_slot_layout` · `set_text_style` · `set_widget_properties` · `set_widget_property` · `wrap_widget`

</details>

<details>
<summary><strong>level_sequence</strong> (13)</summary>

`add_anim_track` · `add_camera` · `add_possessable` · `add_spawnable_from_class` · `add_transform_keyframe` · `add_transform_track` · `close_sequencer` · `convert_binding` · `create_level_sequence` · `get_sequence_info` · `open_in_sequencer` · `remove_binding` · `set_playback_range`

</details>

<details>
<summary><strong>behavior_tree</strong> (12)</summary>

`add_blackboard_key` · `build_behavior_tree` · `create_behavior_tree` · `create_blackboard` · `get_behavior_tree_structure` · `get_blackboard_data` · `get_bt_node_details` · `get_selected_bt_nodes` · `list_behavior_trees` · `list_bt_node_classes` · `remove_blackboard_key` · `set_blackboard_to_behavior_tree`

</details>

<details>
<summary><strong>editor</strong> (12)</summary>

`close_asset_editor` · `create_proxy_actor` · `get_open_assets` · `get_selected_assets` · `join_actors` · `merge_actors` · `open_editor_for_asset` · `replace_mesh_on_selected` · `replace_mesh_on_specified` · `replace_mtl_on_selected` · `replace_mtl_on_specified` · `replace_selected_with_bp`

</details>

<details>
<summary><strong>static_mesh</strong> (12)</summary>

`add_simple_collision` · `get_collision_info` · `get_lod_screen_sizes` · `get_static_mesh_info` · `list_static_mesh_materials` · `remove_collisions` · `remove_lods` · `set_convex_collision` · `set_lod_for_collision` · `set_lod_from_static_mesh` · `set_lods` · `set_static_mesh_material`

</details>

<details>
<summary><strong>gas</strong> (11)</summary>

`add_effect_modifier` · `add_gameplay_tag` · `clear_effect_modifiers` · `create_ability_blueprint` · `create_effect_blueprint` · `get_ability_info` · `get_effect_info` · `list_gameplay_tags` · `set_ability_costs` · `set_ability_tags` · `set_effect_duration`

</details>

<details>
<summary><strong>data_table</strong> (8)</summary>

`create_data_table` · `does_row_exist` · `export_to_csv` · `get_column_names` · `get_row_names` · `get_rows_as_json` · `remove_row` · `set_rows_from_json`

</details>

<details>
<summary><strong>level</strong> (7)</summary>

`create_level` · `get_current_level_path` · `list_level_actors` · `load_level` · `save_all_levels` · `save_current_level` · `set_world_settings`

</details>

<details>
<summary><strong>control_rig</strong> (6)</summary>

`add_rig_bone` · `add_rig_null` · `add_unit_node` · `create_control_rig` · `get_control_rig_info` · `recompile_control_rig`

</details>

<details>
<summary><strong>layer</strong> (6)</summary>

`add_actor_to_layer` · `create_layer` · `delete_layer` · `get_actors_in_layer` · `list_layers` · `remove_actor_from_layer`

</details>

<details>
<summary><strong>retarget</strong> (6)</summary>

`add_retarget_chain` · `auto_map_chains` · `batch_retarget` · `create_ik_rig` · `create_retargeter` · `get_ik_rig_info`

</details>

<details>
<summary><strong>anim_blueprint</strong> (4)</summary>

`add_anim_graph_sequence_player` · `build_anim_state_machine` · `create_anim_blueprint` · `get_anim_blueprint_info`

</details>

<details>
<summary><strong>game</strong> (3)</summary>

`add_input_action` · `add_input_mapping` · `set_game_mode`

</details>

<details>
<summary><strong>texture</strong> (3)</summary>

`get_texture_info` · `set_texture_compression` · `set_texture_srgb`

</details>

<details>
<summary><strong>vision</strong> (3)</summary>

`capture_actors` · `capture_from` · `capture_viewport`

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
