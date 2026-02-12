from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class MCPServerConfig:
    # Keep extended fields for config compatibility; v4 stdio client only uses command/args/env/timeout.
    name: str
    type: str = "stdio"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str | None = None
    message_url: str | None = None
    headers: Dict[str, str] = field(default_factory=dict)
    stdio_msg_format: str = "auto"
    timeout_seconds: int = 30


class MCPError(RuntimeError):
    pass


class StdioMCPClient:
    """
    v4 teaching client: stdio transport + tools/list + tools/call only.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config

    @staticmethod
    def _build_frame(payload: Dict[str, object]) -> bytes:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        return header + body

    @staticmethod
    async def _read_frame(stream: asyncio.StreamReader, timeout_seconds: int) -> Dict[str, object]:
        header_bytes = await asyncio.wait_for(stream.readuntil(b"\r\n\r\n"), timeout=timeout_seconds)
        header_text = header_bytes.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise MCPError("Missing Content-Length in MCP response")
        body = await asyncio.wait_for(stream.readexactly(length), timeout=timeout_seconds)
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise MCPError("Invalid MCP response payload")
        return data

    async def _request(
        self,
        *,
        method: str,
        params: Dict[str, object] | None = None,
        request_id: int = 1,
    ) -> Dict[str, object]:
        params = params or {}

        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.config.env},
        )

        if proc.stdin is None or proc.stdout is None:
            raise MCPError(f"{self.config.name}: failed to open stdio pipes")

        async def send(payload: Dict[str, object]) -> None:
            proc.stdin.write(self._build_frame(payload))
            await proc.stdin.drain()

        await send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "python-agent-suite", "version": "0.1.0"},
                },
            },
        )
        init_resp = await self._read_frame(proc.stdout, self.config.timeout_seconds)
        if "error" in init_resp:
            raise MCPError(f"{self.config.name}: initialize failed: {init_resp['error']}")

        await send(
            {
                "jsonrpc": "2.0",
                "id": request_id + 1,
                "method": method,
                "params": params,
            },
        )
        result_resp = await self._read_frame(proc.stdout, self.config.timeout_seconds)

        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()

        if "error" in result_resp:
            raise MCPError(f"{self.config.name}: {method} failed: {result_resp['error']}")
        return result_resp

    async def list_tools(self) -> List[Dict[str, object]]:
        data = await self._request(method="tools/list", params={})
        result = data.get("result")
        if not isinstance(result, dict):
            return []
        tools = result.get("tools")
        if not isinstance(tools, list):
            return []
        parsed: List[Dict[str, object]] = []
        for tool in tools:
            if isinstance(tool, dict):
                parsed.append(tool)
        return parsed

    async def call_tool(self, name: str, arguments: Dict[str, object]) -> str:
        data = await self._request(
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments,
            },
            request_id=100,
        )
        result = data.get("result")
        if not isinstance(result, dict):
            return ""
        content = result.get("content")
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
            return "\n".join(chunk for chunk in chunks if chunk)
        if "text" in result:
            return str(result["text"])
        return json.dumps(result, ensure_ascii=False)


class MCPManager:
    def __init__(self, server_configs: List[MCPServerConfig]) -> None:
        # v4 keeps stdio-only behavior by design.
        stdio_configs = [cfg for cfg in server_configs if (cfg.type or "stdio") == "stdio"]
        self.clients: Dict[str, StdioMCPClient] = {
            cfg.name: StdioMCPClient(cfg) for cfg in stdio_configs if cfg.command
        }
        self._tool_index: Dict[str, tuple[str, str, Dict[str, object], str]] = {}

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
