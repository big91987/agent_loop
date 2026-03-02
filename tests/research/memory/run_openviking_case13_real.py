#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

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


def build_openviking_config(
    workspace: Path,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str,
    embed_base_url: str,
    embed_model: str,
    embed_api_key: str,
    embed_dim: int,
) -> dict[str, Any]:
    return {
        "storage": {"workspace": str(workspace)},
        "embedding": {
            "dense": {
                "provider": "openai",
                "model": embed_model,
                "api_key": embed_api_key,
                "api_base": embed_base_url,
                "dimension": embed_dim,
            }
        },
        "vlm": {
            "provider": "openai",
            "model": llm_model,
            "api_key": llm_api_key,
            "api_base": llm_base_url,
        },
        "log": {"level": "INFO", "output": "stdout"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/Users/admin/work/agent_loop/configs/default.json")
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--runtime-dir", default="/Users/admin/work/agent_loop/backups/memory/openviking_runtime")
    parser.add_argument("--embed-base-url", default=os.getenv("EMBED_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"))
    parser.add_argument("--embed-model", default=os.getenv("EMBED_MODEL", "embedding-3"))
    parser.add_argument("--embed-api-key-env", default=os.getenv("EMBED_API_KEY_ENV", "ZHIPU_API_KEY"))
    parser.add_argument("--embed-dim", type=int, default=1024)
    parser.add_argument("--search-limit", type=int, default=8)
    parser.add_argument("--print-limit", type=int, default=0)
    args = parser.parse_args()

    app_cfg = load_config(args.config)
    llm_api_key = (app_cfg.api_key or "").strip() if app_cfg.api_key else ""
    if not llm_api_key and app_cfg.api_key_env:
        llm_api_key = (os.getenv(app_cfg.api_key_env) or "").strip()
    if not llm_api_key:
        raise SystemExit(f"Missing API key: {app_cfg.api_key_env or 'OPENAI_API_KEY'}")

    embed_api_key = (os.getenv(args.embed_api_key_env) or "").strip()
    if not embed_api_key:
        raise SystemExit(f"Missing embedding API key: {args.embed_api_key_env}")

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

    runtime_root = Path(args.runtime_dir).expanduser().resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    run_id = int(time.time())
    workspace = runtime_root / f"workspace_case13_{run_id}"
    workspace.mkdir(parents=True, exist_ok=True)

    ov_cfg = build_openviking_config(
        workspace=workspace,
        llm_model=app_cfg.model_name,
        llm_base_url=app_cfg.base_url,
        llm_api_key=llm_api_key,
        embed_base_url=args.embed_base_url,
        embed_model=args.embed_model,
        embed_api_key=embed_api_key,
        embed_dim=args.embed_dim,
    )

    cfg_file = Path(tempfile.mkdtemp(prefix="openviking_case13_")) / "ov.conf"
    cfg_file.write_text(json.dumps(ov_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.environ["OPENVIKING_CONFIG_FILE"] = str(cfg_file)

    print("\n=== OPENVIKING CONFIG ===")
    print(json.dumps(ov_cfg, ensure_ascii=False, indent=2))

    import openviking as ov

    client = ov.OpenViking(path=str(workspace))
    client.initialize()

    try:
        session = client.session()
        sid = session.session_id

        print("\n=== MEMORIZE REQUEST ===")
        print(json.dumps({"session_id": sid, "messages": messages}, ensure_ascii=False, indent=2))

        for msg in messages:
            client.add_message(session_id=sid, role=msg["role"], content=msg["content"])

        commit_result = client.commit_session(sid)
        print("\n=== MEMORIZE RESULT (COMMIT) ===")
        print(json.dumps(to_jsonable(commit_result), ensure_ascii=False, indent=2))

        wait_result = client.wait_processed(timeout=180)
        print("\n=== WAIT PROCESSED RESULT ===")
        print(json.dumps(to_jsonable(wait_result), ensure_ascii=False, indent=2))

        memory_uris: list[str] = []
        for root in ["viking://user/default/memories", "viking://agent/default/memories"]:
            try:
                matches = client.glob(pattern="**/*.md", uri=root)
                for item in to_jsonable(matches).get("matches", []):
                    if isinstance(item, str):
                        memory_uris.append(item)
            except Exception:
                continue
        memory_uris = sorted(set(memory_uris))

        print("\n=== MEMORY FILES ===")
        print(json.dumps(memory_uris, ensure_ascii=False, indent=2))

        print("\n=== MEMORY FILE CONTENTS (FULL) ===")
        for uri in memory_uris:
            content = client.read(uri)
            print(f"\n--- {uri} ---")
            print(content)

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
            request_json = {
                "query": case["query"],
                "session_id": sid,
                "limit": args.search_limit,
                "search_method": "openviking.search(target_uri=viking://user/default/memories)",
                "find_method": "openviking.find(target_uri=viking://user/default/memories)",
            }
            print(json.dumps(request_json, ensure_ascii=False, indent=2))

            search_result = client.search(
                query=case["query"],
                target_uri="viking://user/default/memories",
                session_id=sid,
                limit=args.search_limit,
            )
            find_result = client.find(
                query=case["query"],
                target_uri="viking://user/default/memories",
                limit=args.search_limit,
            )
            result_json = {
                "search": to_jsonable(search_result),
                "find": to_jsonable(find_result),
            }
            if args.print_limit > 0:
                for method in ["search", "find"]:
                    mres = result_json.get(method)
                    if isinstance(mres, dict):
                        for key in ["memories", "resources"]:
                            if key in mres and isinstance(mres[key], list):
                                mres[key] = mres[key][: args.print_limit]
            print("\n=== RETRIEVE RESULT ===")
            print(json.dumps(result_json, ensure_ascii=False, indent=2))

        print("\n=== STORAGE PATHS ===")
        print(json.dumps({"workspace": str(workspace), "config_file": str(cfg_file)}, ensure_ascii=False, indent=2))

    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
