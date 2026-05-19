from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
import re
import time
from uuid import uuid4
from typing import Awaitable, Callable, Dict, List, Set

from core.memory_v6_3 import MemoryRuntimeV63, MemoryToolEvent
from core.runtime_kernel_types import (
    RuntimeEvent,
    RuntimeEventCallback,
    RuntimePhase,
    RuntimeRequest,
    RuntimeResult,
    StopReason,
    TurnStatus,
)
from core.mcp_client import MCPManager
from core.short_memory_v6_1 import (
    SUMMARY_TAG,
    ShortMemoryConfig,
    compact_messages,
    fallback_summary,
    render_transcript,
    split_for_compaction,
)
from core.skill_loader_v7 import SkillLoaderV7
from core.types import Message, ToolSpec
from tools.bash_tool import BashTool
from tools.registry import build_tool_registry, tool_specs_for_names

from .base import BaseAgentLoop


class V7(BaseAgentLoop):
    def __init__(
        self,
        *,
        max_tool_rounds: int = 8,
        default_tool_cwd: str | None = None,
        verbose: bool = True,
        trace_callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        model_delta_callback: Callable[[str], None] | None = None,
        model_round_callback: Callable[[str, Dict[str, int | str]], None] | None = None,
        runtime_event_callback: RuntimeEventCallback | None = None,
        interrupt_check: Callable[[], bool] | None = None,
        short_memory_config: ShortMemoryConfig | None = None,
        mcp_manager: MCPManager | None = None,
        mcp_enabled: bool = False,
        skills_dir: str | None = None,
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
        self.tool_names: Set[str] = {"read", "write", "edit", "grep", "find", "ls"}
        core_tools = tool_specs_for_names(self.tool_names)
        self.max_tool_rounds = max_tool_rounds
        self.default_tool_cwd = default_tool_cwd
        self.verbose = verbose
        self.trace_callback = trace_callback
        self.status_callback = status_callback
        self.model_delta_callback = model_delta_callback
        self.model_round_callback = model_round_callback
        self.runtime_event_callback = runtime_event_callback
        self.interrupt_check = interrupt_check
        self.short_memory_config = short_memory_config or ShortMemoryConfig()
        self._last_compaction_summary = ""
        self._last_compaction_session_tokens = 0
        self._last_compaction_working_prompt_tokens = 0
        self.raw_messages: List[Message] = []

        self.mcp_manager = mcp_manager
        self.mcp_enabled = mcp_enabled and mcp_manager is not None
        self._mcp_tools: List[ToolSpec] = []

        self._base_system_prompt = self.state.system_prompt
        self.skill_loader = SkillLoaderV7(skills_dir)
        self.active_skill_name: str | None = None
        self._base_tools: List[ToolSpec] = [*core_tools, BashTool().to_spec(), self._build_read_skill_tool()]
        self.tools: List[ToolSpec] = list(self._base_tools)
        self._tool_registry: Dict[str, ToolSpec] = build_tool_registry(self.tools)
        self._current_turn_id: str | None = None
        self._last_turn_status: TurnStatus | None = None
        self._last_stop_reason: StopReason | None = None
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

    def _get_runtime_session_id(self) -> str:
        return str(getattr(self, "memory_session_id", "default") or "default")

    def _new_turn_id(self) -> str:
        self._current_turn_id = uuid4().hex
        self._last_turn_status = None
        self._last_stop_reason = None
        return self._current_turn_id

    def _emit_runtime_event(
        self,
        event_type: str,
        *,
        phase: RuntimePhase | None = None,
        data: Dict[str, object] | None = None,
    ) -> None:
        if self.runtime_event_callback is None:
            return
        turn_id = self._current_turn_id or "unknown"
        event = RuntimeEvent(
            type=event_type,
            phase=phase,
            session_id=self._get_runtime_session_id(),
            turn_id=turn_id,
            ts=time.time(),
            data=data or {},
        )
        if event_type == "turn_completed":
            self._last_turn_status = TurnStatus.COMPLETED
            try:
                self._last_stop_reason = StopReason(str(event.data.get("stop_reason", StopReason.FINAL_ANSWER.value)))
            except ValueError:
                self._last_stop_reason = StopReason.FINAL_ANSWER
        elif event_type == "turn_failed":
            self._last_turn_status = TurnStatus.FAILED
            try:
                self._last_stop_reason = StopReason(str(event.data.get("stop_reason", StopReason.MODEL_ERROR.value)))
            except ValueError:
                self._last_stop_reason = StopReason.MODEL_ERROR
        elif event_type == "turn_aborted":
            self._last_turn_status = TurnStatus.ABORTED
            self._last_stop_reason = StopReason.ABORTED
        self.runtime_event_callback(event)

    def _emit_phase(self, phase: RuntimePhase, **data: object) -> None:
        self._emit_runtime_event("phase_changed", phase=phase, data=dict(data))

    async def run_turn_request(self, request: RuntimeRequest) -> RuntimeResult:
        if hasattr(self, "set_memory_session"):
            try:
                getattr(self, "set_memory_session")(request.session_id)
            except Exception:
                pass
        if request.workspace_path is not None and hasattr(self, "workspace_path"):
            try:
                setattr(self, "workspace_path", request.workspace_path)
            except Exception:
                pass

        previous_callback = self.runtime_event_callback
        captured_events: List[RuntimeEvent] = []

        def _capture(event: RuntimeEvent) -> None:
            captured_events.append(event)
            if previous_callback is not None:
                previous_callback(event)

        self.runtime_event_callback = _capture
        final_text = ""
        error_text: str | None = None
        try:
            final_text = await self.run_turn(request.user_input)
        except (asyncio.CancelledError, InterruptedError) as err:
            error_text = str(err)
            if self._last_turn_status is None:
                self._last_turn_status = TurnStatus.ABORTED
            if self._last_stop_reason is None:
                self._last_stop_reason = StopReason.ABORTED
        except Exception as err:  # noqa: BLE001
            error_text = str(err)
            if self._last_turn_status is None:
                self._last_turn_status = TurnStatus.FAILED
            if self._last_stop_reason is None:
                self._last_stop_reason = StopReason.MODEL_ERROR
        finally:
            self.runtime_event_callback = previous_callback

        turn_status = self._last_turn_status or TurnStatus.COMPLETED
        stop_reason = self._last_stop_reason or StopReason.FINAL_ANSWER
        return RuntimeResult(
            session_id=request.session_id,
            turn_id=self._current_turn_id or "unknown",
            final_text=final_text,
            turn_status=turn_status,
            stop_reason=stop_reason,
            events=tuple(captured_events),
            usage_summary=self.get_token_usage_snapshot(),
            error=error_text,
        )

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
        available_skills = self._build_available_skills_block()
        preferred = ""
        if self.active_skill_name:
            preferred = (
                "\n\n[Preferred Skill]\n"
                f"- name: {self.active_skill_name}\n"
                "Use read_skill to load it if relevant to the user's request."
            )
        self.state.system_prompt = (
            f"{self._base_system_prompt}\n\n"
            "Skills are loaded with progressive disclosure.\n"
            "First inspect available skill metadata, then call read_skill(name) only when needed.\n\n"
            f"{available_skills}"
            f"{preferred}"
        )
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

    def _print_tool_call(self, name: str, args: Dict[str, object]) -> None:
        args_text = json.dumps(args, ensure_ascii=False, sort_keys=True)
        self._emit_trace(f"[TOOL CALL] {name} args={self._summarize_text(args_text, limit=160)}")

    def _print_tool_result(self, name: str, output: str, *, duration_ms: int | None = None) -> None:
        summary = self._summarize_text(output)
        if duration_ms is None:
            self._emit_trace(f"[TOOL RESULT] {name} {summary}")
            return
        self._emit_trace(f"[TOOL RESULT] {name} {summary} (duration={duration_ms}ms)")

    def _print_mcp_call(self, tool_name: str, params: Dict[str, object]) -> None:
        args = json.dumps(params, ensure_ascii=False, sort_keys=True)
        self._emit_trace(f"[MCP CALL] {tool_name} args={args}")

    def _print_skill_call(self, skill_name: str) -> None:
        self._emit_trace(f"[SKILL CALL] read_skill name={skill_name}")

    async def _await_interruptible(self, coro: Awaitable[object]) -> object:
        task = asyncio.create_task(coro)
        try:
            while True:
                if self.interrupt_check is not None and self.interrupt_check():
                    task.cancel()
                    raise InterruptedError("Turn interrupted")
                done, _ = await asyncio.wait({task}, timeout=0.1)
                if task in done:
                    return task.result()
        except asyncio.CancelledError:
            task.cancel()
            raise

    def _should_abort_llm(self) -> bool:
        if self.interrupt_check is None:
            return False
        return self.interrupt_check()

    def list_skills(self) -> list[str]:
        return self.skill_loader.list_skill_names()

    def use_skill(self, name: str) -> bool:
        if self.skill_loader.get(name) is None:
            return False
        self.active_skill_name = name
        return True

    def disable_skill(self) -> None:
        self.active_skill_name = None

    def _build_read_skill_tool(self) -> ToolSpec:
        async def _handler(params: Dict[str, object]) -> str:
            skill_name = str(params.get("name", "")).strip()
            self._print_skill_call(skill_name or "<empty>")
            if not skill_name:
                return "Missing required parameter: name"
            skill = self.skill_loader.get(skill_name)
            if not skill:
                return f"Skill not found: {skill_name}"
            skill_base_dir = str(Path(skill.path).resolve().parent)
            rendered_content = skill.content.replace("{baseDir}", skill_base_dir)
            return (
                f'<skill name="{skill.name}" location="{skill.path}" base_dir="{skill_base_dir}">\n'
                f"{rendered_content}\n"
                "</skill>"
            )

        return ToolSpec(
            name="read_skill",
            description=(
                "Load full instructions for a skill by name. "
                "Use this when a task matches an available skill from <available_skills>."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name from <available_skills> (for example: pptx).",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_handler,
        )

    def _build_available_skills_block(self) -> str:
        lines = ["<available_skills>"]
        for skill in self.skill_loader.list_skills():
            lines.extend(
                [
                    "  <skill>",
                    f"    <name>{skill.name}</name>",
                    f"    <description>{skill.description}</description>",
                    f"    <location>{skill.path}</location>",
                    "  </skill>",
                ],
            )
        lines.append("</available_skills>")
        return "\n".join(lines)

    async def _rebuild_tools(self, *, refresh_mcp: bool) -> None:
        mcp_tools: List[ToolSpec] = []
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

        self._mcp_tools = mcp_tools
        self.tools = [*self._base_tools, *self._mcp_tools]
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
        return sorted(tool.name for tool in self._mcp_tools)

    def set_raw_messages(self, messages: List[Message]) -> None:
        self.raw_messages = list(messages)

    def get_raw_messages(self) -> List[Message]:
        return list(self.raw_messages)

    def _append_turn_message(self, message: Message) -> None:
        # Keep two tracks:
        # - state.messages: working context (can be compacted)
        # - raw_messages: immutable raw history (for persistence/memory extraction)
        self.state.messages.append(message)
        self.raw_messages.append(dict(message))

    def get_short_memory_state(self) -> Dict[str, object]:
        if not self._last_compaction_summary:
            for msg in reversed(self.state.messages):
                text = str(msg.get("content", ""))
                if text.startswith(SUMMARY_TAG):
                    parts = text.split("\n\n", 1)
                    if len(parts) == 2:
                        self._last_compaction_summary = parts[1].strip()
                    break
        snap = self.get_token_usage_snapshot()
        working_prompt_tokens = self._estimate_current_working_prompt_tokens()
        return {
            "auto_enabled": self.short_memory_config.auto_enabled,
            "usage_threshold_tokens": self.short_memory_config.usage_threshold_tokens,
            "keep_recent_user_turns": self.short_memory_config.keep_recent_user_turns,
            "min_prefix_messages": self.short_memory_config.min_prefix_messages,
            "max_prefix_messages": self.short_memory_config.max_prefix_messages,
            "session_total_tokens": int(snap.get("session_total_tokens", 0)),
            "working_prompt_tokens": working_prompt_tokens,
            "last_compaction_session_tokens": self._last_compaction_session_tokens,
            "last_compaction_working_prompt_tokens": self._last_compaction_working_prompt_tokens,
            "last_compaction_summary": self._last_compaction_summary,
            "raw_message_count": len(self.raw_messages),
            "working_message_count": len(self.state.messages),
        }

    def hydrate_short_memory_summary(self, summary: str) -> None:
        self._last_compaction_summary = summary.strip()

    def hydrate_short_memory_compaction_state(self, *, session_tokens: int, working_prompt_tokens: int) -> None:
        self._last_compaction_session_tokens = max(0, int(session_tokens))
        self._last_compaction_working_prompt_tokens = max(0, int(working_prompt_tokens))

    def set_short_memory_auto(self, enabled: bool) -> None:
        self.short_memory_config.auto_enabled = enabled

    def set_short_memory_threshold(self, threshold_tokens: int) -> None:
        self.short_memory_config.usage_threshold_tokens = max(1000, threshold_tokens)

    def _estimate_current_working_prompt_tokens(self) -> int:
        llm_messages: List[Message] = [
            {"role": "system", "content": self.state.system_prompt},
            *self.state.messages,
        ]
        return self._estimate_tokens_from_obj(llm_messages)

    @staticmethod
    def _clean_compaction_summary(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        # Remove reasoning traces if provider returns them in content.
        cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
        cleaned = re.sub(r"(?is)```.*?```", "", cleaned)
        cleaned = cleaned.strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    @staticmethod
    def _looks_like_structured_summary(text: str) -> bool:
        if not text.strip():
            return False
        required_markers = ["用户目标", "关键约束", "已完成", "未完成", "下一步"]
        hit = sum(1 for k in required_markers if k in text)
        return hit >= 3

    def _accumulate_usage_from_response(self, *, request_messages: List[Message], response_text: str, source_usage: object) -> None:
        usage = source_usage
        if usage is None:
            est_prompt = self._estimate_tokens_from_obj(request_messages)
            est_completion = self._estimate_tokens_from_obj({"text": response_text, "tool_calls": []})
            from core.types import TokenUsage  # local import to avoid widening module imports

            usage = TokenUsage(
                prompt_tokens=est_prompt,
                completion_tokens=est_completion,
                total_tokens=est_prompt + est_completion,
                source="estimated",
            )
        self._last_usage = usage  # type: ignore[assignment]
        self._usage_seen = True
        self._session_prompt_tokens += int(usage.prompt_tokens)
        self._session_completion_tokens += int(usage.completion_tokens)
        self._session_total_tokens += int(usage.total_tokens)

    async def _summarize_messages_for_compaction(self, messages: List[Dict[str, object]], reason: str) -> str:
        transcript = render_transcript(messages, max_chars=self.short_memory_config.max_transcript_chars)
        if not transcript.strip():
            return fallback_summary(messages, max_chars=self.short_memory_config.max_summary_chars)
        prompt = (
            "你是短期记忆压缩器。你的任务是生成“供后续继续执行任务”的摘要，"
            "不是给用户写回复。\n"
            "严格要求：\n"
            "1) 不要输出 <think> 或任何思维链。\n"
            "2) 不要写“我可以/需要我/告诉我”等面向用户的话术。\n"
            "3) 只保留执行相关信息，删除寒暄与重复。\n"
            "4) 输出必须使用下面模板（中文）：\n"
            "[SHORT MEMORY SUMMARY]\n"
            "- 用户目标: ...\n"
            "- 关键约束: ...\n"
            "- 已完成: ...\n"
            "- 未完成: ...\n"
            "- 下一步: ...\n\n"
            f"压缩原因: {reason}\n\n"
            "历史对话如下：\n"
            f"{transcript}"
        )
        req_messages: List[Message] = [
            {
                "role": "system",
                "content": "你是一个严谨的对话压缩助手，只输出可执行摘要。",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            started = time.perf_counter()
            response = await self._await_interruptible(
                self.client.generate(
                    model_name=self.model_name,
                    messages=req_messages,
                    tools=None,
                    timeout_seconds=self.timeout_seconds,
                    stream=False,
                    should_abort=self._should_abort_llm,
                ),
            )
            self._last_latency_ms = int((time.perf_counter() - started) * 1000)
            self._accumulate_usage_from_response(
                request_messages=req_messages,
                response_text=str(getattr(response, "text", "")),
                source_usage=getattr(response, "usage", None),
            )
            summary = self._clean_compaction_summary(str(getattr(response, "text", "")))
        except Exception:
            summary = ""

        if not summary:
            summary = fallback_summary(messages, max_chars=self.short_memory_config.max_summary_chars)
        if not self._looks_like_structured_summary(summary):
            # Enforce summary-style output when model drifts into reply-style text.
            summary = (
                "[SHORT MEMORY SUMMARY]\n"
                "- 用户目标: " + fallback_summary(messages, max_chars=300).replace("\n", " ") + "\n"
                "- 关键约束: 保留任务目标与约束，忽略寒暄。\n"
                "- 已完成: 见历史中已执行结果与工具输出。\n"
                "- 未完成: 需要继续执行的步骤待补齐。\n"
                "- 下一步: 先核对当前产物，再继续未完成任务。"
            )
        summary = self._clean_compaction_summary(summary)
        if len(summary) > self.short_memory_config.max_summary_chars:
            summary = summary[: self.short_memory_config.max_summary_chars]
        return summary

    def _has_summary_message(self) -> bool:
        for msg in self.state.messages:
            if str(msg.get("role")) == "assistant" and str(msg.get("content", "")).startswith(SUMMARY_TAG):
                return True
        return False

    async def compress_short_memory(self, *, reason: str = "manual") -> Dict[str, object]:
        prefix, _ = split_for_compaction(
            self.state.messages,
            keep_recent_user_turns=self.short_memory_config.keep_recent_user_turns,
            min_prefix_messages=self.short_memory_config.min_prefix_messages,
            max_prefix_messages=self.short_memory_config.max_prefix_messages,
        )
        if not prefix:
            return {"performed": False, "message": "not enough history to compact"}

        summary_text = await self._summarize_messages_for_compaction(prefix, reason)
        result = compact_messages(
            self.state.messages,
            summary_text=summary_text,
            reason=reason,
            keep_recent_user_turns=self.short_memory_config.keep_recent_user_turns,
            min_prefix_messages=self.short_memory_config.min_prefix_messages,
            max_prefix_messages=self.short_memory_config.max_prefix_messages,
        )
        if bool(result.get("performed")):
            self.state.messages = list(result["messages"])  # type: ignore[index]
            self._last_compaction_summary = summary_text
            snap = self.get_token_usage_snapshot()
            self._last_compaction_session_tokens = int(snap.get("session_total_tokens", 0))
            self._last_compaction_working_prompt_tokens = self._estimate_current_working_prompt_tokens()
        return result

    async def maybe_auto_compress_short_memory(self) -> Dict[str, object] | None:
        if not self.short_memory_config.auto_enabled:
            return None
        threshold = self.short_memory_config.usage_threshold_tokens
        current_working_prompt = self._estimate_current_working_prompt_tokens()
        if current_working_prompt < threshold:
            return None
        # Debounce repeated auto-compaction when context has not materially grown since last compaction.
        min_growth = max(1024, threshold // 20)
        if (
            self._last_compaction_working_prompt_tokens > 0
            and current_working_prompt - self._last_compaction_working_prompt_tokens < min_growth
        ):
            return None
        before_working_prompt = current_working_prompt
        result = await self.compress_short_memory(reason=f"auto-threshold-{threshold}")
        if bool(result.get("performed")):
            result["before_working_prompt_tokens"] = before_working_prompt
            return result
        self._last_compaction_working_prompt_tokens = current_working_prompt
        return None

    async def run_turn(self, user_input: str) -> str:
        self._new_turn_id()
        self._emit_phase(RuntimePhase.TURN_START, user_text_preview=self._summarize_text(user_input, limit=80))
        if self.mcp_enabled and not self._mcp_tools:
            await self._rebuild_tools(refresh_mcp=True)

        self._emit_phase(
            RuntimePhase.STATE_LOAD,
            working_message_count=len(self.state.messages),
            raw_message_count=len(self.raw_messages),
        )
        if not self.raw_messages and self.state.messages:
            self.raw_messages = [dict(msg) for msg in self.state.messages]

        self.memory_runtime.start_turn()
        self._emit_phase(RuntimePhase.CONTEXT_PREPARE)
        passive = self.memory_runtime.passive_retrieve(user_input=user_input, recent_messages=self.raw_messages)
        self._turn_memory_context = passive.injected_context.strip()
        if passive.should_retrieve and self._turn_memory_context:
            self._emit_trace(f"[MEMORY] passive_retrieve hits={len(passive.hits)}")
            self._emit_runtime_event(
                "memory_retrieved",
                phase=RuntimePhase.CONTEXT_PREPARE,
                data={"hit_count": len(passive.hits), "backend": self.memory_runtime.backend_name},
            )

        self._apply_skill_prompt()
        self._append_turn_message({"role": "user", "content": user_input})

        final_text = ""
        hit_round_limit = True
        turn_cancelled = False
        tool_events: List[MemoryToolEvent] = []
        self._emit_status("模型回复中")
        try:
            for round_index in range(self.max_tool_rounds):
                self._emit_phase(RuntimePhase.PRE_MODEL, round_index=round_index + 1)
                if self.verbose:
                    print(f"\n[ROUND {round_index + 1}]")
                    print("[MODEL]")
                streamed = False

                def _on_text_delta(delta: str) -> None:
                    nonlocal streamed
                    if turn_cancelled:
                        return
                    streamed = True
                    self._emit_runtime_event(
                        "assistant_delta",
                        phase=RuntimePhase.MODEL_STEP,
                        data={"delta": delta},
                    )
                    if self.verbose:
                        print(delta, end="", flush=True)
                    if self.model_delta_callback is not None:
                        self.model_delta_callback(delta)

                self._emit_phase(RuntimePhase.MODEL_STEP, round_index=round_index + 1)
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
                            "ttfb_ms": int(response.metrics.get("ttfb_ms", 0) or 0),
                            "decode_ms": int(response.metrics.get("decode_ms", 0) or 0),
                            "stream_ms": int(response.metrics.get("stream_ms", 0) or 0),
                        },
                    )
                self._emit_runtime_event(
                    "assistant_message_completed",
                    phase=RuntimePhase.POST_MODEL,
                    data={
                        "round_index": round_index + 1,
                        "tool_call_count": len(response.tool_calls),
                        "text_preview": self._summarize_text(response.text, limit=120),
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
                    self._emit_phase(RuntimePhase.POST_MODEL, tool_call_count=0)
                    break

                self._emit_phase(RuntimePhase.POST_MODEL, tool_call_count=len(response.tool_calls))
                for call in response.tool_calls:
                    self._emit_phase(RuntimePhase.TOOL_DISPATCH, tool_name=call.name, round_index=round_index + 1)
                    self._emit_runtime_event(
                        "tool_call_started",
                        phase=RuntimePhase.TOOL_DISPATCH,
                        data={"tool_name": call.name, "arguments": dict(call.arguments)},
                    )
                    self._emit_status(f"工具调用中: {call.name}")
                    started = time.perf_counter()
                    tool = self._tool_registry.get(call.name)
                    tool_ok = True
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
                    self._emit_phase(RuntimePhase.TOOL_RESULT, tool_name=call.name, ok=tool_ok)
                    self._emit_runtime_event(
                        "tool_call_finished" if tool_ok else "tool_call_failed",
                        phase=RuntimePhase.TOOL_RESULT,
                        data={
                            "tool_name": call.name,
                            "duration_ms": duration_ms,
                            "ok": tool_ok,
                            "result_preview": self._summarize_text(tool_output, limit=160),
                        },
                    )
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
                self._emit_status("记忆写入中")
                self._emit_phase(RuntimePhase.TURN_PERSIST_START)
                write_result = self.memory_runtime.passive_write(
                    user_input=user_input,
                    assistant_text=final_text,
                    recent_messages=self.raw_messages,
                    tool_events=tool_events,
                )
                self._emit_phase(RuntimePhase.TURN_PERSIST, mutation_count=len(write_result.mutations))
                if write_result.should_store:
                    self._emit_trace(f"[MEMORY] passive_write mutations={len(write_result.mutations)}")
                    self._emit_runtime_event(
                        "memory_persisted",
                        phase=RuntimePhase.TURN_PERSIST,
                        data={
                            "mutation_count": len(write_result.mutations),
                            **(write_result.debug if isinstance(write_result.debug, dict) else {}),
                        },
                    )
                self._emit_phase(RuntimePhase.TURN_COMPLETE)

            stop_reason = StopReason.FINAL_ANSWER.value if not hit_round_limit else StopReason.MAX_TOOL_ROUNDS.value
            self._emit_runtime_event(
                "turn_completed",
                phase=RuntimePhase.TURN_END,
                data={"turn_status": TurnStatus.COMPLETED.value, "stop_reason": stop_reason},
            )
            self._emit_phase(RuntimePhase.TURN_END, stop_reason=stop_reason)
            return final_text
        except (asyncio.CancelledError, InterruptedError):
            turn_cancelled = True
            self._emit_runtime_event(
                "turn_aborted",
                phase=RuntimePhase.TURN_END,
                data={"turn_status": TurnStatus.ABORTED.value, "stop_reason": StopReason.ABORTED.value},
            )
            self._emit_phase(RuntimePhase.TURN_END, stop_reason=StopReason.ABORTED.value)
            raise
        except Exception as err:  # noqa: BLE001
            self._emit_runtime_event(
                "turn_failed",
                phase=RuntimePhase.TURN_END,
                data={
                    "turn_status": TurnStatus.FAILED.value,
                    "stop_reason": StopReason.MODEL_ERROR.value,
                    "error": str(err),
                },
            )
            self._emit_phase(RuntimePhase.TURN_END, stop_reason=StopReason.MODEL_ERROR.value)
            raise
        finally:
            turn_cancelled = True
            self._turn_memory_context = ""
            self._emit_status("等待输入")
