import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from services.mcp.tool_bridge import mcp_tool_to_crystal_schema

logger = logging.getLogger(__name__)

class MCPServerInstance:
    """Wraps an active MCP client session."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.session = None
        self.tools: List[Dict[str, Any]] = []
        self._exit_stack = None

    async def connect(self):
        """Connect to MCP server via stdio transport."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from contextlib import AsyncExitStack

        command = self.config.get("command")
        args = self.config.get("args", [])
        env = {**os.environ, **self.config.get("env", {})}

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        self._exit_stack = AsyncExitStack()
        try:
            stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            self.session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await self.session.initialize()

            # Discover tools
            response = await self.session.list_tools()
            self.tools = [
                mcp_tool_to_crystal_schema(self.name, t)
                for t in response.tools
            ]
            logger.info(f"[MCP] Connected server '{self.name}', discovered {len(self.tools)} tools")
        except Exception as e:
            logger.error(f"[MCP] Failed to connect to server '{self.name}': {e}")
            if self._exit_stack:
                await self._exit_stack.aclose()
            self.session = None
            self.tools = []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.session:
            raise RuntimeError(f"MCP server '{self.name}' is not connected")
        result = await self.session.call_tool(tool_name, arguments)
        return result

    async def close(self):
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self.session = None


class MCPClientManager:
    """
    Manages connections to multiple Model Context Protocol (MCP) servers
    and bridges their tools dynamically into Crystal's tool executor.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "crystal_mcp.json"
        self.servers: Dict[str, MCPServerInstance] = {}

    def load_config(self, base_dir: Optional[str] = None) -> Dict[str, Any]:
        candidates = [
            Path(self.config_path),
            Path(base_dir or "") / "crystal_mcp.json",
            Path.home() / ".crystal" / "mcp.json",
        ]
        for p in candidates:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"[MCP] Failed to parse {p}: {e}")
        return {"mcpServers": {}}

    async def initialize(self, base_dir: Optional[str] = None):
        """Load configuration and initialize servers."""
        cfg = self.load_config(base_dir)
        server_defs = cfg.get("mcpServers", {})

        for name, s_cfg in server_defs.items():
            instance = MCPServerInstance(name, s_cfg)
            self.servers[name] = instance
            asyncio.create_task(instance.connect())

    def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        for instance in self.servers.values():
            all_tools.extend(instance.tools)
        return all_tools

    async def execute_tool(self, namespaced_tool_name: str, arguments: Dict[str, Any]) -> Any:
        # Expected format: mcp__{server}__{tool}
        parts = namespaced_tool_name.split("__")
        if len(parts) < 3 or parts[0] != "mcp":
            raise ValueError(f"Invalid MCP tool name: {namespaced_tool_name}")

        server_name = parts[1]
        raw_tool_name = "__".join(parts[2:])

        instance = self.servers.get(server_name)
        if not instance:
            raise ValueError(f"MCP server '{server_name}' not registered")

        return await instance.call_tool(raw_tool_name, arguments)

    async def close_all(self):
        for instance in self.servers.values():
            await instance.close()
        self.servers.clear()
