#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_BENCHMARK_PATH = Path(
    "/Users/admin/work/agent_loop/tests/research/memory/data/agent_memory_case13_shared.md"
)
EVERMEMOS_ROOT = Path("/tmp/memory_scan_round2/EverMemOS")
EVERMEMOS_SRC = EVERMEMOS_ROOT / "src"

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


def print_input_dialogue(messages: list[dict[str, str]]) -> None:
    print("\n=== INPUT DIALOGUE (FULL) ===")
    for idx, msg in enumerate(messages, 1):
        print(f"{idx:02d}. ({msg['role']}) {msg['content']}")


def _to_jsonable(x: Any) -> Any:
    if hasattr(x, "model_dump"):
        return x.model_dump()
    if hasattr(x, "dict"):
        return x.dict()
    if isinstance(x, list):
        return [_to_jsonable(i) for i in x]
    if isinstance(x, dict):
        return {k: _to_jsonable(v) for k, v in x.items()}
    return x


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-path", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--benchmark-case", default="auto")
    parser.add_argument("--benchmark-max-messages", type=int, default=80)
    parser.add_argument("--retrieve-query-set", choices=["single", "daily_habits"], default="daily_habits")
    parser.add_argument("--retrieve-query", default="请回忆我在这组对话里的关键偏好、工作信息和近期计划。")
    parser.add_argument("--max-retrieve-cases", type=int, default=0)
    parser.add_argument("--user-id", default="u_case13_evermemos")
    parser.add_argument("--group-id", default=f"g_case13_{int(time.time())}")
    parser.add_argument("--group-name", default="case13_group")
    parser.add_argument("--hard-message-limit", type=int, default=8)
    parser.add_argument("--hard-token-limit", type=int, default=8192)
    args = parser.parse_args()

    if not EVERMEMOS_SRC.exists():
        raise SystemExit(f"EverMemOS src not found: {EVERMEMOS_SRC}")

    sys.path.insert(0, str(EVERMEMOS_SRC))

    # Keep this run real for extraction/storage, but disable external index sync (ES/Milvus)
    os.environ.setdefault("MONGODB_HOST", "127.0.0.1")
    os.environ.setdefault("MONGODB_PORT", "27017")
    os.environ.setdefault("MONGODB_DATABASE", "memsys")
    os.environ.setdefault("MONGODB_USERNAME", "")
    os.environ.setdefault("MONGODB_PASSWORD", "")
    os.environ.setdefault("MONGODB_URI_PARAMS", "")
    os.environ.setdefault("MOCK_MODE", "true")
    minimax_key = (os.getenv("MINIMAX_API_KEY") or "").strip()
    if minimax_key:
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_MODEL"] = "MiniMax-M2.5"
        os.environ["LLM_BASE_URL"] = "https://api.minimaxi.com/v1"
        os.environ["LLM_API_KEY"] = minimax_key

    from common_utils.load_env import setup_environment

    setup_environment(load_env_file_name=".env", check_env_var="MONGODB_HOST", service_name="memory_probe")

    from application_startup import setup_all
    setup_all(load_entrypoints=True)
    from memory_layer.memcell_extractor.conv_memcell_extractor import ConvMemCellExtractor
    _orig_extractor_init = ConvMemCellExtractor.__init__

    def _patched_extractor_init(self, llm_provider, *init_args, **init_kwargs):
        init_kwargs["hard_message_limit"] = int(args.hard_message_limit)
        init_kwargs["hard_token_limit"] = int(args.hard_token_limit)
        return _orig_extractor_init(self, llm_provider, *init_args, **init_kwargs)

    ConvMemCellExtractor.__init__ = _patched_extractor_init
    print(
        f"[CONFIG] hard_message_limit={args.hard_message_limit} "
        f"hard_token_limit={args.hard_token_limit}"
    )

    # Initialize only MongoDB lifecycle required by extraction/storage
    from core.lifespan.mongodb_lifespan import MongoDBLifespanProvider

    class _FakeState:
        pass

    class _FakeApp:
        state = _FakeState()

    fake_app = _FakeApp()
    mongo_life = MongoDBLifespanProvider()
    await mongo_life.startup(fake_app)

    # Monkey patch save_memory_docs to keep Mongo path only (no ES/Milvus hard dependency)
    import biz_layer.mem_memorize as mm
    from collections import defaultdict
    from core.di import get_bean_by_type
    from api_specs.memory_types import MemoryType
    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import EpisodicMemoryRawRepository
    from infra_layer.adapters.out.persistence.repository.foresight_record_repository import ForesightRecordRawRepository
    from infra_layer.adapters.out.persistence.repository.event_log_record_raw_repository import EventLogRecordRawRepository
    from infra_layer.adapters.out.persistence.repository.group_user_profile_memory_raw_repository import GroupUserProfileMemoryRawRepository
    from infra_layer.adapters.out.persistence.repository.group_profile_raw_repository import GroupProfileRawRepository

    async def _save_memory_docs_mongo_only(doc_payloads, version=None):
        grouped_docs: dict[MemoryType, list[Any]] = defaultdict(list)
        for payload in doc_payloads:
            if payload and payload.doc:
                grouped_docs[payload.memory_type].append(payload.doc)

        saved_result: dict[MemoryType, list[Any]] = {}

        episodic_docs = grouped_docs.get(MemoryType.EPISODIC_MEMORY, [])
        if episodic_docs:
            episodic_repo = get_bean_by_type(EpisodicMemoryRawRepository)
            saved_episodic = []
            for doc in episodic_docs:
                saved_episodic.append(await episodic_repo.append_episodic_memory(doc))
            saved_result[MemoryType.EPISODIC_MEMORY] = saved_episodic

        foresight_docs = grouped_docs.get(MemoryType.FORESIGHT, [])
        if foresight_docs:
            foresight_repo = get_bean_by_type(ForesightRecordRawRepository)
            saved_result[MemoryType.FORESIGHT] = await foresight_repo.create_batch(foresight_docs)

        event_log_docs = grouped_docs.get(MemoryType.EVENT_LOG, [])
        if event_log_docs:
            event_log_repo = get_bean_by_type(EventLogRecordRawRepository)
            saved_result[MemoryType.EVENT_LOG] = await event_log_repo.create_batch(event_log_docs)

        profile_docs = grouped_docs.get(MemoryType.PROFILE, [])
        if profile_docs:
            group_user_profile_repo = get_bean_by_type(GroupUserProfileMemoryRawRepository)
            saved_profiles = []
            for profile_mem in profile_docs:
                try:
                    await mm._save_profile_memory_to_group_user_profile_memory(profile_mem, group_user_profile_repo, version)
                    saved_profiles.append(profile_mem)
                except Exception as exc:
                    print(f"[WARN] save profile failed: {exc}")
            if saved_profiles:
                saved_result[MemoryType.PROFILE] = saved_profiles

        group_profile_docs = grouped_docs.get(MemoryType.GROUP_PROFILE, [])
        if group_profile_docs:
            group_profile_repo = get_bean_by_type(GroupProfileRawRepository)
            saved_group_profiles = []
            for mem in group_profile_docs:
                try:
                    await mm._save_group_profile_memory(mem, group_profile_repo, version)
                    saved_group_profiles.append(mem)
                except Exception as exc:
                    print(f"[WARN] save group_profile failed: {exc}")
            if saved_group_profiles:
                saved_result[MemoryType.GROUP_PROFILE] = saved_group_profiles

        return saved_result

    mm.save_memory_docs = _save_memory_docs_mongo_only

    from api_specs.request_converter import convert_simple_message_to_memorize_request
    from agentic_layer.memory_manager import MemoryManager
    from api_specs.dtos.memory import FetchMemRequest
    from api_specs.memory_models import MemoryType as FetchMemoryType
    from service.memory_request_log_service import MemoryRequestLogService
    from core.context.context import set_current_app_info, clear_current_app_info

    benchmark_path = Path(args.benchmark_path).expanduser().resolve()
    messages = parse_case_messages_from_benchmark(
        benchmark_path=benchmark_path,
        case=args.benchmark_case,
        max_messages=args.benchmark_max_messages,
    )

    print(f"[BENCHMARK] path={benchmark_path}")
    print(f"[BENCHMARK] case={args.benchmark_case} | parsed_messages={len(messages)}")
    print(f"[GROUP] group_id={args.group_id} user_id={args.user_id}")
    print_input_dialogue(messages)

    mgr = MemoryManager()
    req_log_service = MemoryRequestLogService()
    app_info_token = set_current_app_info({"request_id": f"case13_req_{int(time.time())}"})

    print("\n=== MEMORIZE REQUESTS (FULL) ===")
    per_message_payloads: list[dict[str, Any]] = []
    per_turn_results: list[dict[str, Any]] = []
    total_extracted = 0
    for idx, msg in enumerate(messages, 1):
        sender = args.user_id if msg["role"] == "user" else "assistant_bot"
        sender_name = "李明" if msg["role"] == "user" else "assistant"
        create_time = f"2026-02-28T09:{idx // 60:02d}:{idx % 60:02d}+08:00"
        payload = {
            "group_id": args.group_id,
            "group_name": args.group_name,
            "message_id": f"m_{idx:03d}",
            "create_time": create_time,
            "sender": sender,
            "sender_name": sender_name,
            "role": msg["role"],
            "content": msg["content"],
            "refer_list": [],
        }
        per_message_payloads.append(payload)
        req = await convert_simple_message_to_memorize_request(payload)
        await req_log_service.save_request_logs(
            request=req,
            version="case13_probe",
            endpoint_name="run_evermemos_case13_real",
            method="SCRIPT",
            url="local://run_evermemos_case13_real",
            raw_input_dict=payload,
        )
        extracted_count = await mgr.memorize(req)
        extracted_int = int(extracted_count or 0)
        total_extracted += extracted_int
        per_turn_results.append(
            {
                "turn": idx,
                "role": msg["role"],
                "message_id": payload["message_id"],
                "extracted_count": extracted_int,
            }
        )
        print(
            json.dumps(
                {
                    "turn": idx,
                    "message_id": payload["message_id"],
                    "role": msg["role"],
                    "extracted_count": extracted_int,
                },
                ensure_ascii=False,
            )
        )

    print(json.dumps(per_message_payloads, ensure_ascii=False, indent=2))
    print("\n=== MEMORIZE TURN RESULTS ===")
    print(json.dumps(per_turn_results, ensure_ascii=False, indent=2))

    print("\n=== MEMORIZE SUMMARY ===")
    print(json.dumps({"total_extracted": total_extracted}, ensure_ascii=False, indent=2))

    async def _fetch(mem_type: FetchMemoryType):
        req = FetchMemRequest(
            user_id=args.user_id,
            group_id=args.group_id,
            memory_type=mem_type,
            limit=500,
            offset=0,
        )
        resp = await mgr.fetch_mem(req)
        return _to_jsonable(resp)

    fetch_types = [
        FetchMemoryType.EPISODIC_MEMORY,
        FetchMemoryType.EVENT_LOG,
        FetchMemoryType.FORESIGHT,
        FetchMemoryType.PROFILE,
        FetchMemoryType.PREFERENCE,
        FetchMemoryType.BASE_MEMORY,
    ]

    all_fetched: dict[str, Any] = {}
    print("\n=== FETCH RESULT BY TYPE (FULL) ===")
    for t in fetch_types:
        data = await _fetch(t)
        all_fetched[t.value] = data
        print(f"\n--- FETCH {t.value} ---")
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    corpus = json.dumps(all_fetched, ensure_ascii=False, default=str)

    if args.retrieve_query_set == "daily_habits":
        retrieve_cases = parse_daily_habit_queries_from_benchmark(benchmark_path)
        if not retrieve_cases:
            retrieve_cases = DAILY_HABIT_RETRIEVE_CASES
    else:
        retrieve_cases = [{"name": "single", "query": args.retrieve_query}]

    if args.max_retrieve_cases > 0:
        retrieve_cases = retrieve_cases[: args.max_retrieve_cases]

    print("\n=== RETRIEVE SUMMARY ===")
    print(f"total_cases={len(retrieve_cases)}")

    for i, case in enumerate(retrieve_cases, 1):
        name = case["name"]
        query = case["query"]
        expected = EXPECTED_KEYWORDS_BY_QUERY.get(name, [])
        hit_keywords = [kw for kw in expected if kw in corpus]
        ok = len(hit_keywords) > 0 if expected else False

        print(f"\n=== RETRIEVE CASE {i}/{len(retrieve_cases)}: {name} ===")
        print("query:", query)
        print(json.dumps({
            "expected_keywords": expected,
            "hit_keywords": hit_keywords,
            "pass": ok,
        }, ensure_ascii=False, indent=2))

    clear_current_app_info(app_info_token)
    await mongo_life.shutdown(fake_app)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
