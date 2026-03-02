#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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


def http_json(method: str, url: str, payload: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body.strip():
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code} {method} {url}: {raw}") from err


def wait_server(base_url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/healthz", method="GET")
            with urllib.request.urlopen(req, timeout=3):
                return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"memos server not ready after {timeout_seconds}s")


def safe_kill(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--memos-bin", default=os.getenv("MEMOS_BIN", "/tmp/memos_bin"))
    parser.add_argument("--port", type=int, default=18123)
    parser.add_argument("--runtime-dir", default="/Users/admin/work/agent_loop/backups/memory/memos_runtime")
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )

    if args.retrieve_query_set == "daily_habits":
        retrieve_cases = parse_daily_habit_queries_from_benchmark(benchmark_path)
    else:
        retrieve_cases = [{"name": "single", "query": args.retrieve_query}]
    if args.max_retrieve_cases > 0:
        retrieve_cases = retrieve_cases[: args.max_retrieve_cases]

    runtime_root = Path(args.runtime_dir).expanduser().resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    run_id = int(time.time())
    data_dir = runtime_root / f"case13_{run_id}"
    data_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"http://127.0.0.1:{args.port}"
    log_path = data_dir / "memos_server.log"

    print(f"[RUNTIME] memos_bin={args.memos_bin}")
    print(f"[RUNTIME] data_dir={data_dir}")
    print(f"[RUNTIME] base_url={base_url}")
    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(messages)}")

    print("\n=== INPUT DIALOGUE (FULL) ===")
    for idx, msg in enumerate(messages, 1):
        print(f"{idx:02d}. ({msg['role']}) {msg['content']}")

    server_cmd = [args.memos_bin, "--data", str(data_dir), "--port", str(args.port)]
    print("\n=== SERVER START ===")
    print("cmd:", " ".join(server_cmd))

    with log_path.open("wb") as lf:
        proc = subprocess.Popen(server_cmd, stdout=lf, stderr=subprocess.STDOUT)

    token = ""
    try:
        wait_server(base_url=base_url, timeout_seconds=60)

        create_user_req = {
            "username": "case13",
            "password": "case13-pass",
            "role": "ADMIN",
            "state": "NORMAL",
        }
        print("\n=== CREATE USER REQUEST ===")
        print(json.dumps(create_user_req, ensure_ascii=False, indent=2))
        create_user_resp = http_json("POST", f"{base_url}/api/v1/users", create_user_req)
        print("\n=== CREATE USER RESULT ===")
        print(json.dumps(create_user_resp, ensure_ascii=False, indent=2))

        sign_in_req = {"passwordCredentials": {"username": "case13", "password": "case13-pass"}}
        print("\n=== SIGN IN REQUEST ===")
        print(json.dumps(sign_in_req, ensure_ascii=False, indent=2))
        sign_in_resp = http_json("POST", f"{base_url}/api/v1/auth/signin", sign_in_req)
        print("\n=== SIGN IN RESULT ===")
        print(json.dumps(sign_in_resp, ensure_ascii=False, indent=2))
        token = sign_in_resp.get("accessToken", "")
        if not token:
            raise RuntimeError("SignIn succeeded but accessToken missing")

        print("\n=== MEMORIZE REQUEST ===")
        print(json.dumps({"messages": messages}, ensure_ascii=False, indent=2))

        created_memos: list[dict] = []
        for idx, msg in enumerate(messages, 1):
            content = f"[turn={idx:02d} role={msg['role']}] {msg['content']}"
            create_memo_req = {
                "content": content,
                "visibility": "PRIVATE",
                "state": "NORMAL",
            }
            result = http_json("POST", f"{base_url}/api/v1/memos", create_memo_req, token=token)
            created_memos.append(result)

        print("\n=== MEMORIZE RESULT ===")
        print(f"created_memos={len(created_memos)}")
        print(json.dumps(created_memos, ensure_ascii=False, indent=2))

        print("\n=== RETRIEVE SUMMARY ===")
        print(f"total_cases={len(retrieve_cases)}")
        for i, case in enumerate(retrieve_cases, 1):
            raw_query = case["query"]
            expr = f'content.contains({json.dumps(raw_query, ensure_ascii=False)})'
            url = f"{base_url}/api/v1/memos?{urllib.parse.urlencode({'filter': expr, 'pageSize': '200'})}"
            print(f"\n=== RETRIEVE CASE {i}/{len(retrieve_cases)}: {case['name']} ===")
            print("query:", raw_query)
            print("\n=== RETRIEVE REQUEST ===")
            print(json.dumps({"method": "GET", "url": url, "filter": expr}, ensure_ascii=False, indent=2))
            result = http_json("GET", url, token=token)
            memos = result.get("memos", []) if isinstance(result, dict) else []
            print("\n=== RETRIEVE RESULT ===")
            print(f"items_hit={len(memos)}")
            print(json.dumps(result, ensure_ascii=False, indent=2))

        print("\n=== STORAGE SHAPE ===")
        db_file = data_dir / "memos_prod.db"
        print(
            json.dumps(
                {
                    "data_dir": str(data_dir),
                    "expected_sqlite": str(db_file),
                    "sqlite_exists": db_file.exists(),
                    "server_log": str(log_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    finally:
        safe_kill(proc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
