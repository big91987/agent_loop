from __future__ import annotations

from typing import Dict, List

from .mcp_manager import MCPManager as _MCPManagerV41
from .mcp_types import MCPError, MCPServerConfig as MCPServerConfigV41


def _to_v41_config(cfg: object) -> MCPServerConfigV41:
    name = str(getattr(cfg, "name", "")).strip()
    mcp_type = str(getattr(cfg, "type", "stdio")).strip() or "stdio"
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
    return MCPServerConfigV41(
        name=name,
        type=mcp_type,
        command=command,
        args=args,
        env=env,
        url=url,
        message_url=message_url,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )


class MCPManager:
    """
    v4.1 dedicated MCP manager:
    - resources/list + resources/read
    - stdio / sse / streamable_http transports
    """

    def __init__(self, server_configs: List[object]) -> None:
        normalized = [_to_v41_config(cfg) for cfg in server_configs]
        self._impl = _MCPManagerV41(normalized)

    async def refresh_tools(self) -> Dict[str, Dict[str, object]]:
        return await self._impl.refresh_tools()

    async def call(self, external_name: str, arguments: Dict[str, object]) -> str:
        return await self._impl.call(external_name, arguments)

    async def refresh_resources(self) -> Dict[str, List[Dict[str, object]]]:
        return await self._impl.refresh_resources()

    async def list_resources(self, server_name: str) -> List[Dict[str, object]]:
        return await self._impl.list_resources(server_name)

    async def read_resource(self, server_name: str, uri: str) -> str:
        return await self._impl.read_resource(server_name, uri)

    def list_external_tool_names(self) -> List[str]:
        return self._impl.list_external_tool_names()

    def get_exposed_tools(self) -> Dict[str, Dict[str, object]]:
        return self._impl.get_exposed_tools()

    def list_server_names(self) -> List[str]:
        return self._impl.list_server_names()

    def is_resource_supported(self, server_name: str) -> bool:
        return self._impl.is_resource_supported(server_name)

    async def aclose(self) -> None:
        await self._impl.aclose()


__all__ = [
    "MCPServerConfigV41",
    "MCPError",
    "MCPManager",
]
