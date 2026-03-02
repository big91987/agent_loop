#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/admin/work/agent_loop")
from core.config import load_config  # noqa: E402

DEFAULT_BENCHMARK_PATH = Path(
    "/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md"
)


def parse_case_messages_from_benchmark(
    benchmark_path: Path, case: str, max_messages: int | None = None
) -> list[dict[str, str]]:
    text = benchmark_path.read_text(encoding="utf-8")
    case_header_pattern = re.compile(r"^(?:###\s+Case\s+(\d+):.*|##+\s+.*\(Case\s+(\d+)\).*)$", re.MULTILINE)
    headers: list[dict[str, int]] = []
    for m in case_header_pattern.finditer(text):
        num_str = m.group(1) or m.group(2)
        if not num_str:
            continue
        headers.append({"num": int(num_str), "start": m.start(), "end": m.end()})

    if not headers:
        raise ValueError("No case headers found in benchmark markdown")

    if case.lower() in {"auto", "last"}:
        target_num = headers[-1]["num"]
    else:
        m_case = re.search(r"(\d+)", case)
        if not m_case:
            raise ValueError(f"Invalid case selector: {case}")
        target_num = int(m_case.group(1))

    header_idx = next((i for i, h in enumerate(headers) if h["num"] == target_num), None)
    if header_idx is None:
        raise ValueError(f"Case not found: Case {target_num}")

    section_start = headers[header_idx]["end"]
    section_end = headers[header_idx + 1]["start"] if header_idx + 1 < len(headers) else len(text)
    section = text[section_start:section_end]

    messages: list[dict[str, str]] = []
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
        messages.append({"role": role, "content": content_raw})
        if max_messages is not None and len(messages) >= max_messages:
            break

    if not messages:
        raise ValueError(f"No dialogue rows parsed from Case {target_num}")
    return messages


def parse_daily_habit_queries_from_benchmark(benchmark_path: Path) -> list[dict[str, str]]:
    text = benchmark_path.read_text(encoding="utf-8")
    case_header = re.search(r"^##+\s+.*\(Case\s+13\).*$", text, re.MULTILINE)
    if not case_header:
        return []
    section = text[case_header.end() :]
    next_header = re.search(r"^##\s+", section, re.MULTILINE)
    if next_header:
        section = section[: next_header.start()]

    cases: list[dict[str, str]] = []
    pattern = re.compile(r"触发查询\s*\(Query\)\s*-\s*(\d+)(?:\*\*)?\s*:\s*`([^`]+)`")
    for m in pattern.finditer(section):
        idx = m.group(1).strip()
        query = m.group(2).strip()
        if query:
            cases.append({"name": f"Query-{idx}", "query": query})
    return cases


def print_input_dialogue(messages: list[dict[str, str]]) -> None:
    print("\n=== INPUT DIALOGUE (FULL) ===")
    for idx, msg in enumerate(messages, 1):
        print(f"{idx:02d}. ({msg['role']}) {msg['content']}")


