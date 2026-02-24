from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .types import Message

SUMMARY_TAG = "[SESSION SUMMARY v6.1]"


@dataclass
class ShortMemoryConfig:
    auto_enabled: bool = True
    usage_threshold_tokens: int = 18000
    keep_recent_user_turns: int = 4
    min_prefix_messages: int = 8
    max_prefix_messages: int = 120
    max_transcript_chars: int = 12000
    max_summary_chars: int = 2200


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_summary_message(msg: Message) -> bool:
    return str(msg.get("role")) == "assistant" and str(msg.get("content", "")).startswith(SUMMARY_TAG)


def split_for_compaction(
    messages: List[Message],
    *,
    keep_recent_user_turns: int,
    min_prefix_messages: int,
    max_prefix_messages: int,
) -> Tuple[List[Message], List[Message]]:
    if len(messages) < min_prefix_messages:
        return [], list(messages)

    user_seen = 0
    cut_idx = len(messages)
    for idx in range(len(messages) - 1, -1, -1):
        if str(messages[idx].get("role")) == "user":
            user_seen += 1
            if user_seen >= max(1, keep_recent_user_turns):
                cut_idx = idx
                break

    if cut_idx <= 0:
        return [], list(messages)

    prefix = list(messages[:cut_idx])
    if len(prefix) > max_prefix_messages:
        prefix = prefix[-max_prefix_messages:]
        cut_idx = len(messages) - (len(messages) - cut_idx)
    suffix = list(messages[cut_idx:])

    if len(prefix) < min_prefix_messages:
        return [], list(messages)
    return prefix, suffix


def render_transcript(messages: List[Message], *, max_chars: int) -> str:
    chunks: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "unknown"))
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        chunks.append(f"[{role}] {content}")
    text = "\n\n".join(chunks)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def fallback_summary(messages: List[Message], *, max_chars: int) -> str:
    lines: List[str] = ["- 这是自动压缩摘要（fallback），请按需手动编辑。"]
    goals = [str(m.get("content", "")).strip() for m in messages if str(m.get("role")) == "user"]
    replies = [str(m.get("content", "")).strip() for m in messages if str(m.get("role")) == "assistant"]
    if goals:
        lines.append(f"- 早期用户诉求（节选）：{goals[0][:180]}")
    if len(goals) > 1:
        lines.append(f"- 用户后续补充（节选）：{goals[-1][:180]}")
    if replies:
        lines.append(f"- 近期助手回复（节选）：{replies[-1][:180]}")
    out = "\n".join(lines)
    if len(out) <= max_chars:
        return out
    return out[:max_chars]


def build_summary_message(*, summary_text: str, reason: str, covered_count: int) -> Message:
    header = (
        f"{SUMMARY_TAG}\n"
        f"compressed_at={utc_now_iso()}\n"
        f"reason={reason}\n"
        f"covered_messages={covered_count}\n\n"
    )
    return {"role": "assistant", "content": f"{header}{summary_text.strip()}"}


def compact_messages(
    messages: List[Message],
    *,
    summary_text: str,
    reason: str,
    keep_recent_user_turns: int,
    min_prefix_messages: int,
    max_prefix_messages: int,
) -> Dict[str, object]:
    prefix, suffix = split_for_compaction(
        messages,
        keep_recent_user_turns=keep_recent_user_turns,
        min_prefix_messages=min_prefix_messages,
        max_prefix_messages=max_prefix_messages,
    )
    if not prefix:
        return {
            "performed": False,
            "message": "not enough history to compact",
            "messages": list(messages),
            "covered_messages": 0,
            "remaining_messages": len(messages),
        }

    summary_msg = build_summary_message(summary_text=summary_text, reason=reason, covered_count=len(prefix))
    merged = [summary_msg, *suffix]
    return {
        "performed": True,
        "message": "compaction applied",
        "messages": merged,
        "covered_messages": len(prefix),
        "remaining_messages": len(merged),
    }
