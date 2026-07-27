# Copyright (c) 2025 GenOrca. All Rights Reserved.

import os
import sys
import asyncio

sys.path.append(os.path.dirname(__file__))

from unreal_mcp.server import main_mcp, run_server
from fastmcp import Client

async def test_server():
    print("Testing Unreal MCP Server...")
    tools = await main_mcp.list_tools()
    print(f"Available tools: {[tool.name for tool in tools]}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        asyncio.run(test_server())
    else:
        run_server()

if __name__ == "__main__":
    main()
