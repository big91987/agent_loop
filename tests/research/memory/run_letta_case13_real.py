#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

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


def wait_health(base_url: str, timeout_sec: int = 120) -> None:
    deadline = time.time() + timeout_sec
    health_url = f"{base_url.rstrip('/')}/v1/health"
    while time.time() < deadline:
        try:
            resp = requests.get(health_url, timeout=2)
            if resp.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Letta health check timeout: {health_url}")


def to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump())
    if hasattr(obj, "dict"):
        return to_jsonable(obj.dict())
    if hasattr(obj, "__dict__"):
        return to_jsonable({k: v for k, v in obj.__dict__.items() if not k.startswith("_")})
    return str(obj)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--search-limit", type=int, default=8)
    parser.add_argument("--server-url", default="http://localhost:8283")
    parser.add_argument("--letta-cli", default="/Users/admin/miniconda3/envs/py312/bin/letta")
    parser.add_argument("--print-limit", type=int, default=0)
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )

    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(messages)}")
    print_input_dialogue(messages)

    env = os.environ.copy()
    env.setdefault("LETTA_PG_DB", "letta")
    env.setdefault("LETTA_PG_USER", "letta")
    env.setdefault("LETTA_PG_PASSWORD", "letta")
    env.setdefault("LETTA_PG_HOST", "127.0.0.1")
    env.setdefault("LETTA_PG_PORT", "5432")
    env.setdefault("LETTA_PROVIDER", "letta")

    server_proc = subprocess.Popen(
        [args.letta_cli, "server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        wait_health(args.server_url, timeout_sec=180)

        archive_name = f"case13_archive_{int(time.time())}"
        archive_resp = requests.post(
            f"{args.server_url.rstrip('/')}/v1/archives",
            json={"name": archive_name},
            timeout=30,
        )
        archive_resp.raise_for_status()
        archive = archive_resp.json()
        archive_id = archive["id"]

        print("\n=== MEMORIZE REQUEST ===")
        print(json.dumps({"archive_id": archive_id, "messages": messages}, ensure_ascii=False, indent=2))

        inserted: list[Any] = []
        for i, msg in enumerate(messages, 1):
            text = f"turn={i} role={msg['role']} content={msg['content']}"
            passage_resp = requests.post(
                f"{args.server_url.rstrip('/')}/v1/archives/{archive_id}/passages",
                json={"text": text},
                timeout=30,
            )
            passage_resp.raise_for_status()
            inserted.append(passage_resp.json())

        dump_insert = to_jsonable(inserted)
        if args.print_limit > 0 and isinstance(dump_insert, list):
            dump_insert = dump_insert[: args.print_limit]

        print("\n=== MEMORIZE RESULT ===")
        print(json.dumps({"archive_id": archive_id, "passages": dump_insert}, ensure_ascii=False, indent=2))

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
            req = {
                "query": case["query"],
                "archive_id": archive_id,
                "limit": args.search_limit,
            }
            print("\n=== RETRIEVE REQUEST ===")
            print(json.dumps(req, ensure_ascii=False, indent=2))
            results_resp = requests.post(
                f"{args.server_url.rstrip('/')}/v1/passages/search",
                json=req,
                timeout=30,
            )
            results_resp.raise_for_status()
            results = results_resp.json()
            if args.print_limit > 0:
                results = results[: args.print_limit]
            print("\n=== RETRIEVE RESULT ===")
            print(json.dumps(to_jsonable(results), ensure_ascii=False, indent=2))

        print("\n=== STORAGE SHAPE ===")
        print(json.dumps({"type": "postgresql+pgvector", "database": env["LETTA_PG_DB"], "table_hint": "archival_passages"}, ensure_ascii=False, indent=2))

        try:
            requests.delete(f"{args.server_url.rstrip('/')}/v1/archives/{archive_id}", timeout=20)
        except Exception:
            pass

    finally:
        server_proc.send_signal(signal.SIGINT)
        try:
            server_proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait(timeout=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
