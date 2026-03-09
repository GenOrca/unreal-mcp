# Unreal-MCPython

MCP (Model Context Protocol) integration for Unreal Engine. Connects AI assistants like Claude directly to the Unreal Editor for asset management, scene manipulation, and workflow automation.

[![YouTube Demo](https://img.youtube.com/vi/V7KyjzFlBLk/hqdefault.jpg)](https://youtu.be/V7KyjzFlBLk?si=QaqVqmt6YL59DHg4)

<p align="center">
<img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025106.png" width="400">
<img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025111.png" width="400">
<img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025115.png" width="400">
<img src="https://raw.githubusercontent.com/GenOrca/Screenshot/refs/heads/main/unreal-mcp/Screenshot%202025-06-02%20025120.png" width="400">
</p>

## Features

**Actor Manipulation** — Spawn, duplicate, transform, delete actors. Surface placement via raycasting. View frustum queries.

**Asset Management** — Search and filter assets by name/type. Static mesh detail retrieval.

**Material System** — Material instance parameters (scalar, vector, texture, static switch). Expression creation and connection. Recompilation.

**Editor Tools** — Selection management. Material/mesh replacement on actors. Blueprint node inspection. Line-trace raycasting. Generic property access.

**Blueprint Graph Read & Write** — Read graph structure, nodes, pin connections, and variables. Add, connect, and remove nodes. Build and compile entire graphs.

**Behavior Tree & Blackboard** — Create, read, and build Behavior Trees. Manage Blackboard assets and keys. Build complete BT hierarchies.

## Installation

### Prerequisites

- Unreal Engine 5.6+
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- An MCP client (Claude Desktop, VS Code, Cursor, etc.)

See the [MCP documentation](https://modelcontextprotocol.io/quickstart/user) for general MCP setup.

### 1. Install the Plugin

**Option 1: Clone from GitHub (Recommended)**

Clone and place in your project's Plugins directory:
```bash
git clone https://github.com/GenOrca/unreal-mcpython.git
```
```
YourProject/
└── Plugins/
    └── unreal-mcpython/
        ├── Source/
        ├── Content/
        ├── mcp-server/        ← MCP server included
        └── UnrealMCPython.uplugin
```

**Option 2: Install from Fab**

> The Fab version may not include the latest updates. For the most up-to-date version, use GitHub.

[Fab: Unreal-MCPython](https://fab.com/s/aed5f75d50b2)

After installing from Fab, you still need the `mcp-server/` folder from this repository.

### 2. Configure Unreal Engine

1. Open your project in Unreal Engine.
2. Edit > Plugins — enable **Unreal-MCPython** and **Python Editor Script Plugin**.
3. Restart the editor.

### 3. Configure your MCP Client

The MCP server is included under `mcp-server/`. Add it to your client config:

```json
{
    "mcpServers": {
        "unreal-mcpython": {
            "command": "uv",
            "args": [
                "--directory",
                "C:\\absolute\\path\\to\\unreal-mcpython\\mcp-server",
                "run",
                "src/unreal_mcp/main.py"
            ]
        }
    }
}
```

Replace with the actual absolute path to the `mcp-server` folder.

Config file locations:
- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **VS Code / Cursor**: `.vscode/mcp.json` in your workspace

### 4. Connect

1. Restart your MCP client.
2. The MCP server starts automatically.
3. Verify the connection — you should see Unreal-MCPython tools available in your client.

## Usage

```
"Place 10 trees randomly on the terrain surface"
"Find all static meshes with 'rock' in the name"
"Set the base color of MI_Ground to dark brown"
"Explain what the selected Blueprint nodes do"
"Add a PrintString node to BP_Player's EventGraph and connect it to BeginPlay"
"Build a Blueprint graph with event tick, delta time, and a timeline node"
"Create a Behavior Tree with a Selector root, two Sequences, and MoveTo/Wait tasks"
"List all available BT decorator classes"
```

## Troubleshooting

- **MCP server not starting**: Verify Python 3.11+ and uv are installed.
- **Path errors**: Check the absolute path in your config file.
- **Plugin not visible**: Restart UE and confirm both plugins are enabled.
- **Tools not showing**: Restart your MCP client and verify the config.

## References

- [Model Context Protocol](https://modelcontextprotocol.io/quickstart/user)
- [Unreal Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/)

## Contributing

Issues, feature requests, and pull requests are welcome.

## License

Apache-2.0. See [LICENSE](LICENSE) for details.