def memory_to_dict(memory: object) -> dict:
    if hasattr(memory, "model_dump"):
        return getattr(memory, "model_dump")()
    if hasattr(memory, "dict"):
        return getattr(memory, "dict")()
    if isinstance(memory, dict):
        return memory
    result: dict[str, object] = {}
    for key in [
        "entry_id",
        "lossless_restatement",
        "timestamp",
        "location",
        "persons",
        "entities",
        "topic",
        "keywords",
    ]:
        result[key] = getattr(memory, key, None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/Users/admin/work/agent_loop/configs/default.json")
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--runtime-dir", default="/Users/admin/work/agent_loop/backups/memory/simplemem_runtime")
    parser.add_argument("--print-limit", type=int, default=0)
    parser.add_argument("--enable-planning", action="store_true")
    parser.add_argument("--enable-reflection", action="store_true")
    args = parser.parse_args()

    app_cfg = load_config(args.config)
    api_key = (app_cfg.api_key or "").strip() if app_cfg.api_key else ""
    if not api_key and app_cfg.api_key_env:
        api_key = (os.getenv(app_cfg.api_key_env) or "").strip()
    if not api_key:
        raise SystemExit(f"Missing API key: {app_cfg.api_key_env or 'OPENAI_API_KEY'}")

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )

    print(f"[CONFIG] model={app_cfg.model_name} base_url={app_cfg.base_url} provider={app_cfg.provider}")
    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(messages)}")
    print_input_dialogue(messages)

    from simplemem import SimpleMemConfig, SimpleMemSystem, set_config

    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    run_id = int(time.time())
    db_path = runtime_dir / f"lancedb_case13_{run_id}"
    table_name = f"memory_entries_case13_{run_id}"

    sm_cfg = SimpleMemConfig(
        openai_api_key=api_key,
        openai_base_url=app_cfg.base_url,
        llm_model=app_cfg.model_name,
        embedding_model=args.embedding_model,
        lancedb_path=str(db_path),
        memory_table_name=table_name,
        use_streaming=False,
        enable_thinking=False,
        use_json_format=True,
        enable_parallel_processing=False,
        enable_parallel_retrieval=False,
        enable_planning=args.enable_planning,
        enable_reflection=args.enable_reflection,
    )
    set_config(sm_cfg)

    print("\n=== MEMORIZE REQUEST ===")
    print(json.dumps({"messages": messages}, ensure_ascii=False, indent=2))

    system = SimpleMemSystem(
        clear_db=True,
        db_path=str(db_path),
        table_name=table_name,
        enable_planning=args.enable_planning,
        enable_reflection=args.enable_reflection,
        enable_parallel_processing=False,
        enable_parallel_retrieval=False,
    )

    for idx, msg in enumerate(messages, 1):
        speaker = "User" if msg["role"] == "user" else "Assistant"
        ts = f"2026-02-28T08:{idx // 60:02d}:{idx % 60:02d}"
        system.add_dialogue(speaker=speaker, content=msg["content"], timestamp=ts)

    system.finalize()

    all_mem = system.get_all_memories()
    mem_dump = [memory_to_dict(m) for m in all_mem]
    print("\n=== MEMORIZE RESULT ===")
    print(f"memory_entries={len(mem_dump)}")
    if args.print_limit > 0:
        mem_dump = mem_dump[: args.print_limit]
    print(json.dumps(mem_dump, ensure_ascii=False, indent=2))

    if args.retrieve_query_set == "daily_habits":
        retrieve_cases = parse_daily_habit_queries_from_benchmark(benchmark_path)
    else:
        retrieve_cases = [{"name": "single", "query": args.retrieve_query}]

    if args.max_retrieve_cases > 0:
        retrieve_cases = retrieve_cases[: args.max_retrieve_cases]

    print("\n=== RETRIEVE SUMMARY ===")
    print(f"total_cases={len(retrieve_cases)}")

    for i, case in enumerate(retrieve_cases, 1):
        print(f"\n=== RETRIEVE CASE {i}/{len(retrieve_cases)}: {case['name']} ===")
        print("query:", case["query"])
        print("\n=== RETRIEVE REQUEST ===")
        print(
            json.dumps(
                {
                    "query": case["query"],
                    "method": "hybrid_retriever.retrieve",
                    "enable_planning": args.enable_planning,
                    "enable_reflection": args.enable_reflection,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        retrieved = system.hybrid_retriever.retrieve(case["query"], enable_reflection=args.enable_reflection)
        ret_dump = [memory_to_dict(m) for m in retrieved]
        if args.print_limit > 0:
            ret_dump = ret_dump[: args.print_limit]
        print("\n=== RETRIEVE RESULT ===")
        print(f"items_hit={len(retrieved)}")
        print(json.dumps(ret_dump, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
