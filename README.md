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
  <a href="#installation">Installation</a> &middot;
  <a href="#usage">Usage</a> &middot;
  <a href="#tools-reference">Tools Reference</a> &middot;
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

Unreal MCP bridges AI assistants (Claude, Cursor, VS Code Copilot) and the Unreal Editor through the [Model Context Protocol](https://modelcontextprotocol.io/). Spawn actors, edit materials, build Blueprint graphs, construct Behavior Trees, design UMG Widget Blueprints — all from natural language.

<p align="center">
  <a href="https://youtu.be/V7KyjzFlBLk?si=QaqVqmt6YL59DHg4">
    <img src="https://img.youtube.com/vi/V7KyjzFlBLk/hqdefault.jpg" width="600" alt="Watch the demo">
  </a>
  <br>
  <sub>Click to watch the demo on YouTube</sub>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025111.png" width="400">
  <img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025115.png" width="400">
  <img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025120.png" width="400">
</p>

## Features

| Category | Capabilities | Tools |
|---|---|:---:|
| **Actor Manipulation** | Spawn, duplicate, transform, delete actors. Surface raycasting. View frustum queries. Property get/set. | 17 |
| **Asset Management** | Search and filter assets by name/type. Static mesh detail retrieval. | 2 |
| **Material System** | Create and connect expressions. Material instance parameters (scalar, vector, texture, static switch). Recompilation. | 11 |
| **Blueprint Graph** | Read graph structure, nodes, pins, and variables. Add, connect, remove nodes. Build and compile entire graphs. | 10 |
| **Behavior Tree** | Create and read Behavior Trees. Manage Blackboard assets and keys. Build complete BT hierarchies. | 12 |
| **UMG Widget Blueprint** | Create Widget Blueprints. Add/remove widgets (15 types). Set properties, canvas slot layout. Compile. | 6 |
| **Editor Tools** | Selection management. Material/mesh replacement on actors. Blueprint-based replacement. | 6 |
| **Game Settings** | Game mode configuration. Input action and mapping setup. | 3 |
| **Utilities** | Output log retrieval for debugging. | 1 |

> **68 tools** across 9 categories — all accessible through natural language.

## Installation

### Prerequisites

- **Unreal Engine** 5.6+
- **Python** 3.11+
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- An **MCP client** (Claude Desktop, VS Code, Cursor, etc.)

### Step 1 — Install the Plugin

**Option A: Clone from GitHub (Recommended)**

```bash
cd YourProject/Plugins
git clone https://github.com/GenOrca/unreal-mcp.git
```

```
YourProject/
└── Plugins/
    └── unreal-mcp/
        ├── Source/
        ├── Content/
        ├── mcp-server/        ← MCP server included
        └── UnrealMCPython.uplugin
```

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
3. Verify — you should see Unreal-MCPython tools listed in your client

## Usage

Just describe what you want in natural language:

```
"Place 10 trees randomly on the terrain surface"
"Find all static meshes with 'rock' in the name"
"Set the base color of MI_Ground to dark brown"
"Explain what the selected Blueprint nodes do"
"Add a PrintString node to BP_Player's EventGraph and connect it to BeginPlay"
"Build a Blueprint graph with event tick, delta time, and a timeline node"
"Create a Behavior Tree with a Selector root, two Sequences, and MoveTo/Wait tasks"
"Create a HUD widget with a health bar and score label, set the text to 'Score: 0'"
"Add a CanvasPanel root to WBP_MainMenu and place a TextBlock at position (200, 100) with font size 48"
```

## Tools Reference

<details>
<summary><strong>Actor Manipulation</strong> (17 tools)</summary>

| Tool | Description |
|---|---|
| `spawn_from_object` | Spawn actor from an existing asset |
| `spawn_from_class` | Spawn actor from a class |
| `spawn_on_surface_raycast` | Spawn actor on surface via raycast |
| `duplicate_selected` | Duplicate selected actors |
| `delete_by_label` | Delete actors by label |
| `select_all` | Select all actors |
| `invert_selection` | Invert current selection |
| `list_all_with_locations` | List all actors with locations |
| `get_all_details` | Get detailed info for actors |
| `set_transform` | Set full transform (location, rotation, scale) |
| `set_location` | Set actor location |
| `set_rotation` | Set actor rotation |
| `set_scale` | Set actor scale |
| `get_property` | Get actor property value |
| `set_property` | Set actor property value |
| `line_trace` | Perform line trace raycast |
| `get_in_view_frustum` | Get actors in camera view frustum |

</details>

<details>
<summary><strong>Asset Management</strong> (2 tools)</summary>

| Tool | Description |
|---|---|
| `find_by_query` | Search and filter assets by name/type |
| `get_static_mesh_details` | Get static mesh details |

</details>

<details>
<summary><strong>Material System</strong> (11 tools)</summary>

| Tool | Description |
|---|---|
| `create_expression` | Create material expression node |
| `connect_expressions` | Connect two material expressions |
| `recompile` | Recompile material |
| `get_mi_scalar_param` | Get scalar parameter from material instance |
| `set_mi_scalar_param` | Set scalar parameter on material instance |
| `get_mi_vector_param` | Get vector parameter from material instance |
| `set_mi_vector_param` | Set vector parameter on material instance |
| `get_mi_texture_param` | Get texture parameter from material instance |
| `set_mi_texture_param` | Set texture parameter on material instance |
| `get_mi_static_switch` | Get static switch from material instance |
| `set_mi_static_switch` | Set static switch on material instance |

</details>

<details>
<summary><strong>Blueprint Graph</strong> (10 tools)</summary>

| Tool | Description |
|---|---|
| `get_selected_bp_nodes` | Get selected Blueprint nodes |
| `get_selected_bp_node_infos` | Get detailed info for selected nodes |
| `get_blueprint_graph_info` | Read full graph structure |
| `list_callable_functions` | List callable functions in Blueprint context |
| `list_blueprint_variables` | List Blueprint variables |
| `add_blueprint_node` | Add a node to a graph |
| `connect_blueprint_pins` | Connect two pins |
| `remove_blueprint_node` | Remove a node |
| `build_blueprint_graph` | Build entire graph from JSON |
| `compile_blueprint` | Compile Blueprint |

</details>

<details>
<summary><strong>Behavior Tree</strong> (12 tools)</summary>

| Tool | Description |
|---|---|
| `list_behavior_trees` | List all Behavior Tree assets |
| `get_behavior_tree_structure` | Read BT structure |
| `get_blackboard_data` | Get Blackboard data |
| `get_bt_node_details` | Get BT node details |
| `get_selected_bt_nodes` | Get selected BT nodes |
| `create_behavior_tree` | Create new Behavior Tree |
| `create_blackboard` | Create new Blackboard |
| `add_blackboard_key` | Add key to Blackboard |
| `remove_blackboard_key` | Remove key from Blackboard |
| `set_blackboard_to_behavior_tree` | Assign Blackboard to BT |
| `build_behavior_tree` | Build complete BT hierarchy |
| `list_bt_node_classes` | List available BT node classes |

</details>

<details>
<summary><strong>UMG Widget Blueprint</strong> (6 tools)</summary>

| Tool | Description |
|---|---|
| `create_widget_blueprint` | Create a new Widget Blueprint asset |
| `get_widget_blueprint_info` | Get widget tree hierarchy and widget list |
| `add_widget` | Add a widget to the tree (15 supported types) |
| `set_widget_properties` | Set text, font size, color, visibility, canvas slot layout |
| `remove_widget` | Remove a widget from the tree |
| `compile_widget_blueprint` | Compile and validate the Widget Blueprint |

**Supported widget types:** CanvasPanel, TextBlock, Button, Image, HorizontalBox, VerticalBox, Border, Overlay, ScrollBox, SizeBox, CheckBox, EditableText, EditableTextBox, ProgressBar, Slider

**Canvas slot properties** (when parent is CanvasPanel): `slot_position`, `slot_size`, `slot_alignment`, `slot_z_order`

</details>

<details>
<summary><strong>Editor Tools</strong> (6 tools)</summary>

| Tool | Description |
|---|---|
| `get_selected_assets` | Get currently selected assets |
| `replace_mtl_on_selected` | Replace material on selected actors |
| `replace_mtl_on_specified` | Replace material on specified actors |
| `replace_mesh_on_selected` | Replace mesh on selected actors |
| `replace_mesh_on_specified` | Replace mesh on specified actors |
| `replace_selected_with_bp` | Replace selected actors with Blueprint |

</details>

<details>
<summary><strong>Game Settings</strong> (3 tools) &amp; <strong>Utilities</strong> (1 tool)</summary>

| Tool | Description |
|---|---|
| `set_game_mode` | Set game mode |
| `add_input_action` | Add input action |
| `add_input_mapping` | Add input mapping |
| `get_output_log` | Retrieve Unreal output log |

</details>

## How It Works

```
┌─────────────────┐         MCP         ┌─────────────────┐   TCP/JSON   ┌──────────────────┐
│   AI Assistant   │  ◄──────────────►  │   MCP Server    │  ◄────────►  │  Unreal Engine   │
│ (Claude, Cursor) │                     │   (Python/uv)   │              │  (Plugin + Python)│
└─────────────────┘                     └─────────────────┘              └──────────────────┘
```

The MCP server translates AI tool calls into Python commands executed inside Unreal Engine's embedded Python interpreter.

## Troubleshooting

| Problem | Solution |
|---|---|
| MCP server not starting | Verify Python 3.11+ and `uv` are installed |
| Path errors | Check the absolute path in your client config |
| Plugin not visible | Restart UE and confirm both plugins are enabled |
| Tools not showing | Restart your MCP client and verify the config |

## References

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Unreal Engine Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/)

## Contributing

Issues, feature requests, and pull requests are welcome on [GitHub](https://github.com/GenOrca/unreal-mcp).

## License

[Apache-2.0](LICENSE.txt)
