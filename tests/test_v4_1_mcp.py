from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.config import load_config
from core.mcp_client_v4_1 import _to_v41_config
from core.mcp_transport_clients import StdioMCPClient
from core.mcp_types import MCPServerConfig
from core.types import AssistantResponse, ToolCall
from loops.agent_loop_v4_1_mcp_tools import V4_1MCPToolsLoop


class FakeMCPManager:
    def __init__(self) -> None:
        self.read_requests: list[tuple[str, str]] = []
        self._tools = {
            "mcp.simple.calculate": {
                "description": "calc",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
            }
        }

    async def refresh_tools(self) -> dict[str, dict[str, object]]:
        return self._tools

    def get_exposed_tools(self) -> dict[str, dict[str, object]]:
        return self._tools

    def list_external_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    async def call(self, external_name: str, arguments: dict[str, object]) -> str:
        _ = (external_name, arguments)
        return "5"

    async def refresh_resources(self) -> dict[str, list[dict[str, object]]]:
        return {"simple": [{"uri": "simple://about", "name": "about"}]}

    async def list_resources(self, server_name: str) -> list[dict[str, object]]:
        self.read_requests.append((server_name, "__list__"))
        return [
            {
                "uri": "simple://about",
                "name": "about",
                "description": "About this server",
            },
            {
                "uri": "simple://usage",
                "name": "usage",
            },
        ]

    async def read_resource(self, server_name: str, uri: str) -> str:
        self.read_requests.append((server_name, uri))
        return "about-from-resource"

    def list_server_names(self) -> list[str]:
        return ["simple"]


class FakeClientV4_1:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, model_name, messages, tools=None, timeout_seconds=60):  # type: ignore[no-untyped-def]
        _ = (model_name, tools, timeout_seconds)
        self.calls += 1
        if self.calls == 1:
            return AssistantResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        id="resource-read-1",
                        name="mcp.simple.resource_read",
                        arguments={"uri": "simple://about"},
                    )
                ],
            )
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        last = str(tool_msgs[-1]["content"]) if tool_msgs else ""
        return AssistantResponse(text=f"resource says: {last}")


class V4_1MCPTests(unittest.IsolatedAsyncioTestCase):
    def test_load_config_supports_multiple_mcp_transport_types(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-suite-config-v41-") as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "model_name": "gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1",
                        "mcpServers": {
                            "local": {
                                "type": "stdio",
                                "command": "python3",
                                "args": ["./server.py"],
                            },
                            "remote_sse": {
                                "type": "sse",
                                "url": "https://example.com/sse",
                                "headers": {"Authorization": "Bearer token"},
                            },
                            "remote_http": {
                                "type": "streamable_http",
                                "url": "https://example.com/mcp",
                            },
                        },
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            cfg = load_config(str(config_path))
            assert cfg.mcp_servers is not None
            self.assertEqual(len(cfg.mcp_servers), 3)
            self.assertEqual(cfg.mcp_servers[0].type, "stdio")
            self.assertEqual(cfg.mcp_servers[1].type, "sse")
            self.assertEqual(cfg.mcp_servers[1].url, "https://example.com/sse")
            self.assertEqual(cfg.mcp_servers[2].type, "streamable_http")

    def test_v4_1_type_inference_for_mcpservers_object_entries(self) -> None:
        from types import SimpleNamespace

        cfg_stdio = SimpleNamespace(name="pw", type="", command="npx", args=["-y", "@playwright/mcp"], url=None)
        cfg_sse = SimpleNamespace(name="amap-sse", type="", command="", args=[], url="https://mcp.amap.com/sse?key=x")
        cfg_http = SimpleNamespace(name="amap-http", type="", command="", args=[], url="https://mcp.amap.com/mcp?key=x")

        self.assertEqual(_to_v41_config(cfg_stdio).type, "stdio")
        self.assertEqual(_to_v41_config(cfg_sse).type, "sse")
        self.assertEqual(_to_v41_config(cfg_http).type, "streamable_http")

    async def test_v4_1_resource_bridge_tool_roundtrip(self) -> None:
        manager = FakeMCPManager()
        loop = V4_1MCPToolsLoop(
            client=FakeClientV4_1(),
            model_name="test-model",
            timeout_seconds=30,
            mcp_manager=manager,
            mcp_enabled=True,
        )
        text = await loop.run_turn("please read simple resource")
        self.assertIn("about-from-resource", text)
        self.assertIn(("simple", "simple://about"), manager.read_requests)
        self.assertIn("mcp.simple.resource_list", loop.list_mcp_tools())
        self.assertIn("mcp.simple.resource_read", loop.list_mcp_tools())
        read_tool = next(tool for tool in loop.tools if tool.name == "mcp.simple.resource_read")
        self.assertIn("simple://about: About this server", read_tool.description)

    async def test_v4_1_resource_read_description_fallback_when_missing_server_desc(self) -> None:
        manager = FakeMCPManager()

        async def _list_resources_without_desc(server_name: str) -> list[dict[str, object]]:
            _ = server_name
            return [{"uri": "simple://only-uri", "name": "only-uri"}]

        manager.list_resources = _list_resources_without_desc  # type: ignore[method-assign]
        loop = V4_1MCPToolsLoop(
            client=FakeClientV4_1(),
            model_name="test-model",
            timeout_seconds=30,
            mcp_manager=manager,
            mcp_enabled=True,
        )
        await loop.refresh_mcp_tools()
        read_tool = next(tool for tool in loop.tools if tool.name == "mcp.simple.resource_read")
        self.assertEqual(
            read_tool.description,
            "[MCP Resource] Read one resource by URI from server 'simple'.",
        )

    async def test_v4_1_stdio_client_reuses_process_across_requests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcp-stdio-reuse-") as temp_dir:
            server_path = Path(temp_dir) / "server.py"
            server_path.write_text(
                """#!/usr/bin/env python3
import json
import sys

counter = 0

def read_frame():
    content_length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\\r\\n", b"\\n"):
            break
        text = line.decode("ascii", errors="replace").strip()
        if text.lower().startswith("content-length:"):
            content_length = int(text.split(":", 1)[1].strip())
    if content_length is None:
        return None
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))

def write_frame(payload):
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()

while True:
    req = read_frame()
    if req is None:
        break
    method = req.get("method", "")
    req_id = req.get("id")
    if method == "initialize":
        write_frame({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}})
        continue
    if method == "tools/list":
        counter += 1
        write_frame(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": f"counter={counter}",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            }
        )
        continue
    if method == "notifications/initialized":
        continue
    write_frame({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "unknown method"}})
""",
                encoding="utf-8",
            )
            client = StdioMCPClient(
                MCPServerConfig(
                    name="reuse",
                    type="stdio",
                    command="python3",
                    args=[str(server_path)],
                    timeout_seconds=5,
                )
            )
            first = await client.list_tools()
            second = await client.list_tools()
            await client.aclose()
            self.assertEqual(first[0]["description"], "counter=1")
            self.assertEqual(second[0]["description"], "counter=2")


if __name__ == "__main__":
    unittest.main()
