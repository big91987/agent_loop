from __future__ import annotations

from typing import Dict, List

from .mcp_transport_clients import HTTPMCPClient, MCPClient, StdioMCPClient
from .mcp_types import MCPError, MCPServerConfig


def _to_v41_config(cfg: object) -> MCPServerConfig:
    name = str(getattr(cfg, "name", "")).strip()
    explicit_type = str(getattr(cfg, "type", "")).strip().lower()
    command = str(getattr(cfg, "command", "")).strip()
    args_raw = getattr(cfg, "args", [])
    args = [str(part) for part in args_raw] if isinstance(args_raw, list) else []
    env_raw = getattr(cfg, "env", {})
    env: Dict[str, str] = {}
    if isinstance(env_raw, dict):
        env = {str(k): str(v) for k, v in env_raw.items()}
    headers_raw = getattr(cfg, "headers", {})
    headers: Dict[str, str] = {}
    if isinstance(headers_raw, dict):
        headers = {str(k): str(v) for k, v in headers_raw.items()}
    url_raw = getattr(cfg, "url", None)
    url = str(url_raw).strip() if url_raw is not None else None
    if url == "":
        url = None
    message_url_raw = getattr(cfg, "message_url", None)
    message_url = str(message_url_raw).strip() if message_url_raw is not None else None
    if message_url == "":
        message_url = None
    timeout_seconds = int(getattr(cfg, "timeout_seconds", 30))
    stdio_msg_format = str(getattr(cfg, "stdio_msg_format", "auto")).strip().lower() or "auto"

    # v4.1 only: infer transport type when config omits explicit type.
    if explicit_type in {"stdio", "sse", "streamable_http"}:
        mcp_type = explicit_type
    elif command:
        mcp_type = "stdio"
    elif message_url:
        mcp_type = "sse"
    elif url:
        mcp_type = "sse" if "/sse" in url.lower() else "streamable_http"
    else:
        mcp_type = "stdio"

    return MCPServerConfig(
        name=name,
        type=mcp_type,
        command=command,
        args=args,
        env=env,
        url=url,
        message_url=message_url,
        headers=headers,
        stdio_msg_format=stdio_msg_format,
        timeout_seconds=timeout_seconds,
    )


class MCPManager:
    """
    v4.1 dedicated MCP manager (single-file teaching version):
    - resources/list + resources/read
    - stdio / sse / streamable_http transports
    - v4.1-only transport type inference
    """

    def __init__(self, server_configs: List[object]) -> None:
        normalized = [_to_v41_config(cfg) for cfg in server_configs]
        self.clients: Dict[str, MCPClient] = {}
        for cfg in normalized:
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


__all__ = [
    "MCPServerConfig",
    "MCPError",
    "MCPManager",
    "_to_v41_config",
]
