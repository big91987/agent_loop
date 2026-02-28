#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, "/Users/admin/work/agent_loop")
from core.config import load_config  # noqa: E402

DEFAULT_BENCHMARK_PATH = Path(
    "/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md"
)

DAILY_HABIT_RETRIEVE_CASES: list[dict[str, str]] = [
    {"name": "Query-1", "query": "我中午想吃煎饼，帮我下个单。"},
    {"name": "Query-2", "query": "给我推荐个咖啡。"},
    {"name": "Query-3", "query": "我昨天被我家猫挠了一下，怎么处理比较稳妥。"},
    {"name": "Query-4", "query": "我想跳槽，先按我的背景给我起一版简历大纲我看看看。"},
    {"name": "Query-5", "query": "下周分享会我还没想好开场，按我定过的方向给个题目和提纲。"},
    {"name": "Query-6", "query": "我明天去杭州，帮我列个订票要点清单，尤其座位怎么选。"},
    {"name": "Query-7", "query": "我电脑重装了，先把我平时开工常用的软件清单列给我。"},
    {"name": "Query-8", "query": "我现在要出门，钥匙找不到了，你帮我按我平时习惯排查一下。"},
]

EXPECTED_KEYWORDS_BY_QUERY: dict[str, list[str]] = {
    "Query-1": ["香菜", "反胃"],
    "Query-2": ["拿铁", "冰美式", "胃"],
    "Query-3": ["奶油", "布偶猫"],
    "Query-4": ["星云科技", "产品经理", "机器人"],
    "Query-5": ["机器学习", "分享"],
    "Query-6": ["靠窗", "北京", "上海"],
    "Query-7": ["Chrome", "Slack", "VSCode", "app.py"],
    "Query-8": ["钥匙", "厨房门后", "挂钩"],
}


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


def detect_embedding_dims(embed_base_url: str, embed_api_key: str, embed_model: str) -> int:
    client = OpenAI(api_key=embed_api_key, base_url=embed_base_url, max_retries=0, timeout=30)
    resp = client.embeddings.create(model=embed_model, input=["dimension probe"])  # type: ignore[arg-type]
    return len(resp.data[0].embedding)


def print_input_dialogue(messages: list[dict[str, str]]) -> None:
    print("\n=== INPUT DIALOGUE (FULL) ===")
    for idx, msg in enumerate(messages, 1):
        print(f"{idx:02d}. ({msg['role']}) {msg['content']}")


def extract_memories_from_result(result: object) -> list[str]:
    if not isinstance(result, dict):
        return []
    rows = result.get("results", [])
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            mem = row.get("memory")
            if isinstance(mem, str):
                out.append(mem)
    return out


