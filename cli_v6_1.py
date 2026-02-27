#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import signal
import shutil
import textwrap
from typing import Any, Dict, List

from core.client import OpenAICompatClient
from core.config import load_config
from core.logging_utils import create_session_logger
from core.mcp_client import MCPManager as MCPManagerV4
from core.session_store_v6 import SessionRecord, SessionStoreV6
from core.short_memory_v6_1 import ShortMemoryConfig
from core.types import Message, TokenUsage
from loops.agent_loop_v6_1 import V6_1

try:
    import readline
except Exception:  # noqa: BLE001
    readline = None  # type: ignore[assignment]

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
except Exception:  # noqa: BLE001
    PromptSession = None  # type: ignore[assignment]
    KeyBindings = None  # type: ignore[assignment]


async def _read_line(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def _build_prompt_session(ui: "RefreshUI") -> Any | None:
    if PromptSession is None or KeyBindings is None:
        return None
    kb = KeyBindings()

    @kb.add("escape", "k")
    def _page_up(event: Any) -> None:  # noqa: ANN401
        ui.page_up()
        event.app.invalidate()

    @kb.add("escape", "j")
    def _page_down(event: Any) -> None:  # noqa: ANN401
        ui.page_down()
        event.app.invalidate()

    @kb.add("escape", "0")
    def _page_end(event: Any) -> None:  # noqa: ANN401
        ui.page_end()
        event.app.invalidate()

    @kb.add("escape", "u")
    def _line_up(event: Any) -> None:  # noqa: ANN401
        ui.line_up()
        event.app.invalidate()

    @kb.add("escape", "d")
    def _line_down(event: Any) -> None:  # noqa: ANN401
        ui.line_down()
        event.app.invalidate()

    return PromptSession(key_bindings=kb)


class RefreshUI:
    def __init__(self, *, enabled: bool, model_name: str, log_path: str, max_lines: int = 18) -> None:
        self.enabled = enabled
        self.model_name = model_name
        self.log_path = log_path
        self.max_lines = max_lines
        self.session_id = "-"
        self.session_file = "-"
        self.token_line = "[TOKENS] no LLM call yet"
        self.activity_status = "Activity: 状态=等待输入 | context=0% (0/1) | session(p=0 c=0 t=0)"
        self.dialogue: list[tuple[str, str]] = []
        self.output_lines: list[str] = []
        self.dialogue_page = 0
        self._last_dialogue_page_total = 1
        self.dialogue_line_offset = 0
        self._last_dialogue_line_max = 0
        self.runtime_status = "等待输入"
        self._stream_assistant_index: int | None = None

    def set_session(self, session_id: str, session_file: str) -> None:
        self.session_id = session_id
        self.session_file = session_file

    def set_token_line(self, line: str) -> None:
        self.token_line = line

    def set_activity_status(self, line: str) -> None:
        self.activity_status = line

    def set_runtime_status(self, status: str) -> None:
        self.runtime_status = status

    def add(self, text: str) -> None:
        if self.enabled:
            lines = text.splitlines() if text else [""]
            self.output_lines = lines[:200]
            self.render()
            return
        print(text)

    def clear_output(self) -> None:
        self.output_lines = []
        if self.enabled:
            self.render()

    def add_dialogue(self, role: str, text: str) -> None:
        self.dialogue.append((role, text if text else ""))
        self.dialogue = self.dialogue[-60:]
        self.dialogue_page = 0
        self.dialogue_line_offset = 0
        self._stream_assistant_index = None
        if self.enabled:
            self.render()
        else:
            print(f"[{role}] {text}")

    def stream_assistant_delta(self, delta: str) -> None:
        if not delta:
            return
        if self._stream_assistant_index is None:
            self.dialogue.append(("ASSISTANT", ""))
            self._stream_assistant_index = len(self.dialogue) - 1
            self.dialogue = self.dialogue[-60:]
            if self._stream_assistant_index >= len(self.dialogue):
                self._stream_assistant_index = len(self.dialogue) - 1
            self.dialogue_page = 0
            self.dialogue_line_offset = 0
        idx = self._stream_assistant_index
        if idx is None:
            return
        role, content = self.dialogue[idx]
        self.dialogue[idx] = (role, f"{content}{delta}")
        if self.enabled:
            self.render()

    def close_assistant_stream(self) -> None:
        self._stream_assistant_index = None
        if self.enabled:
            self.render()

    def append_to_last_assistant(self, suffix: str) -> None:
        for idx in range(len(self.dialogue) - 1, -1, -1):
            role, content = self.dialogue[idx]
            if role == "ASSISTANT":
                self.dialogue[idx] = (role, f"{content}\n{suffix}")
                if self.enabled:
                    self.render()
                return
        self.add_dialogue("ASSISTANT", suffix)

    def hydrate_dialogue_from_messages(self, messages: List[Message], *, max_messages: int = 12) -> None:
        self.dialogue = []
        tail = messages[-max_messages:]
        for msg in tail:
            role = str(msg.get("role"))
            if role not in {"user", "assistant"}:
                continue
            content = _message_content_to_text(msg.get("content", ""))
            self.dialogue.append((role.upper(), content))
        self.dialogue = self.dialogue[-60:]
        self.dialogue_page = 0
        self.dialogue_line_offset = 0
        if self.enabled:
            self.render()

    def page_up(self) -> None:
        self.dialogue_page = min(self.dialogue_page + 1, max(0, self._last_dialogue_page_total - 1))
        self.dialogue_line_offset = 0
        if self.enabled:
            self.render()

    def page_down(self) -> None:
        self.dialogue_page = max(0, self.dialogue_page - 1)
        self.dialogue_line_offset = 0
        if self.enabled:
            self.render()

    def page_end(self) -> None:
        self.dialogue_page = 0
        self.dialogue_line_offset = 0
        if self.enabled:
            self.render()

    def line_up(self) -> None:
        self.dialogue_page = 0
        self.dialogue_line_offset = min(self.dialogue_line_offset + 1, max(0, self._last_dialogue_line_max))
        if self.enabled:
            self.render()

    def line_down(self) -> None:
        self.dialogue_page = 0
        self.dialogue_line_offset = max(0, self.dialogue_line_offset - 1)
        if self.enabled:
            self.render()

    def line_end(self) -> None:
        self.dialogue_page = 0
        self.dialogue_line_offset = 0
        if self.enabled:
            self.render()

    def _render_dialogue_lines(self, width: int, height: int) -> list[str]:
        if height <= 0:
            return []
        lines: list[str] = []
        body_width = max(20, width - 2)
        for role, content in self.dialogue:
            prefix = f"[{role}] "
            raw_lines = content.splitlines() or [""]
            first_line = True
            for raw in raw_lines:
                wrapped = textwrap.wrap(raw, width=max(10, body_width - len(prefix))) or [""]
                for part in wrapped:
                    lines.append(f"{prefix if first_line else ' ' * len(prefix)}{part}")
                    first_line = False
        if not lines:
            self._last_dialogue_page_total = 1
            return [""] * height

        page_size = max(1, height)
        total_pages = max(1, (len(lines) + page_size - 1) // page_size)
        self._last_dialogue_page_total = total_pages
        self.dialogue_page = min(self.dialogue_page, total_pages - 1)
        self._last_dialogue_line_max = max(0, len(lines) - page_size)
        self.dialogue_line_offset = min(self.dialogue_line_offset, self._last_dialogue_line_max)

        start_from_end = self.dialogue_page * page_size + self.dialogue_line_offset
        end_idx = max(0, len(lines) - start_from_end)
        start_idx = max(0, end_idx - page_size)
        page_lines = lines[start_idx:end_idx]

        if len(page_lines) < height:
            return page_lines + ([""] * (height - len(page_lines)))
        return page_lines

    def render(self) -> None:
        if not self.enabled:
            return
        size = shutil.get_terminal_size((120, 36))
        width = max(60, size.columns)
        total_rows = max(20, size.lines)
        sep = "-" * width
        header_lines = [
            f"agent-loop v6.1 | model={self.model_name}",
            f"log: {self.log_path}",
            f"session: {self.session_id} ({self.session_file})",
            "Commands: /quit /state /tokens /session /mcp /skill /memory",
        ]
        has_output = any(line.strip() for line in self.output_lines)
        fixed_rows = len(header_lines) + 4  # top sep + middle title + bottom sep + activity line
        content_rows = max(8, total_rows - fixed_rows - 1)  # keep one row for prompt

        if has_output:
            # Shared middle area: Dialogue (dominant) + split line + Output (bottom, compact)
            # Keep output as a small bottom pane based on actual lines.
            desired_output_rows = len(self.output_lines) + 1  # +1 for "[Output]" title
            output_rows = min(max(3, desired_output_rows), max(3, min(8, content_rows // 4)))
            dialogue_rows = max(1, content_rows - output_rows - 1)
            # Ensure dialogue area never collapses when output is verbose.
            if content_rows >= 10 and dialogue_rows < 6:
                shrink = 6 - dialogue_rows
                output_rows = max(3, output_rows - shrink)
                dialogue_rows = max(1, content_rows - output_rows - 1)
        else:
            output_rows = 0
            dialogue_rows = content_rows

        dialogue_block = self._render_dialogue_lines(width, dialogue_rows)
        output_block: list[str] = []
        if has_output:
            output_block.append("[Output]")
            remaining = max(0, output_rows - 1)
            head = self.output_lines[:remaining]
            if len(head) < remaining:
                head = head + ([""] * (remaining - len(head)))
            output_block.extend(head)

        print("\033[2J\033[H", end="")
        for row in header_lines:
            print(row[:width])
        print(sep)
        print(
            f"Dialogue: page {self.dialogue_page + 1}/{self._last_dialogue_page_total} "
            f"| line_offset={self.dialogue_line_offset} "
            "(Alt+K prev, Alt+J next, Alt+0 end, Alt+U line-up, Alt+D line-down)",
        )
        for line in dialogue_block:
            print(line[:width])
        if has_output:
            print("." * width)
            for line in output_block:
                print(line[:width])
        print(sep)
        print(self.activity_status[:width])
        print(sep)

    async def read_line(self, prompt: str) -> str:
        if self.enabled:
            self.render()
        return await _read_line(prompt)


def _auto_title(messages: List[Message]) -> str:
    user_msgs = [str(m.get("content", "")).strip() for m in messages if str(m.get("role")) == "user"]
    if not user_msgs:
        return "New Session"

    # Use the first meaningful user query as stable session title.
    first = ""
    for item in user_msgs:
        cleaned = " ".join(item.replace("\n", " ").split())
        if cleaned and not cleaned.startswith("/"):
            first = cleaned
            break
    if not first:
        first = " ".join(user_msgs[0].replace("\n", " ").split()) or "Untitled Session"

    return first[:40] + ("..." if len(first) > 40 else "")


def _session_brief_line(record: SessionRecord) -> str:
    title = (record.title or "Untitled Session").replace("\n", " ").strip()
    title_short = title[:60] + ("..." if len(title) > 60 else "")
    return (
        f"{record.session_id} | updated={record.updated_at} | "
        f"msgs={len(record.messages)} | {record.file_path.name} | title={title_short}"
    )


def _has_user_messages(messages: List[Message]) -> bool:
    return any(str(m.get("role")) == "user" and str(m.get("content", "")).strip() for m in messages)


def _persist_if_needed(
    store: SessionStoreV6,
    record: SessionRecord,
    messages: List[Message],
    *,
    memory_summary: str = "",
    token_snapshot: dict[str, int | bool] | None = None,
    short_memory_state: dict[str, object] | None = None,
) -> bool:
    if not _has_user_messages(messages):
        return False
    record.messages = list(messages)
    record.title = _auto_title(record.messages)
    record.summary = memory_summary.strip()
    snap = token_snapshot or {}
    record.session_prompt_tokens = int(snap.get("session_prompt_tokens", 0) or 0)
    record.session_completion_tokens = int(snap.get("session_completion_tokens", 0) or 0)
    record.session_total_tokens = int(snap.get("session_total_tokens", 0) or 0)
    record.last_prompt_tokens = int(snap.get("last_prompt_tokens", 0) or 0)
    record.last_completion_tokens = int(snap.get("last_completion_tokens", 0) or 0)
    record.last_total_tokens = int(snap.get("last_total_tokens", 0) or 0)
    record.last_usage_source = str(snap.get("last_usage_source", "none") or "none")
    sm = short_memory_state or {}
    record.last_compaction_session_tokens = int(sm.get("last_compaction_session_tokens", 0) or 0)
    record.last_compaction_working_prompt_tokens = int(sm.get("last_compaction_working_prompt_tokens", 0) or 0)
    store.save(record)
    return True


def _latest_by_role(messages: List[Message], role: str) -> str:
    for msg in reversed(messages):
        if str(msg.get("role")) != role:
            continue
        content = " ".join(str(msg.get("content", "")).split())
        if content:
            return content[:80] + ("..." if len(content) > 80 else "")
    return "-"


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _raw_messages_lines(messages: List[Message], *, limit: int) -> list[str]:
    if limit <= 0 or not messages:
        return []
    tail = messages[-limit:]
    lines: list[str] = ["", f"Restored raw messages (last {len(tail)}):"]
    for idx, msg in enumerate(tail, start=1):
        role = str(msg.get("role", "unknown"))
        text = _message_content_to_text(msg.get("content", ""))
        lines.append(f"[{idx}] {role}:")
        lines.append(text)
        lines.append("")
    return lines


def _restored_preview_lines(messages: List[Message], *, max_pairs: int = 4) -> list[str]:
    if not messages:
        return ["(empty session)"]
    lines: list[str] = ["Recent dialogue preview:"]
    user_items = [m for m in messages if str(m.get("role")) == "user"]
    if not user_items:
        return lines + ["(no user messages)"]
    tail_users = user_items[-max_pairs:]
    for idx, user_msg in enumerate(tail_users, start=1):
        user_text = " ".join(str(user_msg.get("content", "")).split())
        lines.append(f"[U{idx}] {user_text[:140]}{'...' if len(user_text) > 140 else ''}")
        assistant_text = "-"
        try:
            pos = messages.index(user_msg)
        except ValueError:
            pos = -1
        if pos >= 0:
            for follow in messages[pos + 1 :]:
                if str(follow.get("role")) == "assistant":
                    assistant_text = " ".join(str(follow.get("content", "")).split())
                    break
                if str(follow.get("role")) == "user":
                    break
        lines.append(
            f"[A{idx}] {assistant_text[:140]}{'...' if len(assistant_text) > 140 else ''}",
        )
    return lines


def _token_snapshot(loop: V6_1) -> dict[str, int | bool]:
    return loop.get_token_usage_snapshot()


def _currency_symbol(code: str) -> str:
    upper = (code or "").upper()
    if upper == "CNY":
        return "¥"
    if upper == "USD":
        return "$"
    return f"{upper} "


def _compute_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_per_million: float | None,
    output_per_million: float | None,
) -> float | None:
    if input_per_million is None or output_per_million is None:
        return None
    if input_per_million < 0 or output_per_million < 0:
        return None
    return (prompt_tokens / 1_000_000.0) * input_per_million + (completion_tokens / 1_000_000.0) * output_per_million


def _restore_token_baseline(loop: V6_1) -> None:
    st = loop.get_short_memory_state()
    working_prompt = max(0, int(st.get("working_prompt_tokens", 0)))
    if working_prompt <= 0:
        return
    # Restore a practical baseline so Activity/TOKENS are meaningful right after /session use.
    loop._last_usage = TokenUsage(  # type: ignore[attr-defined]
        prompt_tokens=working_prompt,
        completion_tokens=0,
        total_tokens=working_prompt,
        source="estimated_restore",
    )
    loop._usage_seen = True  # type: ignore[attr-defined]
    loop._session_prompt_tokens = working_prompt  # type: ignore[attr-defined]
    loop._session_completion_tokens = 0  # type: ignore[attr-defined]
    loop._session_total_tokens = working_prompt  # type: ignore[attr-defined]


def _restore_token_baseline_from_record(loop: V6_1, record: SessionRecord) -> None:
    if record.session_total_tokens > 0 or record.last_total_tokens > 0:
        loop._last_usage = TokenUsage(  # type: ignore[attr-defined]
            prompt_tokens=max(0, int(record.last_prompt_tokens)),
            completion_tokens=max(0, int(record.last_completion_tokens)),
            total_tokens=max(0, int(record.last_total_tokens)),
            source=(record.last_usage_source or "persisted"),
        )
        loop._usage_seen = True  # type: ignore[attr-defined]
        loop._session_prompt_tokens = max(0, int(record.session_prompt_tokens))  # type: ignore[attr-defined]
        loop._session_completion_tokens = max(0, int(record.session_completion_tokens))  # type: ignore[attr-defined]
        loop._session_total_tokens = max(0, int(record.session_total_tokens))  # type: ignore[attr-defined]
        return
    _restore_token_baseline(loop)


def _restore_short_memory_state_from_record(loop: V6_1, record: SessionRecord) -> None:
    loop.hydrate_short_memory_compaction_state(
        session_tokens=max(0, int(record.last_compaction_session_tokens)),
        working_prompt_tokens=max(0, int(record.last_compaction_working_prompt_tokens)),
    )


def _reset_token_baseline(loop: V6_1) -> None:
    loop._last_usage = None  # type: ignore[attr-defined]
    loop._usage_seen = False  # type: ignore[attr-defined]
    loop._session_prompt_tokens = 0  # type: ignore[attr-defined]
    loop._session_completion_tokens = 0  # type: ignore[attr-defined]
    loop._session_total_tokens = 0  # type: ignore[attr-defined]


def _token_stats_line(
    loop: V6_1,
    *,
    turn_delta: dict[str, int] | None = None,
    pricing_input_per_million: float | None,
    pricing_output_per_million: float | None,
    pricing_currency: str,
) -> str:
    snap = _token_snapshot(loop)
    if not bool(snap.get("has_usage")):
        return "[TOKENS] no LLM call yet"
    window_prompt = int(snap.get("last_prompt_tokens", 0))
    window_completion = int(snap.get("last_completion_tokens", 0))
    window_total = int(snap.get("last_total_tokens", 0))
    session_prompt = int(snap.get("session_prompt_tokens", 0))
    session_completion = int(snap.get("session_completion_tokens", 0))
    session_total = int(snap.get("session_total_tokens", 0))
    source = str(snap.get("last_usage_source", "unknown"))
    window_cost = _compute_cost(
        prompt_tokens=window_prompt,
        completion_tokens=window_completion,
        input_per_million=pricing_input_per_million,
        output_per_million=pricing_output_per_million,
    )
    session_cost = _compute_cost(
        prompt_tokens=session_prompt,
        completion_tokens=session_completion,
        input_per_million=pricing_input_per_million,
        output_per_million=pricing_output_per_million,
    )

    line = (
        "[TOKENS] "
        f"source={source} | "
        f"window(prompt={window_prompt}, completion={window_completion}, total={window_total}) | "
        f"session(prompt={session_prompt}, completion={session_completion}, total={session_total})"
    )
    if turn_delta is not None:
        line += (
            " | "
            f"turn(prompt={turn_delta['prompt']}, completion={turn_delta['completion']}, total={turn_delta['total']})"
        )
    if window_cost is not None and session_cost is not None:
        line += (
            " | "
            f"cost(window={_currency_symbol(pricing_currency)}{window_cost:.6f}, "
            f"session={_currency_symbol(pricing_currency)}{session_cost:.6f}"
        )
        if turn_delta is not None:
            turn_cost = _compute_cost(
                prompt_tokens=int(turn_delta["prompt"]),
                completion_tokens=int(turn_delta["completion"]),
                input_per_million=pricing_input_per_million,
                output_per_million=pricing_output_per_million,
            )
            if turn_cost is not None:
                line += f", turn={_currency_symbol(pricing_currency)}{turn_cost:.6f}"
        line += ")"
    return line


def _activity_status_line(
    loop: V6_1,
    runtime_status: str,
    *,
    context_window_tokens: int,
    pricing_input_per_million: float | None,
    pricing_output_per_million: float | None,
    pricing_currency: str,
) -> str:
    snap = _token_snapshot(loop)
    st = loop.get_short_memory_state()
    estimated_working = int(st.get("working_prompt_tokens", 0))
    session_total = int(snap.get("session_total_tokens", 0))
    last_compaction_session_total = int(st.get("last_compaction_session_tokens", 0))
    last_prompt_tokens = int(snap.get("last_prompt_tokens", 0))
    usage_source = str(snap.get("last_usage_source", "none"))
    # Strict mode:
    # - Normal case: show provider prompt usage only.
    # - Right after compaction: show one-shot estimated working prompt so the
    #   UI can reflect the immediate "jump down".
    if last_compaction_session_total == session_total:
        window_used = estimated_working
    else:
        window_used = max(0, last_prompt_tokens)
    context_total = max(1, int(context_window_tokens))
    context_ratio = min(1.0, max(0.0, float(window_used) / float(context_total)))
    context_pct = int(round(context_ratio * 100))
    session_prompt = int(snap.get("session_prompt_tokens", 0))
    session_completion = int(snap.get("session_completion_tokens", 0))
    session_cost = _compute_cost(
        prompt_tokens=session_prompt,
        completion_tokens=session_completion,
        input_per_million=pricing_input_per_million,
        output_per_million=pricing_output_per_million,
    )
    return (
        f"Activity: 状态={runtime_status} | "
        f"context={context_pct}% ({window_used}/{context_total}) | "
        f"session(p={session_prompt} c={session_completion} t={session_total})"
        + (
            f" | cost={_currency_symbol(pricing_currency)}{session_cost:.6f}"
            if session_cost is not None
            else ""
        )
    )


def _top_level_commands() -> list[str]:
    return [
        "/quit",
        "/state",
        "/tokens",
        "/page",
        "/line",
        "/j",
        "/k",
        "/0",
        "/u",
        "/d",
        "/session",
        "/mcp",
        "/skill",
        "/memory",
    ]


def _session_subcommands() -> list[str]:
    return ["list", "new", "use"]


def _mcp_subcommands() -> list[str]:
    return ["list", "on", "off", "refresh"]


def _skill_subcommands() -> list[str]:
    return ["list", "use", "off"]


def _memory_subcommands() -> list[str]:
    return ["status", "summary", "compress", "auto", "threshold"]


def _build_completions(
    *,
    line: str,
    text: str,
    loop: V6_1,
    store: SessionStoreV6,
) -> list[str]:
    if not line.startswith("/"):
        return []

    stripped = line.lstrip()
    tokens = stripped.split()

    if (
        len(tokens) <= 1
        and not stripped.startswith("/session ")
        and not stripped.startswith("/mcp ")
        and not stripped.startswith("/skill ")
        and not stripped.startswith("/memory ")
    ):
        return [cmd for cmd in _top_level_commands() if cmd.startswith(text)]

    head = tokens[0] if tokens else ""

    if head == "/session":
        if len(tokens) == 1:
            return [sub for sub in _session_subcommands() if sub.startswith(text)]
        if len(tokens) == 2 and tokens[1] == "use":
            session_ids = [item.session_id for item in store.list_sessions()]
            return [sid for sid in session_ids if sid.startswith(text)]
        if len(tokens) == 2:
            return [sub for sub in _session_subcommands() if sub.startswith(text)]
        return []

    if head == "/page":
        page_sub = ["up", "down", "end"]
        if len(tokens) <= 2:
            return [sub for sub in page_sub if sub.startswith(text)]
        return []

    if head == "/line":
        line_sub = ["up", "down", "end"]
        if len(tokens) <= 2:
            return [sub for sub in line_sub if sub.startswith(text)]
        return []

    if head == "/mcp":
        if len(tokens) <= 2:
            return [sub for sub in _mcp_subcommands() if sub.startswith(text)]
        return []

    if head == "/skill":
        if len(tokens) == 1:
            return [sub for sub in _skill_subcommands() if sub.startswith(text)]
        if len(tokens) == 2 and tokens[1] == "use":
            names = loop.list_skills()
            return [name for name in names if name.startswith(text)]
        if len(tokens) == 2:
            return [sub for sub in _skill_subcommands() if sub.startswith(text)]
        return []

    if head == "/memory":
        if len(tokens) <= 2:
            return [sub for sub in _memory_subcommands() if sub.startswith(text)]
        if len(tokens) == 3 and tokens[1] == "auto":
            return [sub for sub in ["on", "off"] if sub.startswith(text)]
        return []

    return [cmd for cmd in _top_level_commands() if cmd.startswith(text)]


def _setup_readline(*, history_file: Path, loop: V6_1, store: SessionStoreV6) -> None:
    if readline is None:
        return

    history_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if history_file.exists():
            readline.read_history_file(str(history_file))
    except Exception:  # noqa: BLE001
        pass

    readline.set_history_length(5000)
    readline.parse_and_bind("tab: complete")

    def _completer(text: str, state: int) -> str | None:
        line = readline.get_line_buffer()
        options = _build_completions(line=line, text=text, loop=loop, store=store)
        if state < len(options):
            return options[state]
        return None

    readline.set_completer(_completer)

    def _save_history() -> None:
        try:
            readline.write_history_file(str(history_file))
        except Exception:  # noqa: BLE001
            return

    import atexit

    atexit.register(_save_history)


def _rehydrate_readline_history_from_messages(messages: List[Message], *, max_items: int = 50) -> int:
    if readline is None:
        return 0
    candidates: list[str] = []
    added = 0
    for msg in messages:
        if str(msg.get("role")) != "user":
            continue
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        # Keep user input shape for up/down-key recall; skip huge multi-line payloads.
        one_line = " ".join(content.split())
        if one_line:
            candidates.append(one_line)
    for item in candidates[-max_items:]:
        try:
            readline.add_history(item)
            added += 1
        except Exception:  # noqa: BLE001
            continue
    return added


def _saved_turn_badge() -> str:
    # Bright green badge so it's easy to spot in dialogue area.
    return "\033[1;32m[SAVED] 当前 turn 已保存\033[0m"


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="v6.1 CLI (session + short-memory compaction)")
    parser.add_argument("--config", default="./configs/default.json")
    parser.add_argument("--session", default=None, help="Restore an existing session id")
    parser.add_argument("--sessions-dir", default="./sessions", help="Session markdown directory")
    parser.add_argument("--history-file", default="./logs/cli_v6_1_history.txt", help="Readline history file")
    parser.add_argument(
        "--rehydrate-history",
        type=int,
        default=100,
        help="How many recent user inputs to rehydrate into readline history on session restore",
    )
    parser.add_argument(
        "--show-restored-messages",
        type=int,
        default=20,
        help="How many restored raw messages to print after /session use (default: 20, 0 to disable)",
    )
    parser.add_argument(
        "--stream",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable streaming text output from model (default: on)",
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--log-dir", default="./logs")
    parser.add_argument(
        "--ui-refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable fixed-area terminal refresh UI (default: on)",
    )
    parser.add_argument(
        "--memory-compact-ratio",
        type=float,
        default=None,
        help="Override memory compaction ratio (0,1], threshold = context_window * ratio",
    )
    parser.add_argument(
        "--memory-context-window",
        type=int,
        default=None,
        help="Override context window tokens used for threshold calculation",
    )
    parser.add_argument(
        "--memory-keep-recent-turns",
        type=int,
        default=4,
        help="Keep this many recent user turns in raw form when compacting",
    )
    parser.add_argument(
        "--memory-min-prefix-messages",
        type=int,
        default=8,
        help="Minimum old messages required before compaction can run",
    )
    parser.add_argument(
        "--memory-max-prefix-messages",
        type=int,
        default=120,
        help="Maximum old messages consumed in a single compaction",
    )
    parser.add_argument(
        "--memory-auto",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable automatic short-memory compaction",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    logger, log_path = create_session_logger(log_dir=args.log_dir, debug=args.debug)
    logger.info("startup loop=v6.1 model=%s provider=%s", cfg.model_name, cfg.provider)

    client = OpenAICompatClient(
        base_url=cfg.base_url,
        api_key_env=cfg.api_key_env,
        api_key=cfg.api_key,
        debug=args.debug,
        logger=logger,
    )
    mcp_manager = MCPManagerV4(cfg.mcp_servers or []) if cfg.mcp_servers else None
    ui = RefreshUI(enabled=bool(args.ui_refresh), model_name=cfg.model_name, log_path=log_path)
    turn_stream_state = {"started": False}
    turn_runtime: Dict[str, asyncio.Task[str] | None] = {"task": None}
    turn_interrupt_state = {"cancelled": False}
    turn_output_state = {"accepting": False}
    compact_ratio = float(args.memory_compact_ratio) if args.memory_compact_ratio is not None else float(cfg.memory_compact_ratio)
    if compact_ratio <= 0:
        compact_ratio = 0.8
    if compact_ratio > 1:
        compact_ratio = 1.0
    context_window_tokens = int(args.memory_context_window) if args.memory_context_window is not None else int(cfg.memory_context_window_tokens)
    context_window_tokens = max(1000, context_window_tokens)
    auto_threshold = max(1000, int(context_window_tokens * compact_ratio))
    pricing_input_per_million = cfg.pricing_input_per_million
    pricing_output_per_million = cfg.pricing_output_per_million
    pricing_currency = cfg.pricing_currency

    def _trace_to_ui(line: str) -> None:
        if not turn_output_state["accepting"]:
            return
        if ui.enabled:
            ui.add_dialogue("TOOL", line)

    def _status_to_ui(status: str) -> None:
        if ui.enabled:
            ui.set_runtime_status(status)
            _refresh_activity_status()
            ui.render()

    def _model_delta_to_ui(delta: str) -> None:
        if not turn_output_state["accepting"]:
            return
        if not ui.enabled:
            return
        turn_stream_state["started"] = True
        ui.stream_assistant_delta(delta)

    def _model_round_to_ui(response_text: str, metrics: Dict[str, int | str]) -> None:
        if not turn_output_state["accepting"]:
            return
        if not ui.enabled:
            return
        round_cost = _compute_cost(
            prompt_tokens=int(metrics.get("prompt_tokens", 0)),
            completion_tokens=int(metrics.get("completion_tokens", 0)),
            input_per_million=pricing_input_per_million,
            output_per_million=pricing_output_per_million,
        )
        suffix = (
            f"(usage: in={int(metrics.get('prompt_tokens', 0))}, "
            f"out={int(metrics.get('completion_tokens', 0))}, "
            f"total={int(metrics.get('total_tokens', 0))}; "
            f"latency={int(metrics.get('latency_ms', 0))}ms"
            + (f"; cost={_currency_symbol(pricing_currency)}{round_cost:.6f}" if round_cost is not None else "")
            + ")"
        )
        if turn_stream_state["started"]:
            ui.close_assistant_stream()
            ui.append_to_last_assistant(suffix)
        else:
            body = response_text or ""
            if body:
                ui.add_dialogue("ASSISTANT", f"{body}\n{suffix}")
            else:
                ui.add_dialogue("ASSISTANT", suffix)
        turn_stream_state["started"] = False
        _refresh_activity_status()

    loop = V6_1(
        client=client,
        model_name=cfg.model_name,
        timeout_seconds=cfg.timeout_seconds,
        max_tool_rounds=50,
        default_tool_cwd=".",
        mcp_manager=mcp_manager,
        mcp_enabled=bool(cfg.mcp_servers),
        skills_dir=cfg.skills_dir,
        stream_text=bool(args.stream),
        verbose=not bool(args.ui_refresh),
        trace_callback=_trace_to_ui if bool(args.ui_refresh) else None,
        status_callback=_status_to_ui if bool(args.ui_refresh) else None,
        model_delta_callback=_model_delta_to_ui if bool(args.ui_refresh) else None,
        model_round_callback=_model_round_to_ui if bool(args.ui_refresh) else None,
        interrupt_check=lambda: bool(turn_interrupt_state["cancelled"]),
        short_memory_config=ShortMemoryConfig(
            auto_enabled=bool(args.memory_auto),
            usage_threshold_tokens=auto_threshold,
            keep_recent_user_turns=max(1, int(args.memory_keep_recent_turns)),
            min_prefix_messages=max(4, int(args.memory_min_prefix_messages)),
            max_prefix_messages=max(20, int(args.memory_max_prefix_messages)),
        ),
    )

    store = SessionStoreV6(args.sessions_dir)
    if args.session:
        record = store.load(args.session)
        loop.state.messages = list(record.messages)
        loop.set_raw_messages(list(record.messages))
        loop.hydrate_short_memory_summary(record.summary)
        _restore_short_memory_state_from_record(loop, record)
        _restore_token_baseline_from_record(loop, record)
    else:
        record = store.create(model_name=cfg.model_name, loop_version="v6.1", persist=False)
        _reset_token_baseline(loop)

    _setup_readline(history_file=Path(args.history_file), loop=loop, store=store)
    _rehydrate_readline_history_from_messages(
        loop.state.messages,
        max_items=max(0, int(args.rehydrate_history)),
    )

    prompt_session = _build_prompt_session(ui) if ui.enabled else None
    ui.set_session(record.session_id, str(record.file_path))

    def _refresh_activity_status() -> None:
        ui.set_activity_status(
            _activity_status_line(
                loop,
                ui.runtime_status,
                context_window_tokens=context_window_tokens,
                pricing_input_per_million=pricing_input_per_million,
                pricing_output_per_million=pricing_output_per_million,
                pricing_currency=pricing_currency,
            ),
        )

    _refresh_activity_status()
    if ui.enabled and prompt_session is None:
        ui.set_activity_status(f"{ui.activity_status} | prompt_toolkit missing")
    if not ui.enabled:
        ui.add(f"agent-loop suite started | loop=v6.1 | model={cfg.model_name}")
        ui.add("Session Commands: /session list|new|use <id>")
        ui.add("MCP Commands: /mcp list|on|off|refresh")
        ui.add("Skill Commands: /skill list|use <name>|off")
        ui.add("Memory Commands: /memory status|summary|compress|auto on|off|threshold <n>")

    previous_sigint_handler = signal.getsignal(signal.SIGINT)
    signal_handler_installed = False
    asyncio_sigint_installed = False
    running_loop = asyncio.get_running_loop()

    def _sigint_handler(signum: int, frame: object) -> None:  # noqa: ARG001
        running = turn_runtime["task"]
        if running is not None and not running.done():
            turn_interrupt_state["cancelled"] = True
            running.cancel()
            return
        raise KeyboardInterrupt

    def _sigint_async_handler() -> None:
        running = turn_runtime["task"]
        if running is not None and not running.done():
            turn_interrupt_state["cancelled"] = True
            running.cancel()
            return
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, _sigint_handler)
        signal_handler_installed = True
    except Exception:  # noqa: BLE001
        signal_handler_installed = False

    try:
        running_loop.add_signal_handler(signal.SIGINT, _sigint_async_handler)
        asyncio_sigint_installed = True
    except NotImplementedError:
        asyncio_sigint_installed = False
    except RuntimeError:
        asyncio_sigint_installed = False

    try:
        while True:
            try:
                if prompt_session is not None:
                    if ui.enabled:
                        ui.render()
                    user_input = (await prompt_session.prompt_async("> ")).strip()
                else:
                    user_input = (await ui.read_line("> ")).strip()
            except KeyboardInterrupt:
                ui.add("Interrupted (^C). Exiting...")
                return 130
            except EOFError:
                return 0
            if not user_input:
                continue
            if ui.enabled and ui.output_lines:
                ui.clear_output()
            if user_input == "/k":
                ui.page_up()
                continue
            if user_input == "/j":
                ui.page_down()
                continue
            if user_input == "/0":
                ui.page_end()
                continue
            if user_input == "/u":
                ui.line_up()
                continue
            if user_input == "/d":
                ui.line_down()
                continue
            if user_input == "/quit":
                return 0
            if user_input == "/state":
                ui.add(json.dumps(loop.get_messages(), ensure_ascii=False, indent=2))
                continue
            if user_input == "/tokens":
                token_line = _token_stats_line(
                    loop,
                    pricing_input_per_million=pricing_input_per_million,
                    pricing_output_per_million=pricing_output_per_million,
                    pricing_currency=pricing_currency,
                )
                ui.set_token_line(token_line)
                ui.add(token_line)
                _refresh_activity_status()
                continue
            if user_input.startswith("/page"):
                action = user_input[5:].strip()
                if action == "up":
                    ui.page_up()
                    continue
                if action == "down":
                    ui.page_down()
                    continue
                if action == "end":
                    ui.page_end()
                    continue
                ui.add("Usage: /page up|down|end (快捷: /k /j /0)")
                continue

            if user_input.startswith("/line"):
                action = user_input[5:].strip()
                if action == "up":
                    ui.line_up()
                    continue
                if action == "down":
                    ui.line_down()
                    continue
                if action == "end":
                    ui.line_end()
                    continue
                ui.add("Usage: /line up|down|end (快捷: /u /d)")
                continue

            if user_input.startswith("/session "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    _persist_if_needed(
                        store,
                        record,
                        loop.get_raw_messages(),
                        memory_summary=str(loop.get_short_memory_state().get("last_compaction_summary", "")),
                        token_snapshot=_token_snapshot(loop),
                        short_memory_state=loop.get_short_memory_state(),
                    )
                    records = store.list_sessions()
                    if not records:
                        ui.add("(no sessions)")
                    else:
                        shown = records[:50]
                        header = f"showing {len(shown)}/{len(records)} sessions"
                        ui.add("\n".join([header, *[_session_brief_line(item) for item in shown]]))
                    continue
                if action == "new":
                    _persist_if_needed(
                        store,
                        record,
                        loop.get_raw_messages(),
                        memory_summary=str(loop.get_short_memory_state().get("last_compaction_summary", "")),
                        token_snapshot=_token_snapshot(loop),
                        short_memory_state=loop.get_short_memory_state(),
                    )
                    record = store.create(model_name=cfg.model_name, loop_version="v6.1", persist=False)
                    loop.state.messages = []
                    loop.set_raw_messages([])
                    loop.hydrate_short_memory_summary("")
                    loop.hydrate_short_memory_compaction_state(session_tokens=0, working_prompt_tokens=0)
                    _reset_token_baseline(loop)
                    if ui.enabled:
                        ui.hydrate_dialogue_from_messages([], max_messages=16)
                        ui.clear_output()
                    ui.set_session(record.session_id, str(record.file_path))
                    _refresh_activity_status()
                    ui.add(f"Switched to new session: {record.session_id}")
                    continue
                if action.startswith("use "):
                    sid = action.split(" ", 1)[1].strip()
                    if not sid:
                        ui.add("Usage: /session use <id>")
                        continue
                    _persist_if_needed(
                        store,
                        record,
                        loop.get_raw_messages(),
                        memory_summary=str(loop.get_short_memory_state().get("last_compaction_summary", "")),
                        token_snapshot=_token_snapshot(loop),
                        short_memory_state=loop.get_short_memory_state(),
                    )
                    record = store.load(sid)
                    loop.state.messages = list(record.messages)
                    loop.set_raw_messages(list(record.messages))
                    loop.hydrate_short_memory_summary(record.summary)
                    _restore_short_memory_state_from_record(loop, record)
                    _restore_token_baseline_from_record(loop, record)
                    ui.set_session(record.session_id, str(record.file_path))
                    _refresh_activity_status()
                    if ui.enabled:
                        ui.clear_output()
                        ui.hydrate_dialogue_from_messages(loop.state.messages, max_messages=16)
                    rehydrated = _rehydrate_readline_history_from_messages(
                        loop.state.messages,
                        max_items=max(0, int(args.rehydrate_history)),
                    )
                    ui.add(
                        f"Restored session: {record.session_id} | "
                        f"loaded_messages={len(record.messages)} | "
                        f"rehydrated_history={rehydrated}"
                    )
                    ui.add(f"last_user: {_latest_by_role(loop.state.messages, 'user')}")
                    ui.add(f"last_assistant: {_latest_by_role(loop.state.messages, 'assistant')}")
                    for line in _restored_preview_lines(loop.state.messages, max_pairs=4):
                        ui.add(line)
                    for line in _raw_messages_lines(
                        loop.state.messages,
                        limit=max(0, int(args.show_restored_messages)),
                    ):
                        ui.add(line)
                    continue
                ui.add("Usage: /session list|new|use <id>")
                continue

            if user_input.startswith("/memory "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "status":
                    st = loop.get_short_memory_state()
                    session_total = int(st["session_total_tokens"])
                    working_prompt = int(st.get("working_prompt_tokens", 0))
                    context_pct = int(round(min(1.0, float(working_prompt) / float(max(1, context_window_tokens))) * 100))
                    ui.add(
                        "[MEMORY] "
                        f"auto={st['auto_enabled']} | threshold={st['usage_threshold_tokens']} | "
                        f"ratio={compact_ratio:.2f} | context_window={context_window_tokens} | "
                        f"context_used={working_prompt} ({context_pct}%) | "
                        f"raw_msgs={st['raw_message_count']} | working_msgs={st['working_message_count']} | "
                        f"keep_recent_turns={st['keep_recent_user_turns']} | "
                        f"session_total={session_total} | "
                        f"last_compaction_session_total={st['last_compaction_session_tokens']} | "
                        f"last_compaction_working_prompt={st['last_compaction_working_prompt_tokens']}",
                    )
                    summary_text = str(st.get("last_compaction_summary", "")).strip()
                    ui.add_dialogue("MEMORY", "[summary]")
                    ui.add_dialogue("MEMORY", summary_text if summary_text else "(empty)")
                    continue
                if action == "summary":
                    summary = str(loop.get_short_memory_state().get("last_compaction_summary", "")).strip()
                    if not summary:
                        ui.add("(no compaction summary yet)")
                    else:
                        ui.add(summary)
                    continue
                if action == "compress":
                    before_working = int(loop.get_short_memory_state().get("working_prompt_tokens", 0))
                    result = await loop.compress_short_memory(reason="manual")
                    if bool(result.get("performed")):
                        after_working = int(loop.get_short_memory_state().get("working_prompt_tokens", 0))
                        before_pct = int(round(min(1.0, float(before_working) / float(max(1, context_window_tokens))) * 100))
                        after_pct = int(round(min(1.0, float(after_working) / float(max(1, context_window_tokens))) * 100))
                        ui.add(
                            "[MEMORY] compressed | "
                            f"covered={result.get('covered_messages', 0)} | "
                            f"remaining={result.get('remaining_messages', len(loop.state.messages))} | "
                            f"context_used: {before_working} ({before_pct}%) -> {after_working} ({after_pct}%)",
                        )
                        summary_text = str(loop.get_short_memory_state().get("last_compaction_summary", "")).strip()
                        ui.add_dialogue("MEMORY", "[summary]")
                        ui.add_dialogue("MEMORY", summary_text if summary_text else "(empty)")
                        _refresh_activity_status()
                        _persist_if_needed(
                            store,
                            record,
                            loop.get_raw_messages(),
                            memory_summary=str(loop.get_short_memory_state().get("last_compaction_summary", "")),
                            token_snapshot=_token_snapshot(loop),
                            short_memory_state=loop.get_short_memory_state(),
                        )
                    else:
                        ui.add(f"[MEMORY] skipped: {result.get('message', 'unknown reason')}")
                    continue
                if action.startswith("auto "):
                    value = action.split(" ", 1)[1].strip().lower()
                    if value in {"on", "off"}:
                        loop.set_short_memory_auto(value == "on")
                        ui.add(f"[MEMORY] auto={value}")
                    else:
                        ui.add("Usage: /memory auto on|off")
                    continue
                if action.startswith("threshold "):
                    value = action.split(" ", 1)[1].strip()
                    try:
                        threshold = int(value)
                    except ValueError:
                        ui.add("Usage: /memory threshold <int>")
                        continue
                    loop.set_short_memory_threshold(threshold)
                    ui.add(f"[MEMORY] threshold={max(1000, threshold)}")
                    continue
                ui.add("Usage: /memory status|summary|compress|auto on|off|threshold <n>")
                continue

            if user_input.startswith("/mcp "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    names = loop.list_mcp_tools()
                    ui.add("\n".join(names) if names else "(no mcp tools)")
                    continue
                if action == "on":
                    await loop.set_mcp_enabled(True)
                    ui.add("MCP enabled")
                    continue
                if action == "off":
                    await loop.set_mcp_enabled(False)
                    ui.add("MCP disabled")
                    continue
                if action == "refresh":
                    await loop.refresh_mcp_tools()
                    ui.add("MCP tools refreshed")
                    continue
                ui.add("Usage: /mcp list|on|off|refresh")
                continue

            if user_input.startswith("/skill "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    names = loop.list_skills()
                    ui.add("\n".join(names) if names else "(no skills)")
                    continue
                if action.startswith("use "):
                    name = action.split(" ", 1)[1].strip()
                    if not name:
                        ui.add("Usage: /skill use <name>")
                        continue
                    if loop.use_skill(name):
                        ui.add(f"Skill enabled: {name}")
                    else:
                        ui.add(f"Skill not found: {name}")
                    continue
                if action == "off":
                    loop.disable_skill()
                    ui.add("Skill disabled")
                    continue
                ui.add("Usage: /skill list|use <name>|off")
                continue

            if user_input.startswith("/"):
                ui.add(
                    "Unknown command. Built-in commands: "
                    "/quit, /state, /tokens, /session list|new|use <id>, "
                    "/mcp list|on|off|refresh, /skill list|use <name>|off, "
                    "/memory status|summary|compress|auto on|off|threshold <n>",
                )
                continue

            ui.add_dialogue("USER", user_input)
            turn_stream_state["started"] = False
            ui.close_assistant_stream()
            before = _token_snapshot(loop)
            try:
                turn_interrupt_state["cancelled"] = False
                turn_output_state["accepting"] = True
                turn_runtime["task"] = asyncio.create_task(loop.run_turn(user_input))
                text = await turn_runtime["task"]
            except asyncio.CancelledError:
                if turn_interrupt_state["cancelled"]:
                    turn_stream_state["started"] = False
                    turn_output_state["accepting"] = False
                    ui.close_assistant_stream()
                    ui.set_runtime_status("等待输入")
                    _refresh_activity_status()
                    ui.add("Interrupted current turn (^C)")
                    continue
                raise
            except InterruptedError:
                if turn_interrupt_state["cancelled"]:
                    turn_stream_state["started"] = False
                    turn_output_state["accepting"] = False
                    ui.close_assistant_stream()
                    ui.set_runtime_status("等待输入")
                    _refresh_activity_status()
                    ui.add("Interrupted current turn (^C)")
                    continue
                raise
            except KeyboardInterrupt:
                current = turn_runtime["task"]
                if current is not None and not current.done():
                    turn_interrupt_state["cancelled"] = True
                    current.cancel()
                    turn_stream_state["started"] = False
                    turn_output_state["accepting"] = False
                    ui.close_assistant_stream()
                    ui.set_runtime_status("等待输入")
                    _refresh_activity_status()
                    ui.add("Interrupted current turn (^C)")
                    continue
                ui.add("Interrupted (^C). Exiting...")
                return 130
            finally:
                turn_runtime["task"] = None
                turn_interrupt_state["cancelled"] = False
                turn_output_state["accepting"] = False
            ui.close_assistant_stream()
            if text and not ui.enabled:
                ui.add_dialogue("ASSISTANT", text)
            after = _token_snapshot(loop)
            turn_delta = {
                "prompt": int(after.get("session_prompt_tokens", 0)) - int(before.get("session_prompt_tokens", 0)),
                "completion": int(after.get("session_completion_tokens", 0)) - int(before.get("session_completion_tokens", 0)),
                "total": int(after.get("session_total_tokens", 0)) - int(before.get("session_total_tokens", 0)),
            }
            token_line = _token_stats_line(
                loop,
                turn_delta=turn_delta,
                pricing_input_per_million=pricing_input_per_million,
                pricing_output_per_million=pricing_output_per_million,
                pricing_currency=pricing_currency,
            )
            ui.set_token_line(token_line)
            _refresh_activity_status()
            if not ui.enabled:
                ui.add(token_line)
            auto_compact = await loop.maybe_auto_compress_short_memory()
            if auto_compact and bool(auto_compact.get("performed")):
                before_working = int(auto_compact.get("before_working_prompt_tokens", 0) or 0)
                after_working = int(loop.get_short_memory_state().get("working_prompt_tokens", 0))
                before_pct = int(round(min(1.0, float(before_working) / float(max(1, context_window_tokens))) * 100))
                after_pct = int(round(min(1.0, float(after_working) / float(max(1, context_window_tokens))) * 100))
                ui.add(
                    "[MEMORY] auto-compressed | "
                    f"covered={auto_compact.get('covered_messages', 0)} | "
                    f"remaining={auto_compact.get('remaining_messages', len(loop.state.messages))} | "
                    f"context_used: {before_working} ({before_pct}%) -> {after_working} ({after_pct}%)",
                )
                summary_text = str(loop.get_short_memory_state().get("last_compaction_summary", "")).strip()
                ui.add_dialogue("MEMORY", "[summary]")
                ui.add_dialogue("MEMORY", summary_text if summary_text else "(empty)")
                _refresh_activity_status()
            saved = _persist_if_needed(
                store,
                record,
                loop.get_raw_messages(),
                memory_summary=str(loop.get_short_memory_state().get("last_compaction_summary", "")),
                token_snapshot=_token_snapshot(loop),
                short_memory_state=loop.get_short_memory_state(),
            )
            if saved:
                ui.add_dialogue("SYSTEM", _saved_turn_badge())
    finally:
        if asyncio_sigint_installed:
            try:
                running_loop.remove_signal_handler(signal.SIGINT)
            except Exception:  # noqa: BLE001
                pass
        if signal_handler_installed:
            signal.signal(signal.SIGINT, previous_sigint_handler)
        # v4 MCP manager has no long-lived connections to close.
        pass


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted. Bye.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
