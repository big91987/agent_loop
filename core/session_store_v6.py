from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from .types import Message


_SESSION_META_START = "<!-- AGENT_LOOP_V6_META"
_SESSION_META_END = "-->"
_MESSAGES_START = "<!-- AGENT_LOOP_V6_MESSAGES_START -->"
_MESSAGES_END = "<!-- AGENT_LOOP_V6_MESSAGES_END -->"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _escape_md(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class SessionRecord:
    session_id: str
    created_at: str
    updated_at: str
    model_name: str
    loop_version: str
    title: str
    summary: str
    messages: List[Message]
    file_path: Path
    session_prompt_tokens: int = 0
    session_completion_tokens: int = 0
    session_total_tokens: int = 0
    last_prompt_tokens: int = 0
    last_completion_tokens: int = 0
    last_total_tokens: int = 0
    last_usage_source: str = "none"


class SessionStoreV6:
    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, *, model_name: str, loop_version: str, persist: bool = True) -> SessionRecord:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        session_id = f"{ts}_{uuid4().hex[:6]}"
        now = _now_iso()
        record = SessionRecord(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            model_name=model_name,
            loop_version=loop_version,
            title="New Session",
            summary="",
            messages=[],
            file_path=self.root / f"{session_id}.md",
            session_prompt_tokens=0,
            session_completion_tokens=0,
            session_total_tokens=0,
            last_prompt_tokens=0,
            last_completion_tokens=0,
            last_total_tokens=0,
            last_usage_source="none",
        )
        if persist:
            self.save(record)
        return record

    def list_sessions(self) -> List[SessionRecord]:
        records: List[SessionRecord] = []
        for path in self.root.glob("*.md"):
            try:
                record = self.load(path.stem)
                if not self._has_meaningful_user_message(record.messages):
                    # Keep sessions directory clean: empty sessions should not be persisted.
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
                records.append(record)
            except Exception:  # noqa: BLE001
                continue
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records

    def load(self, session_id: str) -> SessionRecord:
        path = self.root / f"{session_id}.md"
        raw = path.read_text(encoding="utf-8")
        meta = self._parse_meta(raw)
        messages = self._parse_messages(raw)
        summary = self._parse_summary(raw)
        title = self._parse_title(raw)
        return SessionRecord(
            session_id=str(meta["session_id"]),
            created_at=str(meta["created_at"]),
            updated_at=str(meta["updated_at"]),
            model_name=str(meta["model_name"]),
            loop_version=str(meta["loop_version"]),
            title=title,
            summary=summary,
            messages=messages,
            file_path=path,
            session_prompt_tokens=int(meta.get("session_prompt_tokens", 0) or 0),
            session_completion_tokens=int(meta.get("session_completion_tokens", 0) or 0),
            session_total_tokens=int(meta.get("session_total_tokens", 0) or 0),
            last_prompt_tokens=int(meta.get("last_prompt_tokens", 0) or 0),
            last_completion_tokens=int(meta.get("last_completion_tokens", 0) or 0),
            last_total_tokens=int(meta.get("last_total_tokens", 0) or 0),
            last_usage_source=str(meta.get("last_usage_source", "none") or "none"),
        )

    def save(self, record: SessionRecord) -> bool:
        if not self._has_meaningful_user_message(record.messages):
            # Enforce "no empty session files".
            try:
                if record.file_path.exists():
                    record.file_path.unlink()
            except OSError:
                pass
            return False

        record.updated_at = _now_iso()
        meta = {
            "session_id": record.session_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "model_name": record.model_name,
            "loop_version": record.loop_version,
            "title": record.title,
            "session_prompt_tokens": int(record.session_prompt_tokens),
            "session_completion_tokens": int(record.session_completion_tokens),
            "session_total_tokens": int(record.session_total_tokens),
            "last_prompt_tokens": int(record.last_prompt_tokens),
            "last_completion_tokens": int(record.last_completion_tokens),
            "last_total_tokens": int(record.last_total_tokens),
            "last_usage_source": str(record.last_usage_source),
        }
        readable = self._render_readable(record.messages)
        content = (
            f"{_SESSION_META_START}\n"
            f"{json.dumps(meta, ensure_ascii=False, indent=2)}\n"
            f"{_SESSION_META_END}\n\n"
            f"# Session {record.session_id}\n\n"
            f"- created_at: {record.created_at}\n"
            f"- updated_at: {record.updated_at}\n"
            f"- loop: {record.loop_version}\n"
            f"- model: {record.model_name}\n\n"
            "## Title\n\n"
            f"{_escape_md(record.title)}\n\n"
            "## Summary\n\n"
            f"{_escape_md(record.summary)}\n\n"
            "## Messages (for restore)\n\n"
            f"{_MESSAGES_START}\n"
            f"{json.dumps(record.messages, ensure_ascii=False, indent=2)}\n"
            f"{_MESSAGES_END}\n\n"
            "## Transcript (readable)\n\n"
            f"{readable}\n"
        )
        record.file_path.write_text(content, encoding="utf-8")
        return True

    @staticmethod
    def _render_readable(messages: List[Message]) -> str:
        lines: List[str] = []
        turn = 0
        for msg in messages:
            role = str(msg.get("role", "unknown"))
            if role == "user":
                turn += 1
                lines.append(f"### Turn {turn}")
            content = str(msg.get("content", "")).strip()
            if role == "tool":
                name = str(msg.get("name", "tool"))
                lines.append(f"- tool `{name}`")
                if content:
                    lines.append(f"  - {content[:400]}")
                continue
            label = role
            lines.append(f"- {label}:")
            lines.append(f"  {_escape_md(content)[:1200] if content else '(empty)'}")
        if not lines:
            return "(empty)"
        return "\n".join(lines)

    @staticmethod
    def _parse_meta(raw: str) -> dict:
        start = raw.find(_SESSION_META_START)
        if start < 0:
            raise ValueError("missing session meta start marker")
        json_start = raw.find("\n", start)
        end = raw.find(_SESSION_META_END, json_start + 1)
        if json_start < 0 or end < 0:
            raise ValueError("invalid session meta block")
        payload = raw[json_start:end].strip()
        meta = json.loads(payload)
        if not isinstance(meta, dict):
            raise ValueError("session meta must be object")
        return meta

    @staticmethod
    def _parse_messages(raw: str) -> List[Message]:
        start = raw.find(_MESSAGES_START)
        if start < 0:
            return []
        body_start = raw.find("\n", start + len(_MESSAGES_START))
        if body_start < 0:
            return []
        end = raw.find(_MESSAGES_END, body_start + 1)
        if end < 0:
            return []
        payload = raw[body_start:end].strip()
        data = json.loads(payload)
        if not isinstance(data, list):
            return []
        messages: List[Message] = []
        for item in data:
            if isinstance(item, dict):
                messages.append(item)
        return messages

    @staticmethod
    def _parse_summary(raw: str) -> str:
        marker = "## Summary"
        idx = raw.find(marker)
        if idx < 0:
            return "(not generated yet)"
        start = raw.find("\n", idx)
        if start < 0:
            return "(not generated yet)"
        next_heading = raw.find("\n## ", start + 1)
        if next_heading < 0:
            next_heading = len(raw)
        summary = raw[start:next_heading].strip()
        return summary or "(not generated yet)"

    @staticmethod
    def _parse_title(raw: str) -> str:
        marker = "## Title"
        idx = raw.find(marker)
        if idx >= 0:
            start = raw.find("\n", idx)
            if start >= 0:
                next_heading = raw.find("\n## ", start + 1)
                if next_heading < 0:
                    next_heading = len(raw)
                title = raw[start:next_heading].strip()
                if title:
                    return title

        # Backward compatibility for older files without "## Title".
        try:
            meta = SessionStoreV6._parse_meta(raw)
            title_meta = str(meta.get("title", "")).strip()
            if title_meta:
                return title_meta
        except Exception:  # noqa: BLE001
            pass
        return "Untitled Session"

    @staticmethod
    def _has_meaningful_user_message(messages: List[Message]) -> bool:
        for msg in messages:
            if str(msg.get("role")) != "user":
                continue
            if str(msg.get("content", "")).strip():
                return True
        return False