def keyword_hit(memories: list[str], keywords: list[str]) -> bool:
    joined = " | ".join(memories)
    return any(kw in joined for kw in keywords)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/Users/admin/work/agent_loop/configs/default.json")
    parser.add_argument("--user-id", default="u_real_demo_mem0_001")
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--embed-base-url", default=os.getenv("EMBED_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"))
    parser.add_argument("--embed-model", default=os.getenv("EMBED_MODEL", "embedding-3"))
    parser.add_argument("--embed-api-key-env", default=os.getenv("EMBED_API_KEY_ENV", "ZHIPU_API_KEY"))
    parser.add_argument("--search-limit", type=int, default=8)
    parser.add_argument("--embed-dims", type=int, default=0, help="Set embedding dims explicitly (0=auto detect)")
    parser.add_argument(
        "--mem0-dir",
        default="/Users/admin/work/agent_loop/backups/memu/mem0_runtime",
        help="Writable runtime dir for MEM0_DIR",
    )
    args = parser.parse_args()

    os.environ["MEM0_DIR"] = args.mem0_dir
    Path(args.mem0_dir).mkdir(parents=True, exist_ok=True)

    app_cfg = load_config(args.config)
    llm_key = (app_cfg.api_key or "").strip() if app_cfg.api_key else ""
    if not llm_key and app_cfg.api_key_env:
        llm_key = (os.getenv(app_cfg.api_key_env) or "").strip()
    if not llm_key:
        raise SystemExit(
            f"Missing API key. Please set {app_cfg.api_key_env or 'OPENAI_API_KEY'} or fill api_key in {args.config}."
        )

    embed_key = (os.getenv(args.embed_api_key_env) or "").strip()
    if not embed_key:
        raise SystemExit(f"Missing embedding API key. Please set {args.embed_api_key_env}.")

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    if not benchmark_path.exists():
        raise SystemExit(f"Benchmark file not found: {benchmark_path}")

    messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )

    print(f"[CONFIG] model={app_cfg.model_name} base_url={app_cfg.base_url} provider={app_cfg.provider}")
    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(messages)}")
    print_input_dialogue(messages)

    llm_base_url = app_cfg.base_url
    embed_base_url = args.embed_base_url
    print("\n[STEP] detect embedding dims")
    if args.embed_dims > 0:
        embed_dims = args.embed_dims
        print(f"[EMBED] using fixed dims={embed_dims} base_url={embed_base_url}")
    else:
        embed_dims = detect_embedding_dims(embed_base_url, embed_key, args.embed_model)
        print(f"[EMBED] model={args.embed_model} dims={embed_dims}")

    collection_name = f"mem0_case13_{int(time.time())}"
    qdrant_path = f"/tmp/mem0_qdrant_case13_{int(time.time())}"

    mem0_config = {
        "version": "v1.1",
        "llm": {
            "provider": "openai",
            "config": {
                "model": app_cfg.model_name,
                "api_key": llm_key,
                "openai_base_url": llm_base_url,
                "temperature": 0.1,
                "top_p": 0.95,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": args.embed_model,
                "api_key": embed_key,
                "openai_base_url": embed_base_url,
                "embedding_dims": embed_dims,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection_name,
                "embedding_model_dims": embed_dims,
                "path": qdrant_path,
                "on_disk": True,
            },
        },
    }

    from mem0 import Memory  # imported only after env and config prepared

    memory = Memory.from_config(mem0_config)

    print("\n=== MEMORIZE REQUEST ===")
    print(json.dumps({"user_id": args.user_id, "messages": messages}, ensure_ascii=False, indent=2))

    memorize_result = memory.add(messages=messages, user_id=args.user_id, infer=True)
    print("\n=== MEMORIZE RESULT ===")
    print(json.dumps(memorize_result, ensure_ascii=False, indent=2))

    if args.retrieve_query_set == "daily_habits":
        parsed_cases = parse_daily_habit_queries_from_benchmark(benchmark_path)
        retrieve_cases = parsed_cases if parsed_cases else DAILY_HABIT_RETRIEVE_CASES
    else:
        retrieve_cases = [{"name": "single", "query": args.retrieve_query}]

    if args.max_retrieve_cases > 0:
        retrieve_cases = retrieve_cases[: args.max_retrieve_cases]

    print("\n=== RETRIEVE SUMMARY ===")
    print(f"total_cases={len(retrieve_cases)}")
    base_results: list[tuple[str, str, dict]] = []

    for i, case in enumerate(retrieve_cases, 1):
        q = case["query"]
        print(f"\n=== RETRIEVE CASE {i}/{len(retrieve_cases)}: {case['name']} ===")
        print("query:", q)
        result = memory.search(query=q, user_id=args.user_id, limit=args.search_limit)
        print("result:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        base_results.append((case["name"], q, result))

    print("\n=== SELLPOINT PROBE A: infer=True vs infer=False ===")
    collection_name_no_infer = f"mem0_case13_noinfer_{int(time.time())}"
    qdrant_path_no_infer = f"/tmp/mem0_qdrant_case13_noinfer_{int(time.time())}"
    mem0_config_no_infer = {
        **mem0_config,
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection_name_no_infer,
                "embedding_model_dims": embed_dims,
                "path": qdrant_path_no_infer,
                "on_disk": True,
            },
        },
    }
    memory_no_infer = Memory.from_config(mem0_config_no_infer)
    _ = memory_no_infer.add(messages=messages, user_id=args.user_id, infer=False)

    baseline_hits = 0
    noinfer_hits = 0
    total_with_expectation = 0
    for name, q, baseline_result in base_results:
        expected = EXPECTED_KEYWORDS_BY_QUERY.get(name)
        if not expected:
            continue
        total_with_expectation += 1
        baseline_memories = extract_memories_from_result(baseline_result)
        noinfer_result = memory_no_infer.search(query=q, user_id=args.user_id, limit=args.search_limit)
        noinfer_memories = extract_memories_from_result(noinfer_result)
        baseline_ok = keyword_hit(baseline_memories, expected)
        noinfer_ok = keyword_hit(noinfer_memories, expected)
        baseline_hits += int(baseline_ok)
        noinfer_hits += int(noinfer_ok)
        print(f"[PROBE-A] {name} | expected={expected} | infer=True_hit={baseline_ok} | infer=False_hit={noinfer_ok}")

    if total_with_expectation > 0:
        print(
            f"[PROBE-A SUMMARY] infer=True={baseline_hits}/{total_with_expectation} "
            f"| infer=False={noinfer_hits}/{total_with_expectation}"
        )

    print("\n=== SELLPOINT PROBE B: metadata + filters ===")
    collection_name_meta = f"mem0_case13_meta_{int(time.time())}"
    qdrant_path_meta = f"/tmp/mem0_qdrant_case13_meta_{int(time.time())}"
    mem0_config_meta = {
        **mem0_config,
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection_name_meta,
                "embedding_model_dims": embed_dims,
                "path": qdrant_path_meta,
                "on_disk": True,
            },
        },
    }
    memory_meta = Memory.from_config(mem0_config_meta)
    probe_user = f"{args.user_id}_meta_probe"
    memory_meta.add(
        messages="我最讨厌香菜，点外卖一定不要香菜。",
        user_id=probe_user,
        infer=False,
        metadata={"topic": "food_preference", "source": "probe"},
    )
    memory_meta.add(
        messages="我在星云科技做产品经理，负责AI机器人方向。",
        user_id=probe_user,
        infer=False,
        metadata={"topic": "work_profile", "source": "probe"},
    )
    memory_meta.add(
        messages="我家的钥匙在厨房门后的挂钩上。",
        user_id=probe_user,
        infer=False,
        metadata={"topic": "home_habit", "source": "probe"},
    )
    q = "帮我点个午饭，别踩雷。"
    no_filter = memory_meta.search(query=q, user_id=probe_user, limit=5)
    with_filter = memory_meta.search(
        query=q,
        user_id=probe_user,
        limit=5,
        filters={"topic": {"eq": "food_preference"}},
    )
    print("[PROBE-B] query:", q)
    print("[PROBE-B] no_filter:")
    print(json.dumps(no_filter, ensure_ascii=False, indent=2))
    print("[PROBE-B] with_filter(topic=food_preference):")
    print(json.dumps(with_filter, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
