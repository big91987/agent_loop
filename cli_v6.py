#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import List

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


async def _read_line(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


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


def _print_session_brief(record: SessionRecord) -> None:
    title = (record.title or "Untitled Session").replace("\n", " ").strip()
    title_short = title[:60] + ("..." if len(title) > 60 else "")
    print(
        f"{record.session_id} | updated={record.updated_at} | "
        f"msgs={len(record.messages)} | {record.file_path.name} | title={title_short}",
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


def _print_raw_messages(messages: List[Message], *, limit: int) -> None:
    if limit <= 0 or not messages:
        return
    tail = messages[-limit:]
    print("")
    print(f"Restored raw messages (last {len(tail)}):")
    for idx, msg in enumerate(tail, start=1):
        role = str(msg.get("role", "unknown"))
        text = _message_content_to_text(msg.get("content", ""))
        print(f"[{idx}] {role}:")
        print(text)
        print("")


def _token_snapshot(loop: V5SkillToolsLoop) -> dict[str, int | bool]:
    return loop.get_token_usage_snapshot()


def _print_token_stats(loop: V5SkillToolsLoop, *, turn_delta: dict[str, int] | None = None) -> None:
    snap = _token_snapshot(loop)
    if not bool(snap.get("has_usage")):
        print("[TOKENS] no LLM call yet")
        return
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
    print(line)


def _top_level_commands() -> list[str]:
    return ["/quit", "/state", "/tokens", "/session", "/mcp", "/skill"]


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

    print(f"agent-loop suite started | loop=v6 | model={cfg.model_name}")
    print(f"log file: {log_path}")
    print(f"session: {record.session_id} ({record.file_path})")
    print("Commands: /quit, /state, /tokens")
    print("Session Commands: /session list|new|use <id>")
    print("MCP Commands: /mcp list|on|off|refresh")
    print("Skill Commands: /skill list|use <name>|off")

    try:
        while True:
            user_input = (await _read_line("> ")).strip()
            if not user_input:
                continue
            if user_input == "/quit":
                return 0
            if user_input == "/state":
                print(json.dumps(loop.get_messages(), ensure_ascii=False, indent=2))
                continue
            if user_input == "/tokens":
                _print_token_stats(loop)
                continue

            if user_input.startswith("/session "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    _persist_if_needed(store, record, loop.state.messages)
                    records = [item for item in store.list_sessions() if _has_user_messages(item.messages)]
                    if not records:
                        print("(no sessions)")
                    for item in records:
                        _print_session_brief(item)
                    continue
                if action == "new":
                    _persist_if_needed(store, record, loop.state.messages)
                    record = store.create(model_name=cfg.model_name, loop_version="v6", persist=False)
                    loop.state.messages = []
                    print(f"Switched to new session: {record.session_id}")
                    continue
                if action.startswith("use "):
                    sid = action.split(" ", 1)[1].strip()
                    if not sid:
                        print("Usage: /session use <id>")
                        continue
                    _persist_if_needed(store, record, loop.state.messages)
                    record = store.load(sid)
                    loop.state.messages = list(record.messages)
                    rehydrated = _rehydrate_readline_history_from_messages(
                        loop.state.messages,
                        max_items=max(0, int(args.rehydrate_history)),
                    )
                    print(
                        f"Restored session: {record.session_id} | "
                        f"loaded_messages={len(record.messages)} | "
                        f"rehydrated_history={rehydrated}",
                    )
                    print(f"last_user: {_latest_by_role(loop.state.messages, 'user')}")
                    print(f"last_assistant: {_latest_by_role(loop.state.messages, 'assistant')}")
                    _print_raw_messages(
                        loop.state.messages,
                        limit=max(0, int(args.show_restored_messages)),
                    )
                    continue
                print("Usage: /session list|new|use <id>")
                continue

            if user_input.startswith("/mcp "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    names = loop.list_mcp_tools()
                    print("\n".join(names) if names else "(no mcp tools)")
                    continue
                if action == "on":
                    await loop.set_mcp_enabled(True)
                    print("MCP enabled")
                    continue
                if action == "off":
                    await loop.set_mcp_enabled(False)
                    print("MCP disabled")
                    continue
                if action == "refresh":
                    await loop.refresh_mcp_tools()
                    print("MCP tools refreshed")
                    continue
                print("Usage: /mcp list|on|off|refresh")
                continue

            if user_input.startswith("/skill "):
                action = user_input.split(" ", 1)[1].strip()
                if action == "list":
                    names = loop.list_skills()
                    print("\n".join(names) if names else "(no skills)")
                    continue
                if action.startswith("use "):
                    name = action.split(" ", 1)[1].strip()
                    if not name:
                        print("Usage: /skill use <name>")
                        continue
                    if loop.use_skill(name):
                        print(f"Skill enabled: {name}")
                    else:
                        print(f"Skill not found: {name}")
                    continue
                if action == "off":
                    loop.disable_skill()
                    print("Skill disabled")
                    continue
                print("Usage: /skill list|use <name>|off")
                continue

            before = _token_snapshot(loop)
            text = await loop.run_turn(user_input)
            print(text)
            after = _token_snapshot(loop)
            turn_delta = {
                "prompt": int(after.get("session_prompt_tokens", 0)) - int(before.get("session_prompt_tokens", 0)),
                "completion": int(after.get("session_completion_tokens", 0)) - int(before.get("session_completion_tokens", 0)),
                "total": int(after.get("session_total_tokens", 0)) - int(before.get("session_total_tokens", 0)),
            }
            _print_token_stats(loop, turn_delta=turn_delta)
            _persist_if_needed(store, record, loop.state.messages)
    finally:
        # v4 MCP manager has no long-lived connections to close.
        pass


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
