#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import textwrap
from typing import Any, List

from core.client import OpenAICompatClient
from core.config import load_config
from core.logging_utils import create_session_logger
from core.mcp_client import MCPManager as MCPManagerV4
from core.session_store_v6 import SessionRecord, SessionStoreV6
from core.types import Message
from loops.agent_loop_v5_skill_tools import V5SkillToolsLoop

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
        self.activity_status = "Activity: window(p=0 c=0 t=0) | session(p=0 c=0 t=0) | source=none"
        self.dialogue: list[tuple[str, str]] = []
        self.output_lines: list[str] = []
        self.dialogue_page = 0
        self._last_dialogue_page_total = 1

    def set_session(self, session_id: str, session_file: str) -> None:
        self.session_id = session_id
        self.session_file = session_file

    def set_token_line(self, line: str) -> None:
        self.token_line = line

    def set_activity_status(self, line: str) -> None:
        self.activity_status = line

    def add(self, text: str) -> None:
        if self.enabled:
            lines = text.splitlines() if text else [""]
            self.output_lines = lines[:200]
            self.render()
            return
        print(text)

    def add_dialogue(self, role: str, text: str) -> None:
        self.dialogue.append((role, text if text else ""))
        self.dialogue = self.dialogue[-60:]
        self.dialogue_page = 0
        if self.enabled:
            self.render()
        else:
            print(f"[{role}] {text}")

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
        if self.enabled:
            self.render()

    def page_up(self) -> None:
        self.dialogue_page = min(self.dialogue_page + 1, max(0, self._last_dialogue_page_total - 1))
        if self.enabled:
            self.render()

    def page_down(self) -> None:
        self.dialogue_page = max(0, self.dialogue_page - 1)
        if self.enabled:
            self.render()

    def page_end(self) -> None:
        self.dialogue_page = 0
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

        start_from_end = self.dialogue_page * page_size
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
            f"agent-loop v6 | model={self.model_name}",
            f"log: {self.log_path}",
            f"session: {self.session_id} ({self.session_file})",
            "Commands: /quit /state /tokens /session /mcp /skill",
        ]
        has_output = any(line.strip() for line in self.output_lines)
        fixed_rows = len(header_lines) + 4  # top sep + middle title + bottom sep + activity line
        content_rows = max(8, total_rows - fixed_rows - 1)  # keep one row for prompt

        if has_output:
            # Shared middle area: Dialogue + split line + Output
            output_rows = min(6, max(3, content_rows // 3))
            dialogue_rows = max(4, content_rows - output_rows - 1)
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
            "(Alt+K prev, Alt+J next, Alt+0 end)",
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


def _persist_if_needed(store: SessionStoreV6, record: SessionRecord, messages: List[Message]) -> None:
    if not _has_user_messages(messages):
        return
    record.messages = list(messages)
    record.title = _auto_title(record.messages)
    record.summary = ""
    store.save(record)


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


def _token_snapshot(loop: V5SkillToolsLoop) -> dict[str, int | bool]:
    return loop.get_token_usage_snapshot()


def _token_stats_line(loop: V5SkillToolsLoop, *, turn_delta: dict[str, int] | None = None) -> str:
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
    return line


def _activity_status_line(loop: V5SkillToolsLoop) -> str:
    snap = _token_snapshot(loop)
    return (
        "Activity: "
        f"window(p={int(snap.get('last_prompt_tokens', 0))} "
        f"c={int(snap.get('last_completion_tokens', 0))} "
        f"t={int(snap.get('last_total_tokens', 0))}) | "
        f"session(p={int(snap.get('session_prompt_tokens', 0))} "
        f"c={int(snap.get('session_completion_tokens', 0))} "
        f"t={int(snap.get('session_total_tokens', 0))}) | "
        f"source={str(snap.get('last_usage_source', 'none'))}"
    )


def _top_level_commands() -> list[str]:
    return ["/quit", "/state", "/tokens", "/page", "/j", "/k", "/0", "/session", "/mcp", "/skill"]


def _session_subcommands() -> list[str]:
    return ["list", "new", "use"]


def _mcp_subcommands() -> list[str]:
    return ["list", "on", "off", "refresh"]


def _skill_subcommands() -> list[str]:
    return ["list", "use", "off"]


def _build_completions(
    *,
    line: str,
    text: str,
    loop: V5SkillToolsLoop,
    store: SessionStoreV6,
) -> list[str]:
    if not line.startswith("/"):
        return []

    stripped = line.lstrip()
    tokens = stripped.split()

    if len(tokens) <= 1 and not stripped.startswith("/session ") and not stripped.startswith("/mcp ") and not stripped.startswith("/skill "):
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

    return [cmd for cmd in _top_level_commands() if cmd.startswith(text)]


def _setup_readline(*, history_file: Path, loop: V5SkillToolsLoop, store: SessionStoreV6) -> None:
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


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="v6 CLI (session-first, markdown persistence)")
    parser.add_argument("--config", default="./configs/default.json")
    parser.add_argument("--session", default=None, help="Restore an existing session id")
    parser.add_argument("--sessions-dir", default="./sessions", help="Session markdown directory")
    parser.add_argument("--history-file", default="./logs/cli_v6_history.txt", help="Readline history file")
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
        default=False,
        help="Enable fixed-area terminal refresh UI (default: off)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    logger, log_path = create_session_logger(log_dir=args.log_dir, debug=args.debug)
    logger.info("startup loop=v6 model=%s provider=%s", cfg.model_name, cfg.provider)

    client = OpenAICompatClient(
        base_url=cfg.base_url,
        api_key_env=cfg.api_key_env,
        api_key=cfg.api_key,
        debug=args.debug,
        logger=logger,
    )
    mcp_manager = MCPManagerV4(cfg.mcp_servers or []) if cfg.mcp_servers else None
    ui = RefreshUI(enabled=bool(args.ui_refresh), model_name=cfg.model_name, log_path=log_path)

    def _trace_to_ui(line: str) -> None:
        if ui.enabled:
            ui.add_dialogue("TOOL", line)

    loop = V5SkillToolsLoop(
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
    )

    store = SessionStoreV6(args.sessions_dir)
    if args.session:
        record = store.load(args.session)
        loop.state.messages = list(record.messages)
    else:
        record = store.create(model_name=cfg.model_name, loop_version="v6", persist=False)

    _setup_readline(history_file=Path(args.history_file), loop=loop, store=store)
    _rehydrate_readline_history_from_messages(
        loop.state.messages,
        max_items=max(0, int(args.rehydrate_history)),
    )

    prompt_session = _build_prompt_session(ui) if ui.enabled else None
    ui.set_session(record.session_id, str(record.file_path))

    def _refresh_activity_status() -> None:
        ui.set_activity_status(_activity_status_line(loop))

    _refresh_activity_status()
    if ui.enabled and prompt_session is None:
        ui.set_activity_status(f"{ui.activity_status} | prompt_toolkit missing")
    if not ui.enabled:
        ui.add(f"agent-loop suite started | loop=v6 | model={cfg.model_name}")
        ui.add("Session Commands: /session list|new|use <id>")
        ui.add("MCP Commands: /mcp list|on|off|refresh")
        ui.add("Skill Commands: /skill list|use <name>|off")

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
            if user_input == "/k":
                ui.page_up()
                continue
            if user_input == "/j":
                ui.page_down()
                continue
            if user_input == "/0":
                ui.page_end()
                continue
            if user_input == "/quit":
                return 0
            if user_input == "/state":
                ui.add(json.dumps(loop.get_messages(), ensure_ascii=False, indent=2))
                continue
            if user_input == "/tokens":
                token_line = _token_stats_line(loop)
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

            if user_input.startswith("/session "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    _persist_if_needed(store, record, loop.state.messages)
                    records = [item for item in store.list_sessions() if _has_user_messages(item.messages)]
                    if not records:
                        ui.add("(no sessions)")
                    else:
                        ui.add("\n".join(_session_brief_line(item) for item in records))
                    continue
                if action == "new":
                    _persist_if_needed(store, record, loop.state.messages)
                    record = store.create(model_name=cfg.model_name, loop_version="v6", persist=False)
                    loop.state.messages = []
                    ui.set_session(record.session_id, str(record.file_path))
                    _refresh_activity_status()
                    ui.add(f"Switched to new session: {record.session_id}")
                    continue
                if action.startswith("use "):
                    sid = action.split(" ", 1)[1].strip()
                    if not sid:
                        ui.add("Usage: /session use <id>")
                        continue
                    _persist_if_needed(store, record, loop.state.messages)
                    record = store.load(sid)
                    loop.state.messages = list(record.messages)
                    ui.set_session(record.session_id, str(record.file_path))
                    _refresh_activity_status()
                    if ui.enabled:
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
                    "/mcp list|on|off|refresh, /skill list|use <name>|off",
                )
                continue

            ui.add_dialogue("USER", user_input)
            before = _token_snapshot(loop)
            try:
                text = await loop.run_turn(user_input)
            except KeyboardInterrupt:
                ui.add("Interrupted (^C). Exiting...")
                return 130
            if text:
                ui.add_dialogue("ASSISTANT", text)
            after = _token_snapshot(loop)
            turn_delta = {
                "prompt": int(after.get("session_prompt_tokens", 0)) - int(before.get("session_prompt_tokens", 0)),
                "completion": int(after.get("session_completion_tokens", 0)) - int(before.get("session_completion_tokens", 0)),
                "total": int(after.get("session_total_tokens", 0)) - int(before.get("session_total_tokens", 0)),
            }
            token_line = _token_stats_line(loop, turn_delta=turn_delta)
            ui.set_token_line(token_line)
            _refresh_activity_status()
            token_suffix = (
                f"(usage: in={int(after.get('last_prompt_tokens', 0))}, "
                f"out={int(after.get('last_completion_tokens', 0))}, "
                f"total={int(after.get('last_total_tokens', 0))}; "
                f"latency={int(after.get('last_latency_ms', 0))}ms)"
            )
            if ui.dialogue and ui.dialogue[-1][0] == "ASSISTANT":
                role, content = ui.dialogue[-1]
                ui.dialogue[-1] = (role, f"{content}\n{token_suffix}")
                if ui.enabled:
                    ui.render()
            else:
                ui.add_dialogue("ASSISTANT", token_suffix)
            _persist_if_needed(store, record, loop.state.messages)
    finally:
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
