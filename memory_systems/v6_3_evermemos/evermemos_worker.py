#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JSON_PREFIX = "__JSON__"
STATE: dict[str, Any] = {}


def _emit(payload: dict[str, Any]) -> None:
    print(JSON_PREFIX + json.dumps(_to_jsonable(payload), ensure_ascii=False), flush=True)


def _to_jsonable(x: Any) -> Any:
    if isinstance(x, datetime):
        return x.isoformat()
    if hasattr(x, "model_dump"):
        return x.model_dump()
    if hasattr(x, "dict"):
        return x.dict()
    if isinstance(x, list):
        return [_to_jsonable(i) for i in x]
    if isinstance(x, dict):
        return {k: _to_jsonable(v) for k, v in x.items()}
    return x


def _patch_runtime(hard_message_limit: int, hard_token_limit: int) -> None:
    from memory_layer.memcell_extractor.conv_memcell_extractor import ConvMemCellExtractor
    orig_init = ConvMemCellExtractor.__init__

    def patched_init(self, llm_provider, *args, **kwargs):
        kwargs["hard_message_limit"] = int(hard_message_limit)
        kwargs["hard_token_limit"] = int(hard_token_limit)
        return orig_init(self, llm_provider, *args, **kwargs)

    def patched_count_tokens(self, message_dict_list):
        total = 0
        for msg in message_dict_list or []:
            if isinstance(msg, dict):
                total += len(str(msg.get("content", "")))
            else:
                total += len(str(msg))
        return max(1, total // 2) if total else 0

    ConvMemCellExtractor.__init__ = patched_init
    ConvMemCellExtractor._count_tokens = patched_count_tokens

    from infra_layer.adapters.out.persistence.repository.conversation_status_raw_repository import (
        ConversationStatusRawRepository,
    )
    from infra_layer.adapters.out.persistence.document.memory.conversation_status import (
        ConversationStatus,
    )

    async def raw_get_by_group_id(self, group_id, session=None):
        coll = self.model.get_pymongo_collection()
        doc = await coll.find_one({"group_id": group_id}, session=session)
        if not doc:
            return None
        doc.pop("_id", None)
        doc.pop("revision_id", None)
        return ConversationStatus(**doc)

    async def raw_upsert_by_group_id(self, group_id, update_data, session=None):
        coll = self.model.get_pymongo_collection()
        now = datetime.now(timezone.utc)
        payload = {"group_id": group_id, **update_data, "updated_at": now}
        existing = await coll.find_one({"group_id": group_id}, session=session)
        if existing:
            await coll.update_one({"group_id": group_id}, {"$set": payload}, session=session)
        else:
            payload["created_at"] = now
            payload["deleted_at"] = None
            await coll.insert_one(payload, session=session)
        doc = await coll.find_one({"group_id": group_id}, session=session)
        doc.pop("_id", None)
        doc.pop("revision_id", None)
        return ConversationStatus(**doc)

    ConversationStatusRawRepository.get_by_group_id = raw_get_by_group_id
    ConversationStatusRawRepository.upsert_by_group_id = raw_upsert_by_group_id

    import biz_layer.mem_memorize as mm
    from core.di import get_bean_by_type
    from api_specs.memory_types import MemoryType
    from infra_layer.adapters.out.persistence.repository.episodic_memory_raw_repository import EpisodicMemoryRawRepository
    from infra_layer.adapters.out.persistence.repository.foresight_record_repository import ForesightRecordRawRepository
    from infra_layer.adapters.out.persistence.repository.event_log_record_raw_repository import EventLogRecordRawRepository
    from infra_layer.adapters.out.persistence.repository.group_user_profile_memory_raw_repository import GroupUserProfileMemoryRawRepository
    from infra_layer.adapters.out.persistence.repository.group_profile_raw_repository import GroupProfileRawRepository

    async def save_memory_docs_mongo_only(doc_payloads, version=None):
        grouped_docs: dict[MemoryType, list[Any]] = defaultdict(list)
        for payload in doc_payloads:
            if payload and payload.doc:
                grouped_docs[payload.memory_type].append(payload.doc)

        saved_result: dict[MemoryType, list[Any]] = {}

        episodic_docs = grouped_docs.get(MemoryType.EPISODIC_MEMORY, [])
        if episodic_docs:
            episodic_repo = get_bean_by_type(EpisodicMemoryRawRepository)
            saved_result[MemoryType.EPISODIC_MEMORY] = [
                await episodic_repo.append_episodic_memory(doc) for doc in episodic_docs
            ]

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
                with suppress(Exception):
                    await mm._save_profile_memory_to_group_user_profile_memory(profile_mem, group_user_profile_repo, version)
                    saved_profiles.append(profile_mem)
            if saved_profiles:
                saved_result[MemoryType.PROFILE] = saved_profiles

        group_profile_docs = grouped_docs.get(MemoryType.GROUP_PROFILE, [])
        if group_profile_docs:
            group_profile_repo = get_bean_by_type(GroupProfileRawRepository)
            saved_group_profiles = []
            for mem in group_profile_docs:
                with suppress(Exception):
                    await mm._save_group_profile_memory(mem, group_profile_repo, version)
                    saved_group_profiles.append(mem)
            if saved_group_profiles:
                saved_result[MemoryType.GROUP_PROFILE] = saved_group_profiles

        return saved_result

    mm.save_memory_docs = save_memory_docs_mongo_only


async def _startup(payload: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(str(payload["repo_root"])).expanduser().resolve()
    src = repo_root / "src"
    os.chdir(repo_root)
    sys.path = [str(repo_root), str(src)] + [p for p in sys.path if "/Users/admin/work/agent_loop" not in p]

    env_overrides = {
        "MONGODB_HOST": str(payload.get("mongodb_host", "127.0.0.1")),
        "MONGODB_PORT": str(payload.get("mongodb_port", "27017")),
        "MONGODB_DATABASE": str(payload["mongodb_database"]),
        "MONGODB_USERNAME": str(payload.get("mongodb_username", "")),
        "MONGODB_PASSWORD": str(payload.get("mongodb_password", "")),
        "MONGODB_URI_PARAMS": str(payload.get("mongodb_uri_params", "")),
        "MOCK_MODE": "false",
        "LLM_PROVIDER": str(payload.get("llm_provider", "openai")),
        "LLM_MODEL": str(payload["llm_model"]),
        "LLM_BASE_URL": str(payload["llm_base_url"]),
        "LLM_API_KEY": str(payload["llm_api_key"]),
        "LLM_TEMPERATURE": str(payload.get("llm_temperature", 0.3)),
        "LLM_MAX_TOKENS": str(payload.get("llm_max_tokens", 32768)),
        "VECTORIZE_PROVIDER": str(payload.get("vectorize_provider", "openai")),
        "VECTORIZE_API_KEY": str(payload["vectorize_api_key"]),
        "VECTORIZE_BASE_URL": str(payload["vectorize_base_url"]),
        "VECTORIZE_MODEL": str(payload["vectorize_model"]),
        "VECTORIZE_FALLBACK_PROVIDER": str(payload.get("vectorize_fallback_provider", "none")),
        "VECTORIZE_TIMEOUT": str(payload.get("vectorize_timeout", 30)),
        "VECTORIZE_MAX_RETRIES": str(payload.get("vectorize_max_retries", 1)),
        "VECTORIZE_BATCH_SIZE": str(payload.get("vectorize_batch_size", 8)),
        "VECTORIZE_MAX_CONCURRENT": str(payload.get("vectorize_max_concurrent", 2)),
        "VECTORIZE_ENCODING_FORMAT": str(payload.get("vectorize_encoding_format", "float")),
        "VECTORIZE_DIMENSIONS": str(payload.get("vectorize_dimensions", 2048)),
        "RERANK_PROVIDER": str(payload.get("rerank_provider", "none")),
        "MEMORY_LANGUAGE": str(payload.get("memory_language", "en")),
    }
    os.environ.update(env_overrides)

    from common_utils.load_env import setup_environment
    setup_environment(load_env_file_name=str(payload.get("env_file", ".env")), check_env_var="MONGODB_HOST", service_name="agent_loop_evermemos")
    os.environ.update(env_overrides)

    from application_startup import setup_all
    setup_all(load_entrypoints=True)
    _patch_runtime(int(payload.get("hard_message_limit", 8)), int(payload.get("hard_token_limit", 8192)))

    from core.lifespan.mongodb_lifespan import MongoDBLifespanProvider

    class _FakeState:
        pass

    class _FakeApp:
        state = _FakeState()

    fake_app = _FakeApp()
    mongo_life = MongoDBLifespanProvider()
    await mongo_life.startup(fake_app)

    from agentic_layer.memory_manager import MemoryManager
    from service.memory_request_log_service import MemoryRequestLogService
    from service.conversation_meta_service import ConversationMetaService

    STATE.update(
        repo_root=str(repo_root),
        fake_app=fake_app,
        mongo_life=mongo_life,
        memory_manager=MemoryManager(),
        request_log_service=MemoryRequestLogService(),
        conversation_meta_service=ConversationMetaService(),
        initialized_groups=set(),
        startup_payload=payload,
    )
    return {"ok": True, "repo_root": str(repo_root), "mongodb_database": os.environ['MONGODB_DATABASE']}


async def _ensure_group(payload: dict[str, Any]) -> dict[str, Any]:
    from api_specs.dtos.conversation_meta import ConversationMetaCreateRequest
    from common_utils.datetime_utils import get_timezone

    group_id = str(payload["group_id"])
    if group_id in STATE["initialized_groups"]:
        return {"ok": True, "created": False, "group_id": group_id}

    scene = str(payload.get("scene", "assistant"))
    user_id = str(payload["user_id"])
    user_name = str(payload.get("user_name", "用户"))
    assistant_id = str(payload.get("assistant_id", "assistant_bot"))
    assistant_name = str(payload.get("assistant_name", "assistant"))
    timezone_name = str(payload.get("timezone", "Asia/Shanghai")) or get_timezone().key

    req = ConversationMetaCreateRequest(
        version="1.0.0",
        scene=scene,
        scene_desc={},
        name=str(payload.get("group_name", group_id)),
        description=str(payload.get("description", "agent_loop_evermemos")),
        group_id=group_id,
        created_at=str(payload.get("created_at") or datetime.now().astimezone().isoformat()),
        default_timezone=timezone_name,
        user_details={
            user_id: {"full_name": user_name, "role": "user", "extra": {}},
            assistant_id: {"full_name": assistant_name, "role": "assistant", "extra": {}},
        },
        tags=["agent_loop", "v6.3", "evermemos"],
    )
    resp = await STATE["conversation_meta_service"].save(req)
    STATE["initialized_groups"].add(group_id)
    return {"ok": True, "created": bool(resp), "group_id": group_id, "scene": scene}


async def _memorize(payload: dict[str, Any]) -> dict[str, Any]:
    from api_specs.request_converter import convert_simple_message_to_memorize_request
    from core.context.context import set_current_app_info, clear_current_app_info

    await _ensure_group(payload)
    message_id = str(payload["message_id"])
    req_payload = {
        "group_id": str(payload["group_id"]),
        "group_name": str(payload.get("group_name", payload["group_id"])),
        "message_id": message_id,
        "create_time": str(payload["create_time"]),
        "sender": str(payload["sender"]),
        "sender_name": str(payload["sender_name"]),
        "role": str(payload["role"]),
        "content": str(payload["content"]),
        "refer_list": [],
    }
    token = set_current_app_info({"request_id": f"evermemos_{message_id}"})
    try:
        req = await convert_simple_message_to_memorize_request(req_payload)
        await STATE["request_log_service"].save_request_logs(
            request=req,
            version="agent_loop_v63",
            endpoint_name="evermemos_worker",
            method="SCRIPT",
            url="local://evermemos_worker",
            raw_input_dict=req_payload,
        )
        count = await STATE["memory_manager"].memorize(req)
        return {"ok": True, "count": int(count or 0), "message_id": message_id}
    finally:
        clear_current_app_info(token)


async def _fetch(payload: dict[str, Any]) -> dict[str, Any]:
    from api_specs.dtos.memory import FetchMemRequest
    from api_specs.memory_models import MemoryType as FetchMemoryType

    mem_type = FetchMemoryType(str(payload.get("memory_type", "episodic_memory")))
    req = FetchMemRequest(
        user_id=str(payload.get("user_id") or ""),
        group_id=str(payload.get("group_id") or ""),
        memory_type=mem_type,
        limit=int(payload.get("limit", 100) or 100),
        offset=int(payload.get("offset", 0) or 0),
    )
    resp = await STATE["memory_manager"].fetch_mem(req)
    return {"ok": True, "memory_type": mem_type.value, "result": _to_jsonable(resp)}


async def _handle(cmd: dict[str, Any]) -> dict[str, Any]:
    op = str(cmd.get("cmd", "")).strip()
    if op == "startup":
        return await _startup(cmd)
    if not STATE:
        return {"ok": False, "error": "worker not initialized"}
    if op == "ensure_group":
        return await _ensure_group(cmd)
    if op == "memorize":
        return await _memorize(cmd)
    if op == "fetch":
        return await _fetch(cmd)
    if op == "close":
        mongo_life = STATE.get("mongo_life")
        fake_app = STATE.get("fake_app")
        if mongo_life and fake_app:
            with suppress(Exception):
                await mongo_life.shutdown(fake_app)
        return {"ok": True, "closed": True}
    return {"ok": False, "error": f"unknown cmd: {op}"}


async def amain() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            _emit({"ok": False, "error": f"invalid json: {exc}"})
            continue
        try:
            result = await _handle(cmd)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": repr(exc)}
        _emit(result)
        if cmd.get("cmd") == "close":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
