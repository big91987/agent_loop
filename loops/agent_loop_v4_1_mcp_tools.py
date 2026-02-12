from __future__ import annotations

import json
from typing import Dict, List

from core.types import ToolSpec
from tools.registry import build_tool_registry

from .agent_loop_v4_mcp_tools import V4MCPToolsLoop


class V4_1MCPToolsLoop(V4MCPToolsLoop):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._resource_bridge_tools: List[ToolSpec] = []

    async def _rebuild_tools(self, *, refresh_mcp: bool) -> None:
        await super()._rebuild_tools(refresh_mcp=refresh_mcp)
        self._resource_bridge_tools = []

        if not self.mcp_enabled or not self.mcp_manager:
            return

        if refresh_mcp:
            await self.mcp_manager.refresh_resources()

        bridge_tools: List[ToolSpec] = []
        for server_name in self.mcp_manager.list_server_names():
            if hasattr(self.mcp_manager, "is_resource_supported"):
                if not bool(self.mcp_manager.is_resource_supported(server_name)):  # type: ignore[call-arg]
                    continue
            list_name = f"mcp.{server_name}.resource_list"
            read_name = f"mcp.{server_name}.resource_read"
            resources = await self.mcp_manager.list_resources(server_name)
            described_resources: List[str] = []
            for item in resources:
                uri = str(item.get("uri", "")).strip()
                desc = str(item.get("description", "")).strip()
                if uri and desc:
                    described_resources.append(f"{uri}: {desc}")
            if described_resources:
                preview = "; ".join(described_resources[:3])
                read_description = (
                    f"[MCP Resource] Read one resource by URI from server '{server_name}'. "
                    f"Server-described resources: {preview}"
                )
            else:
                read_description = (
                    f"[MCP Resource] Read one resource by URI from server '{server_name}'."
                )

            async def _list_handler(params: Dict[str, object], *, server: str = server_name) -> str:
                _ = params
                resources = await self.mcp_manager.list_resources(server)
                return json.dumps(resources, ensure_ascii=False)

            async def _read_handler(params: Dict[str, object], *, server: str = server_name) -> str:
                uri = str(params.get("uri", "")).strip()
                if not uri:
                    return "Missing required argument: uri"
                return await self.mcp_manager.read_resource(server, uri)

            bridge_tools.append(
                ToolSpec(
                    name=list_name,
                    description=f"[MCP Resource] List resources exposed by server '{server_name}'.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=_list_handler,
                ),
            )
            bridge_tools.append(
                ToolSpec(
                    name=read_name,
                    description=read_description,
                    parameters={
                        "type": "object",
                        "properties": {
                            "uri": {
                                "type": "string",
                                "description": "MCP resource URI, e.g. simple://about",
                            },
                        },
                        "required": ["uri"],
                        "additionalProperties": False,
                    },
                    handler=_read_handler,
                ),
            )

        self._resource_bridge_tools = bridge_tools
        self._mcp_tools = [*self._mcp_tools, *self._resource_bridge_tools]
        self.tools = [*self._base_tools, *self._mcp_tools]
        self._tool_registry = build_tool_registry(self.tools)
