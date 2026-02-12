from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Dict, List, Protocol
from urllib.request import Request, urlopen

from .mcp_types import MCPError, MCPServerConfig


class MCPClient(Protocol):
    async def list_tools(self) -> List[Dict[str, object]]: ...

    async def call_tool(self, name: str, arguments: Dict[str, object]) -> str: ...

    async def list_resources(self) -> List[Dict[str, object]]: ...

    async def read_resource(self, uri: str) -> str: ...

    async def aclose(self) -> None: ...


def _flatten_text_result(result: Dict[str, object]) -> str:
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


class StdioMCPClient:
    """
    Minimal MCP client over stdio using JSON-RPC style framing.
    This is intentionally lightweight for teaching usage.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._proc: asyncio.subprocess.Process | None = None
        self._stdin: asyncio.StreamWriter | None = None
        self._stdout: asyncio.StreamReader | None = None
        self._stderr: asyncio.StreamReader | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: List[str] = []
        self._initialized = False
        self._request_lock = asyncio.Lock()
        self._next_request_id = 1
        self._debug = os.getenv("MCP_V41_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

    def _debug_log(self, message: str) -> None:
        if not self._debug:
            return
        ts = time.strftime("%H:%M:%S")
        print(f"[mcp-v4.1:{self.config.name} {ts}] {message}", file=sys.stderr)

    async def _consume_stderr(self) -> None:
        if self._stderr is None:
            return
        while True:
            chunk = await self._stderr.readline()
            if not chunk:
                return
            text = chunk.decode("utf-8", errors="replace").rstrip("\n")
            if len(self._stderr_tail) >= 50:
                self._stderr_tail.pop(0)
            self._stderr_tail.append(text)
            self._debug_log(f"stderr: {text}")

    def _stderr_hint(self) -> str:
        if not self._stderr_tail:
            return "stderr=empty"
        preview = " | ".join(self._stderr_tail[-5:])
        return f"stderr_tail={preview}"

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

    async def _start_process(self) -> None:
        self._debug_log(
            f"start process: {self.config.command} {' '.join(self.config.args)} timeout={self.config.timeout_seconds}s"
        )
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
        self._proc = proc
        self._stdin = proc.stdin
        self._stdout = proc.stdout
        self._stderr = proc.stderr
        self._initialized = False
        self._stderr_tail = []
        if self._stderr is not None:
            self._stderr_task = asyncio.create_task(self._consume_stderr())

    async def _ensure_connected(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            await self._start_process()
        if self._stdin is None or self._stdout is None:
            raise MCPError(f"{self.config.name}: missing stdio stream handles")
        if self._initialized:
            return
        request_id = self._next_request_id
        self._next_request_id += 1
        init_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "python-agent-suite", "version": "0.1.0"},
            },
        }
        self._debug_log("send initialize")
        self._stdin.write(self._build_frame(init_payload))
        await self._stdin.drain()
        try:
            init_resp = await self._read_frame(self._stdout, self.config.timeout_seconds)
        except TimeoutError as err:
            raise MCPError(
                f"{self.config.name}: initialize timeout after {self.config.timeout_seconds}s ({self._stderr_hint()})"
            ) from err
        if "error" in init_resp:
            raise MCPError(f"{self.config.name}: initialize failed: {init_resp['error']}")
        self._initialized = True
        self._debug_log("initialize ok")

    async def _request(
        self,
        *,
        method: str,
        params: Dict[str, object] | None = None,
        request_id: int | None = None,
    ) -> Dict[str, object]:
        params = params or {}
        async with self._request_lock:
            await self._ensure_connected()
            if self._stdin is None or self._stdout is None:
                raise MCPError(f"{self.config.name}: disconnected stdio streams")
            if request_id is None:
                request_id = self._next_request_id
                self._next_request_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self._debug_log(f"send method={method} id={request_id}")
            self._stdin.write(self._build_frame(payload))
            await self._stdin.drain()
            try:
                result_resp = await self._read_frame(self._stdout, self.config.timeout_seconds)
            except TimeoutError as err:
                raise MCPError(
                    f"{self.config.name}: {method} timeout after {self.config.timeout_seconds}s ({self._stderr_hint()})"
                ) from err
            if "error" in result_resp:
                raise MCPError(f"{self.config.name}: {method} failed: {result_resp['error']}")
            self._debug_log(f"recv method={method} id={request_id} ok")
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
        return _flatten_text_result(result)

    async def list_resources(self) -> List[Dict[str, object]]:
        data = await self._request(method="resources/list", params={})
        result = data.get("result")
        if not isinstance(result, dict):
            return []
        resources = result.get("resources")
        if not isinstance(resources, list):
            return []
        parsed: List[Dict[str, object]] = []
        for resource in resources:
            if isinstance(resource, dict):
                parsed.append(resource)
        return parsed

    async def read_resource(self, uri: str) -> str:
        data = await self._request(
            method="resources/read",
            params={"uri": uri},
            request_id=200,
        )
        result = data.get("result")
        if not isinstance(result, dict):
            return ""
        return _flatten_text_result(result)

    async def aclose(self) -> None:
        async with self._request_lock:
            if self._proc is None:
                return
            self._debug_log("closing stdio process")
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._proc.kill()
            if self._stderr_task is not None:
                self._stderr_task.cancel()
                try:
                    await self._stderr_task
                except asyncio.CancelledError:
                    pass
            self._proc = None
            self._stdin = None
            self._stdout = None
            self._stderr = None
            self._stderr_task = None
            self._initialized = False


class HTTPMCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.rpc_url = self._resolve_rpc_url()
        self._initialized = False
        self._session_id: str | None = None

    def _resolve_rpc_url(self) -> str:
        if self.config.type == "sse":
            if self.config.message_url:
                return self.config.message_url
            if not self.config.url:
                raise MCPError(f"{self.config.name}: missing url for sse transport")
            if self.config.url.endswith("/sse"):
                return f"{self.config.url[:-4]}/messages"
            return f"{self.config.url.rstrip('/')}/messages"
        if not self.config.url:
            raise MCPError(f"{self.config.name}: missing url for {self.config.type} transport")
        return self.config.url

    async def _post_jsonrpc(self, payload: Dict[str, object]) -> Dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            # Streamable HTTP requires advertising support for both JSON and SSE.
            "Accept": "application/json, text/event-stream",
            "Mcp-Protocol-Version": "2024-11-05",
            **self.config.headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = Request(self.rpc_url, data=body, headers=headers, method="POST")

        def _send() -> Dict[str, object]:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:  # noqa: S310
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self._session_id = session_id
                content_type = response.headers.get("Content-Type", "").lower()
                payload_text = response.read().decode("utf-8")

                if "text/event-stream" in content_type:
                    data_blocks: List[str] = []
                    for line in payload_text.splitlines():
                        if line.startswith("data:"):
                            data_blocks.append(line[5:].lstrip())
                    if not data_blocks:
                        raise MCPError(f"{self.config.name}: empty SSE response body")
                    last_block = data_blocks[-1]
                    parsed = json.loads(last_block)
                    if not isinstance(parsed, dict):
                        raise MCPError(f"{self.config.name}: invalid SSE JSON-RPC payload type")
                    return parsed

                data = json.loads(payload_text)
                if not isinstance(data, dict):
                    raise MCPError(f"{self.config.name}: invalid JSON-RPC response type")
                return data

        return await asyncio.to_thread(_send)

    async def _request(
        self,
        *,
        method: str,
        params: Dict[str, object] | None = None,
        request_id: int = 1,
    ) -> Dict[str, object]:
        params = params or {}
        if not self._initialized:
            init_resp = await self._post_jsonrpc(
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
            if "error" in init_resp:
                raise MCPError(f"{self.config.name}: initialize failed: {init_resp['error']}")
            self._initialized = True
        result_resp = await self._post_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": request_id + 1,
                "method": method,
                "params": params,
            },
        )
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
        return [tool for tool in tools if isinstance(tool, dict)]

    async def call_tool(self, name: str, arguments: Dict[str, object]) -> str:
        data = await self._request(
            method="tools/call",
            params={"name": name, "arguments": arguments},
            request_id=100,
        )
        result = data.get("result")
        if not isinstance(result, dict):
            return ""
        return _flatten_text_result(result)

    async def list_resources(self) -> List[Dict[str, object]]:
        data = await self._request(method="resources/list", params={})
        result = data.get("result")
        if not isinstance(result, dict):
            return []
        resources = result.get("resources")
        if not isinstance(resources, list):
            return []
        return [resource for resource in resources if isinstance(resource, dict)]

    async def read_resource(self, uri: str) -> str:
        data = await self._request(
            method="resources/read",
            params={"uri": uri},
            request_id=200,
        )
        result = data.get("result")
        if not isinstance(result, dict):
            return ""
        return _flatten_text_result(result)

    async def aclose(self) -> None:
        return None
