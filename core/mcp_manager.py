from __future__ import annotations

from typing import Dict, List

from .mcp_transport_clients import HTTPMCPClient, MCPClient, StdioMCPClient
from .mcp_types import MCPError, MCPServerConfig


class MCPManager:
    def __init__(self, server_configs: List[MCPServerConfig]) -> None:
        self.clients: Dict[str, MCPClient] = {}
        for cfg in server_configs:
            if cfg.type == "stdio":
                self.clients[cfg.name] = StdioMCPClient(cfg)
            elif cfg.type in {"sse", "streamable_http"}:
                self.clients[cfg.name] = HTTPMCPClient(cfg)
            else:
                raise MCPError(f"Unsupported MCP transport type: {cfg.type}")
        self._tool_index: Dict[str, tuple[str, str, Dict[str, object], str]] = {}
        self._resource_cache: Dict[str, List[Dict[str, object]]] = {}
        self._resource_supported: Dict[str, bool] = {name: True for name in self.clients}

    @staticmethod
    def _is_method_not_found_error(err: Exception, method_name: str) -> bool:
        text = str(err)
        return "Method not found" in text and method_name in text

    async def refresh_tools(self) -> Dict[str, Dict[str, object]]:
        self._tool_index.clear()
        exposed: Dict[str, Dict[str, object]] = {}
        for server_name, client in self.clients.items():
            tools = await client.list_tools()
            for tool in tools:
                base_name = str(tool.get("name", "")).strip()
                if not base_name:
                    continue
                external_name = f"mcp.{server_name}.{base_name}"
                description = str(tool.get("description", f"MCP tool from {server_name}"))
                parameters = tool.get("inputSchema")
                if not isinstance(parameters, dict):
                    parameters = {"type": "object", "properties": {}, "additionalProperties": True}
                exposed[external_name] = {
                    "description": description,
                    "parameters": parameters,
                }
                self._tool_index[external_name] = (server_name, base_name, parameters, description)
        return exposed

    async def call(self, external_name: str, arguments: Dict[str, object]) -> str:
        if external_name not in self._tool_index:
            raise MCPError(f"Unknown MCP tool: {external_name}")
        server_name, base_name, _, _ = self._tool_index[external_name]
        client = self.clients[server_name]
        return await client.call_tool(base_name, arguments)

    async def refresh_resources(self) -> Dict[str, List[Dict[str, object]]]:
        self._resource_cache.clear()
        for server_name, client in self.clients.items():
            try:
                self._resource_cache[server_name] = await client.list_resources()
                self._resource_supported[server_name] = True
            except MCPError as err:
                if self._is_method_not_found_error(err, "resources/list"):
                    self._resource_cache[server_name] = []
                    self._resource_supported[server_name] = False
                    continue
                raise
        return dict(self._resource_cache)

    async def list_resources(self, server_name: str) -> List[Dict[str, object]]:
        if server_name not in self.clients:
            raise MCPError(f"Unknown MCP server: {server_name}")
        if self._resource_supported.get(server_name) is False:
            return []
        if server_name not in self._resource_cache:
            try:
                self._resource_cache[server_name] = await self.clients[server_name].list_resources()
                self._resource_supported[server_name] = True
            except MCPError as err:
                if self._is_method_not_found_error(err, "resources/list"):
                    self._resource_cache[server_name] = []
                    self._resource_supported[server_name] = False
                    return []
                raise
        return list(self._resource_cache.get(server_name, []))

    async def read_resource(self, server_name: str, uri: str) -> str:
        if server_name not in self.clients:
            raise MCPError(f"Unknown MCP server: {server_name}")
        if self._resource_supported.get(server_name) is False:
            raise MCPError(f"{server_name}: resources/read is not supported by this MCP server")
        return await self.clients[server_name].read_resource(uri)

    def list_external_tool_names(self) -> List[str]:
        return sorted(self._tool_index.keys())

    def get_exposed_tools(self) -> Dict[str, Dict[str, object]]:
        exposed: Dict[str, Dict[str, object]] = {}
        for external_name, (_server_name, _base_name, parameters, description) in self._tool_index.items():
            exposed[external_name] = {
                "description": description,
                "parameters": parameters,
            }
        return exposed

    def list_server_names(self) -> List[str]:
        return sorted(self.clients.keys())

    def is_resource_supported(self, server_name: str) -> bool:
        return bool(self._resource_supported.get(server_name, True))

    async def aclose(self) -> None:
        for client in self.clients.values():
            await client.aclose()
