"""Capture the FastMCP 2 namespace-tool contract before migrating to v3."""

import asyncio
import json
from pathlib import Path

from unreal_mcp.dispatcher import dispatcher_mcp


async def main() -> None:
    output = Path(__file__).parent / "golden" / "namespace_tools_v2.json"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")

    if hasattr(dispatcher_mcp, "list_tools"):
        tools = await dispatcher_mcp.list_tools()
    else:
        tools = list((await dispatcher_mcp.get_tools()).values())
    records = [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.parameters,
        }
        for tool in sorted(tools, key=lambda item: item.name)
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
