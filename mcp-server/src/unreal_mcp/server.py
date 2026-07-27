# Copyright (c) 2025 GenOrca. All Rights Reserved.

from unreal_mcp.dispatcher import _settings, dispatcher_mcp

# Public name kept stable for main.py and external imports.
main_mcp = dispatcher_mcp
settings = _settings

def run_server():
    """Entry point function for the Unreal MCP Server"""
    main_mcp.run(transport="stdio")

if __name__ == "__main__":
    run_server()
