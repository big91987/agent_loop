from __future__ import annotations

import inspect
import json
from typing import Callable, Dict, List, Set

from core.mcp_client_v4_1 import MCPManager
from core.types import ToolSpec
from tools.registry import build_tool_registry, tool_specs_for_names

from .base import BaseAgentLoop


class V4_1MCPToolsLoop(BaseAgentLoop):
    def __init__(
        self,
        *,
        max_tool_rounds: int = 8,
        default_tool_cwd: str | None = None,
        verbose: bool = True,
        trace_callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        model_delta_callback: Callable[[str], None] | None = None,
        mcp_manager: MCPManager | None = None,
        mcp_enabled: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_names: Set[str] = {"read", "write", "edit", "grep", "find", "ls"}
        self._base_tools: List[ToolSpec] = tool_specs_for_names(self.tool_names)
        self.tools: List[ToolSpec] = list(self._base_tools)
        self.max_tool_rounds = max_tool_rounds
        self.default_tool_cwd = default_tool_cwd
        self.verbose = verbose
        self.trace_callback = trace_callback
        self.status_callback = status_callback
        self.model_delta_callback = model_delta_callback
        self._tool_registry: Dict[str, ToolSpec] = build_tool_registry(self.tools)

        self.mcp_manager = mcp_manager
        self.mcp_enabled = mcp_enabled and mcp_manager is not None
        self._mcp_tools: List[ToolSpec] = []
        self._resource_bridge_tools: List[ToolSpec] = []

    @staticmethod
    def _summarize_text(text: str, *, limit: int = 120) -> str:
        one_line = " ".join(text.split())
        if len(one_line) <= limit:
            return one_line
        return f"{one_line[:limit]}..."

    def _emit_trace(self, line: str) -> None:
        if self.verbose:
            print(line)
        if self.trace_callback is not None:
            self.trace_callback(line)

    def _emit_status(self, status: str) -> None:
        if self.status_callback is not None:
            self.status_callback(status)

    def _print_tool_call(self, name: str, args: Dict[str, object]) -> None:
        args_text = json.dumps(args, ensure_ascii=False, sort_keys=True)
        self._emit_trace(f"[TOOL CALL] {name} args={self._summarize_text(args_text, limit=160)}")

    def _print_tool_result(self, name: str, output: str) -> None:
        summary = self._summarize_text(output)
        self._emit_trace(f"[TOOL RESULT] {name} {summary}")

    def _print_mcp_call(self, tool_name: str, params: Dict[str, object]) -> None:
        args = json.dumps(params, ensure_ascii=False, sort_keys=True)
        self._emit_trace(f"[MCP CALL] {tool_name} args={args}")

    async def _rebuild_tools(self, *, refresh_mcp: bool) -> None:
        mcp_tools: List[ToolSpec] = []
        resource_tools: List[ToolSpec] = []
        if self.mcp_enabled and self.mcp_manager:
            if refresh_mcp:
                await self.mcp_manager.refresh_tools()
            exposed = self.mcp_manager.get_exposed_tools()
            for external_name in self.mcp_manager.list_external_tool_names():
                meta = exposed.get(external_name, {})
                parameters = meta.get("parameters")
                if not isinstance(parameters, dict):
                    parameters = {"type": "object", "properties": {}, "additionalProperties": True}
                description = str(meta.get("description", "MCP tool"))

                async def _handler(params: Dict[str, object], ext_name: str = external_name) -> str:
                    self._print_mcp_call(ext_name, params)
                    return await self.mcp_manager.call(ext_name, params)  # type: ignore[arg-type]

                mcp_tools.append(
                    ToolSpec(
                        name=external_name,
                        description=f"[MCP] {description}",
                        parameters=parameters,
                        handler=_handler,
                    ),
                )

            if refresh_mcp:
                await self.mcp_manager.refresh_resources()
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
                    self._print_mcp_call(f"mcp.{server}.resource_list", {})
                    listed = await self.mcp_manager.list_resources(server)
                    return json.dumps(listed, ensure_ascii=False)

                async def _read_handler(params: Dict[str, object], *, server: str = server_name) -> str:
                    uri = str(params.get("uri", "")).strip()
                    if not uri:
                        return "Missing required argument: uri"
                    self._print_mcp_call(f"mcp.{server}.resource_read", {"uri": uri})
                    return await self.mcp_manager.read_resource(server, uri)

                resource_tools.append(
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
                resource_tools.append(
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

        self._mcp_tools = mcp_tools
        self._resource_bridge_tools = resource_tools
        self.tools = [*self._base_tools, *self._mcp_tools, *self._resource_bridge_tools]
        self._tool_registry = build_tool_registry(self.tools)

    async def set_mcp_enabled(self, enabled: bool) -> None:
        self.mcp_enabled = enabled and self.mcp_manager is not None
        await self._rebuild_tools(refresh_mcp=self.mcp_enabled)

    async def refresh_mcp_tools(self) -> None:
        if not self.mcp_enabled:
            return
        await self._rebuild_tools(refresh_mcp=True)

    def list_mcp_tools(self) -> List[str]:
        if not self.mcp_enabled:
            return []
        return sorted(tool.name for tool in [*self._mcp_tools, *self._resource_bridge_tools])

    async def run_turn(self, user_input: str) -> str:
        if self.mcp_enabled and (not self._mcp_tools and not self._resource_bridge_tools):
            await self._rebuild_tools(refresh_mcp=True)

        self.state.messages.append({"role": "user", "content": user_input})
        final_text = ""
        hit_round_limit = True
        self._emit_status("模型回复中")

        for round_index in range(self.max_tool_rounds):
            if self.verbose:
                print(f"\n[ROUND {round_index + 1}]")
                print("[MODEL]")
            streamed = False

            def _on_text_delta(delta: str) -> None:
                nonlocal streamed
                streamed = True
                if self.verbose:
                    print(delta, end="", flush=True)
                if self.model_delta_callback is not None:
                    self.model_delta_callback(delta)

            response = await self._call_llm(tools=self.tools, on_text_delta=_on_text_delta)
            if self.verbose:
                if streamed:
                    print()
                elif response.text.strip():
                    print(response.text.strip())

            assistant_message = {"role": "assistant", "content": response.text}
            if response.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=True),
                        },
                    }
                    for call in response.tool_calls
                ]
            self.state.messages.append(assistant_message)

            if not response.tool_calls:
                final_text = response.text
                hit_round_limit = False
                break

            for call in response.tool_calls:
                self._emit_status(f"工具调用中: {call.name}")
                tool = self._tool_registry.get(call.name)
                if not tool:
                    tool_output = f"Tool not found: {call.name}"
                    self._print_tool_call(call.name, call.arguments)
                else:
                    call_args = dict(call.arguments)
                    if call.name in self.tool_names and "cwd" not in call_args and self.default_tool_cwd:
                        call_args["cwd"] = self.default_tool_cwd
                    self._print_tool_call(call.name, call_args)
                    try:
                        maybe_output = tool.handler(call_args)
                        if inspect.isawaitable(maybe_output):
                            tool_output = await maybe_output
                        else:
                            tool_output = str(maybe_output)
                    except Exception as err:  # noqa: BLE001
                        tool_output = f"Tool execution error: {err}"
                self._print_tool_result(call.name, tool_output)
                self.state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": tool_output,
                    },
                )
                self._emit_status("模型回复中")

        if hit_round_limit and not final_text:
            final_text = (
                f"[loop warning] reached max_tool_rounds={self.max_tool_rounds}; "
                "the model kept issuing tool calls and did not produce a final text answer. "
                "Try asking it to summarize progress or continue from current state."
            )
            self.state.messages.append({"role": "assistant", "content": final_text})

        self._emit_status("等待输入")
        return final_text


class V4_1(V4_1MCPToolsLoop):
    pass
