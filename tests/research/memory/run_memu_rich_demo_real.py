#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/Users/admin/work/agent_loop")
# Use memU source code from local clone
sys.path.insert(0, "/tmp/memU/src")
if "memu._core" not in sys.modules:
    core_stub = types.ModuleType("memu._core")
    core_stub.hello_from_bin = lambda: "stub"  # type: ignore[attr-defined]
    sys.modules["memu._core"] = core_stub

from core.config import load_config  # noqa: E402

DEFAULT_BENCHMARK_PATH = Path(
    "/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_benchmark_v6_full.md"
)

def build_conversation_file(messages: list[dict[str, object]]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="memu_rich_real_"))
    f = d / "rich_conversation.json"
    f.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


def parse_case_messages_from_benchmark(
    benchmark_path: Path, case: str, max_messages: int | None = None
) -> list[dict[str, object]]:
    text = benchmark_path.read_text(encoding="utf-8")
    headers = list(re.finditer(r"^###\s+(Case\s+\d+):?.*$", text, re.MULTILINE))
    if not headers:
        raise ValueError("No case headers found in benchmark markdown")
    if case.lower() in {"auto", "last"}:
        target_case = headers[-1].group(1)
    else:
        target_case = case

    case_header_pattern = re.compile(rf"^###\s+{re.escape(target_case)}\b.*$", re.MULTILINE)
    header_match = case_header_pattern.search(text)
    if not header_match:
        raise ValueError(f"Case not found: {target_case}")

    section_start = header_match.end()
    next_case = re.search(r"^###\s+Case\s+\d+:", text[section_start:], re.MULTILINE)
    section_end = section_start + next_case.start() if next_case else len(text)
    section = text[section_start:section_end]

    messages: list[dict[str, object]] = []
    idx = 0
    for line in section.splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 3:
            continue
        role_raw = cells[1]
        content_raw = cells[2]
        role_norm = role_raw.lower()
        if role_norm not in {"user", "agent", "assistant"}:
            continue
        if not content_raw or content_raw == ":---":
            continue
        role = "assistant" if role_norm in {"agent", "assistant"} else "user"
        created_at = f"2026-02-26T08:{idx // 60:02d}:{idx % 60:02d}Z"
        messages.append(
            {
                "role": role,
                "created_at": created_at,
                "content": {"text": content_raw},
            }
        )
        idx += 1
        if max_messages is not None and len(messages) >= max_messages:
            break

    if not messages:
        raise ValueError(f"No dialogue rows parsed from {target_case}")
    return messages


def print_input_dialogue(messages: list[dict[str, object]]) -> None:
    print("\n=== INPUT DIALOGUE (FULL) ===")
    for idx, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        created_at = msg.get("created_at", "")
        content = msg.get("content", {})
        text = ""
        if isinstance(content, dict):
            text = str(content.get("text", ""))
        else:
            text = str(content)
        print(f"{idx:02d}. [{created_at}] ({role}) {text}")


def print_retrieve_request(queries: list[dict[str, object]], where: dict[str, str], method: str) -> None:
    print("\n=== RETRIEVE REQUEST ===")
    print(f"method: {method}")
    print("where:", json.dumps(where, ensure_ascii=False))
    print("queries:")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {json.dumps(q, ensure_ascii=False)}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/Users/admin/work/agent_loop/configs/default.json")
    parser.add_argument("--user-id", default="u_real_demo_001")
    parser.add_argument("--retrieve-method", choices=["rag", "llm"], default="rag")
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument(
        "--retrieve-query",
        default="请回忆我在这组对话里的关键偏好、工作信息和近期计划，先给结论再给细节。",
    )
    parser.add_argument("--embed-base-url", default=os.getenv("EMBED_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"))
    parser.add_argument("--embed-model", default=os.getenv("EMBED_MODEL", "embedding-3"))
    parser.add_argument("--embed-api-key-env", default=os.getenv("EMBED_API_KEY_ENV", "ZHIPU_API_KEY"))
    args = parser.parse_args()

    app_cfg = load_config(args.config)
    key = (app_cfg.api_key or "").strip() if app_cfg.api_key else ""
    if not key and app_cfg.api_key_env:
        key = (os.getenv(app_cfg.api_key_env) or "").strip()

    if not key:
        raise SystemExit(
            f"Missing API key. Please set {app_cfg.api_key_env or 'OPENAI_API_KEY'} or fill api_key in {args.config}."
        )
    embed_key = (os.getenv(args.embed_api_key_env) or "").strip()
    if not embed_key:
        raise SystemExit(f"Missing embedding API key. Please set {args.embed_api_key_env}.")

    from memu.app import MemoryService  # type: ignore  # noqa: E402

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    if not benchmark_path.exists():
        raise SystemExit(f"Benchmark file not found: {benchmark_path}")
    input_messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )
    conv_file = build_conversation_file(input_messages)

    print(f"[CONFIG] model={app_cfg.model_name} base_url={app_cfg.base_url} provider={app_cfg.provider}")
    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(input_messages)}")
    print(f"[INPUT FILE] {conv_file}")
    print_input_dialogue(input_messages)

    service = MemoryService(
        llm_profiles={
            "default": {
                "provider": "openai",
                "client_backend": "sdk",
                "base_url": app_cfg.base_url,
                "api_key": key,
                "chat_model": app_cfg.model_name,
            },
            "embedding": {
                "provider": "openai",
                "client_backend": "sdk",
                "base_url": args.embed_base_url,
                "api_key": embed_key,
                "embed_model": args.embed_model,
            },
        },
        database_config={"metadata_store": {"provider": "inmemory"}},
        retrieve_config={
            "method": args.retrieve_method,
            "route_intention": True,
            "sufficiency_check": True,
            "item": {"ranking": "salience", "top_k": 8},
            "category": {"top_k": 5},
        },
        memorize_config={
            "memory_types": ["profile", "behavior", "event"],
            "enable_item_reinforcement": True,
            "memory_categories": [
                {"name": "preferences", "description": "user preferences"},
                {"name": "habits", "description": "user routines"},
                {"name": "activities", "description": "user activities"},
                {"name": "work_life", "description": "work context"},
                {"name": "experiences", "description": "events and plans"},
            ],
        },
    )

    mem = await service.memorize(resource_url=str(conv_file), modality="conversation", user={"user_id": args.user_id})
    print("\n=== MEMORIZE RESULT ===")
    print("items:", len(mem.get("items", [])))
    print("categories:", len(mem.get("categories", [])))
    for i, item in enumerate(mem.get("items", [])[:12], 1):
        print(f"  item{i}: [{item.get('memory_type')}] {item.get('summary')}")

    retrieve_queries = [{"role": "user", "content": {"text": args.retrieve_query}}]
    retrieve_where = {"user_id": args.user_id}
    print_retrieve_request(retrieve_queries, retrieve_where, args.retrieve_method)
    ret = await service.retrieve(
        queries=retrieve_queries,
        where=retrieve_where,
    )
    print("\n=== RETRIEVE RESULT ===")
    print("needs_retrieval:", ret.get("needs_retrieval"))
    print("categories hit:", len(ret.get("categories", [])))
    print("items hit:", len(ret.get("items", [])))
    for i, item in enumerate(ret.get("items", [])[:12], 1):
        print(f"  hit{i}: [{item.get('memory_type')}] {item.get('summary')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
