from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Dict, List

from core.memory_v6_3 import MemoryRuntimeV63, MemoryToolEvent
from core.types import Message, ToolSpec
from tools.registry import build_tool_registry

from .agent_loop_v6_1 import V6_1


class V6_3(V6_1):
    def __init__(
        self,
        *,
        memory_backend: str = "simplemem",
        memory_system_dir: str = "./memory_systems/v6_3_simplemem",
        memory_artifact_dir: str = "./memory/simplemem",
        memory_user_id: str = "default",
        workspace_path: str | None = None,
        memory_api_key: str | None = None,
        memory_api_key_env: str | None = None,
        memory_model_name: str = "",
        memory_base_url: str = "",
        memory_backend_config: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_path = (workspace_path or "").strip() or "."
        self.memory_runtime = MemoryRuntimeV63(
            backend_name=memory_backend,
            system_dir=memory_system_dir,
            workspace_path=self.workspace_path,
            artifact_dir=memory_artifact_dir,
            memory_user_id=memory_user_id,
            api_key=memory_api_key,
            api_key_env=memory_api_key_env,
            model_name=memory_model_name,
            base_url=memory_base_url,
            backend_config=memory_backend_config or {},
        )
        self.memory_session_id = "default"
        self._turn_memory_context = ""
        self._memory_tools: List[ToolSpec] = self._build_memory_tools()
        self._base_tools = [*self._base_tools, *self._memory_tools]
        self.tools = [*self._base_tools, *self._mcp_tools]
        self._tool_registry = build_tool_registry(self.tools)

    def set_memory_session(self, session_id: str) -> None:
        self.memory_session_id = session_id.strip() or "default"
        self.memory_runtime.set_session(self.memory_session_id)

    def get_memory_system_status(self) -> Dict[str, object]:
        stats = self.memory_runtime.stats()
        return {
            "session_id": self.memory_session_id,
            **stats,
        }

    def _apply_skill_prompt(self) -> None:
        super()._apply_skill_prompt()
        block = self.memory_runtime.build_system_prompt_block()
        self.state.system_prompt = f"{self.state.system_prompt}\n\n{block}"
        if self._turn_memory_context:
            self.state.system_prompt = (
                f"{self.state.system_prompt}\n\n"
                "<memory_context>\n"
                f"{self._turn_memory_context}\n"
                "</memory_context>\n"
            )

    def _build_memory_tools(self) -> List[ToolSpec]:
        async def _mem_get(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_get args={json.dumps(params, ensure_ascii=False)}")
            return json.dumps(self.memory_runtime.active_get(params), ensure_ascii=False)

        async def _mem_set(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_set args={json.dumps(params, ensure_ascii=False)}")
            return json.dumps(self.memory_runtime.active_set(params), ensure_ascii=False)

        async def _mem_update(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_update args={json.dumps(params, ensure_ascii=False)}")
            return json.dumps(self.memory_runtime.active_update(params), ensure_ascii=False)

        async def _mem_delete(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_delete args={json.dumps(params, ensure_ascii=False)}")
            return json.dumps(self.memory_runtime.active_delete(params), ensure_ascii=False)

        return [
            ToolSpec(
                name="mem_get",
                description="Retrieve long-term memories by semantic keyword query.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                        "top_k": {"type": "integer"},
                        "min_score": {"type": "number"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=_mem_get,
            ),
            ToolSpec(
                name="mem_set",
                description="Create or upsert a long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "scope": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                        "source": {"type": "string"},
                        "mentioned_at": {"type": "string"},
                        "occurred_at": {"type": "string"},
                    },
                    "required": ["type", "scope", "content"],
                    "additionalProperties": False,
                },
                handler=_mem_set,
            ),
            ToolSpec(
                name="mem_update",
                description="Update an existing long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "patch": {"type": "object", "additionalProperties": True},
                        "expected_version": {"type": "integer"},
                    },
                    "required": ["id", "patch"],
                    "additionalProperties": False,
                },
                handler=_mem_update,
            ),
            ToolSpec(
                name="mem_delete",
                description="Delete or soft-delete a long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["soft", "hard"]},
                        "expected_version": {"type": "integer"},
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
                handler=_mem_delete,
            ),
        ]

    async def run_turn(self, user_input: str) -> str:
        if self.mcp_enabled and not self._mcp_tools:
            await self._rebuild_tools(refresh_mcp=True)

        if not self.raw_messages and self.state.messages:
            self.raw_messages = [dict(msg) for msg in self.state.messages]

        self.memory_runtime.start_turn()
        passive = self.memory_runtime.passive_retrieve(user_input=user_input, recent_messages=self.raw_messages)
        self._turn_memory_context = passive.injected_context.strip()
        if passive.should_retrieve and self._turn_memory_context:
            self._emit_trace(f"[MEMORY] passive_retrieve hits={len(passive.hits)}")

        self._apply_skill_prompt()
        self._append_turn_message({"role": "user", "content": user_input})

        final_text = ""
        hit_round_limit = True
        turn_cancelled = False
        tool_events: List[MemoryToolEvent] = []
        self._emit_status("模型回复中")
        try:
            for round_index in range(self.max_tool_rounds):
                if self.verbose:
                    print(f"\n[ROUND {round_index + 1}]")
                    print("[MODEL]")
                streamed = False

                def _on_text_delta(delta: str) -> None:
                    nonlocal streamed
                    if turn_cancelled:
                        return
                    streamed = True
                    if self.verbose:
                        print(delta, end="", flush=True)
                    if self.model_delta_callback is not None:
                        self.model_delta_callback(delta)

                response = await self._await_interruptible(
                    self._call_llm(
                        tools=self.tools,
                        on_text_delta=_on_text_delta,
                        should_abort=self._should_abort_llm,
                    ),
                )
                if self.model_round_callback is not None:
                    snap = self.get_token_usage_snapshot()
                    self.model_round_callback(
                        response.text,
                        {
                            "prompt_tokens": int(snap.get("last_prompt_tokens", 0)),
                            "completion_tokens": int(snap.get("last_completion_tokens", 0)),
                            "total_tokens": int(snap.get("last_total_tokens", 0)),
                            "latency_ms": int(snap.get("last_latency_ms", 0)),
                            "source": str(snap.get("last_usage_source", "none")),
                            "round": round_index + 1,
                        },
                    )
                if self.verbose:
                    if streamed:
                        print()
                    elif response.text.strip():
                        print(response.text.strip())

                assistant_message: Message = {"role": "assistant", "content": response.text}
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
                self._append_turn_message(assistant_message)

                if not response.tool_calls:
                    final_text = response.text
                    hit_round_limit = False
                    break

                for call in response.tool_calls:
                    self._emit_status(f"工具调用中: {call.name}")
                    started = time.perf_counter()
                    tool = self._tool_registry.get(call.name)
                    tool_ok = True
                    duration_ms: int | None = None
                    if not tool:
                        tool_output = f"Tool not found: {call.name}"
                        self._print_tool_call(call.name, call.arguments)
                        tool_ok = False
                    else:
                        call_args = dict(call.arguments)
                        if call.name in self.tool_names and "cwd" not in call_args and self.default_tool_cwd:
                            call_args["cwd"] = self.default_tool_cwd
                        self._print_tool_call(call.name, call_args)
                        try:
                            if inspect.iscoroutinefunction(tool.handler):
                                tool_output = await self._await_interruptible(tool.handler(call_args))  # type: ignore[arg-type]
                            else:
                                tool_output = await self._await_interruptible(asyncio.to_thread(tool.handler, call_args))
                            tool_output = str(tool_output)
                        except Exception as err:  # noqa: BLE001
                            tool_output = f"Tool execution error: {err}"
                            tool_ok = False
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    self._print_tool_result(call.name, tool_output, duration_ms=duration_ms)
                    tool_events.append(
                        MemoryToolEvent(
                            tool_name=call.name,
                            arguments=dict(call.arguments),
                            result_preview=self._summarize_text(tool_output, limit=200),
                            duration_ms=duration_ms,
                            ok=not tool_output.startswith("Tool execution error"),
                        ),
                    )
                    self._append_turn_message(
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
                self._append_turn_message({"role": "assistant", "content": final_text})

            if not turn_cancelled:
                write_result = self.memory_runtime.passive_write(
                    user_input=user_input,
                    assistant_text=final_text,
                    recent_messages=self.raw_messages,
                    tool_events=tool_events,
                )
                if write_result.should_store:
                    self._emit_trace(f"[MEMORY] passive_write mutations={len(write_result.mutations)}")

            return final_text
        except (asyncio.CancelledError, InterruptedError):
            turn_cancelled = True
            raise
        except Exception:
            raise
        finally:
            turn_cancelled = True
            self._turn_memory_context = ""
            self._emit_status("等待输入")
