from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import subprocess
import atexit
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Protocol
from uuid import uuid4

from openai import OpenAI

from core.types import Message


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokenize(text: str) -> List[str]:
    lowered = (text or "").lower()
    parts = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", lowered)
    tokens: List[str] = []
    for part in parts:
        tokens.append(part)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            chars = [ch for ch in part if ch.strip()]
            tokens.extend(chars)
            if len(chars) >= 2:
                tokens.extend("".join(chars[i : i + 2]) for i in range(len(chars) - 1))
    return tokens


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _resolve_api_key(*, api_key: str | None, api_key_env: str | None) -> str:
    if api_key and api_key.strip():
        return api_key.strip()
    if api_key_env:
        candidate = os.environ.get(api_key_env, "").strip()
        if candidate:
            return candidate
    fallback = os.environ.get("OPENAI_API_KEY", "").strip()
    if fallback:
        return fallback
    env_name = api_key_env or "OPENAI_API_KEY"
    raise ValueError(f"Missing API key for memory backend. Set {env_name} or config.api_key.")


def _resolve_relative_time(value: str, *, now_local: datetime) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("/", "-")
    if re.match(r"^\d{4}-\d{2}-\d{2}", normalized):
        return normalized
    day = now_local.date()
    mapping = {
        "今天": day,
        "今日": day,
        "昨天": day - timedelta(days=1),
        "昨日": day - timedelta(days=1),
        "前天": day - timedelta(days=2),
        "明天": day + timedelta(days=1),
        "后天": day + timedelta(days=2),
    }
    if normalized in mapping:
        return mapping[normalized].isoformat()
    return raw


@dataclass
class MemoryToolEvent:
    tool_name: str
    arguments: Dict[str, Any]
    result_preview: str
    duration_ms: int | None = None
    ok: bool = True


@dataclass
class PassiveTurnStartEvent:
    workspace_path: str
    session_id: str
    user_input: str
    recent_messages: List[Message]
    now_local: str
    now_utc: str
    timezone: str


@dataclass
class PassiveTurnEndEvent:
    workspace_path: str
    session_id: str
    user_input: str
    assistant_text: str
    recent_messages: List[Message]
    tool_events: List[MemoryToolEvent]
    now_local: str
    now_utc: str
    timezone: str
    active_write_count: int = 0


@dataclass
class PassiveRetrieveResult:
    should_retrieve: bool
    hits: List[Dict[str, Any]] = field(default_factory=list)
    injected_context: str = ""
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PassiveWriteResult:
    should_store: bool
    mutations: List[Dict[str, Any]] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    scope: str
    content: str
    tags: List[str]
    confidence: float
    source: str
    version: int
    created_at: str
    updated_at: str
    mentioned_at: str | None = None
    occurred_at: str | None = None
    expires_at: str | None = None
    deleted_at: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.memory_type,
            "scope": self.scope,
            "content": self.content,
            "tags": list(self.tags),
            "confidence": float(self.confidence),
            "source": self.source,
            "version": int(self.version),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "mentioned_at": self.mentioned_at,
            "occurred_at": self.occurred_at,
            "expires_at": self.expires_at,
            "deleted_at": self.deleted_at,
        }

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "MemoryRecord":
        tags_raw = raw.get("tags", [])
        tags = [str(x).strip() for x in tags_raw] if isinstance(tags_raw, list) else []
        return MemoryRecord(
            id=str(raw.get("id", "")).strip(),
            memory_type=str(raw.get("type", "fact")).strip() or "fact",
            scope=str(raw.get("scope", "user")).strip() or "user",
            content=_normalize_text(str(raw.get("content", ""))),
            tags=[tag for tag in tags if tag],
            confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
            source=str(raw.get("source", "assistant")).strip() or "assistant",
            version=max(1, int(raw.get("version", 1) or 1)),
            created_at=str(raw.get("created_at", "")) or _now_utc_iso(),
            updated_at=str(raw.get("updated_at", "")) or _now_utc_iso(),
            mentioned_at=str(raw.get("mentioned_at")) if raw.get("mentioned_at") else None,
            occurred_at=str(raw.get("occurred_at")) if raw.get("occurred_at") else None,
            expires_at=str(raw.get("expires_at")) if raw.get("expires_at") else None,
            deleted_at=str(raw.get("deleted_at")) if raw.get("deleted_at") else None,
        )


class JsonlMemoryStore:
    def __init__(self, records_path: Path) -> None:
        self.records_path = records_path
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[MemoryRecord] = []
        self._load()

    def _load(self) -> None:
        self._records = []
        if not self.records_path.exists():
            return
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            src = line.strip()
            if not src:
                continue
            try:
                raw = json.loads(src)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                record = MemoryRecord.from_dict(raw)
                if record.id and record.content:
                    self._records.append(record)

    def _persist(self) -> None:
        payload = "\n".join(json.dumps(record.to_dict(), ensure_ascii=False) for record in self._records)
        self.records_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")

    @staticmethod
    def _is_alive(record: MemoryRecord) -> bool:
        if record.deleted_at:
            return False
        if record.expires_at:
            return record.expires_at > _now_utc_iso()
        return True

    def _find_by_id(self, record_id: str) -> MemoryRecord | None:
        for record in self._records:
            if record.id == record_id:
                return record
        return None

    def _find_dedupe(self, *, scope: str, memory_type: str, content: str) -> MemoryRecord | None:
        normalized = _normalize_text(content)
        for record in self._records:
            if not self._is_alive(record):
                continue
            if record.scope == scope and record.memory_type == memory_type and record.content == normalized:
                return record
        return None

    def set_record(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        tags: List[str] | None = None,
        confidence: float = 0.7,
        source: str = "assistant",
        mentioned_at: str | None = None,
        occurred_at: str | None = None,
    ) -> Dict[str, Any]:
        normalized = _normalize_text(content)
        if not normalized:
            return {"ok": False, "error": "content is required"}
        existing = self._find_dedupe(scope=scope, memory_type=memory_type, content=normalized)
        now = _now_utc_iso()
        if existing is not None:
            existing.updated_at = now
            existing.version += 1
            existing.confidence = max(existing.confidence, max(0.0, min(1.0, float(confidence))))
            if tags:
                existing.tags = sorted(set([*existing.tags, *[tag for tag in tags if tag.strip()]]))
            existing.mentioned_at = _normalize_text(mentioned_at or "") or existing.mentioned_at or now
            if occurred_at is not None:
                existing.occurred_at = _normalize_text(occurred_at) or None
            self._persist()
            return {"ok": True, "created": False, "record": existing.to_dict()}

        record = MemoryRecord(
            id=f"m_{uuid4().hex[:12]}",
            memory_type=memory_type.strip() or "fact",
            scope=scope.strip() or "user",
            content=normalized,
            tags=sorted(set([tag.strip() for tag in (tags or []) if tag and tag.strip()])),
            confidence=max(0.0, min(1.0, float(confidence))),
            source=source.strip() or "assistant",
            version=1,
            created_at=now,
            updated_at=now,
            mentioned_at=_normalize_text(mentioned_at or "") or now,
            occurred_at=_normalize_text(occurred_at or "") or None,
        )
        self._records.append(record)
        self._persist()
        return {"ok": True, "created": True, "record": record.to_dict()}

    def update_record(self, *, record_id: str, patch: Dict[str, Any], expected_version: int | None = None) -> Dict[str, Any]:
        record = self._find_by_id(record_id)
        if record is None:
            return {"ok": False, "error": "record not found"}
        if expected_version is not None and record.version != expected_version:
            return {"ok": False, "error": "version conflict", "current_version": record.version}
        now = _now_utc_iso()
        if "content" in patch:
            record.content = _normalize_text(str(patch.get("content", "")))
        if "type" in patch:
            record.memory_type = _normalize_text(str(patch.get("type", "fact"))) or "fact"
        if "scope" in patch:
            record.scope = _normalize_text(str(patch.get("scope", "user"))) or "user"
        if "tags" in patch and isinstance(patch["tags"], list):
            record.tags = sorted(set([str(x).strip() for x in patch["tags"] if str(x).strip()]))
        if "confidence" in patch:
            record.confidence = max(0.0, min(1.0, float(patch["confidence"] or 0.0)))
        if "mentioned_at" in patch:
            record.mentioned_at = _normalize_text(str(patch.get("mentioned_at", ""))) or None
        if "occurred_at" in patch:
            record.occurred_at = _normalize_text(str(patch.get("occurred_at", ""))) or None
        if "expires_at" in patch:
            record.expires_at = _normalize_text(str(patch.get("expires_at", ""))) or None
        record.updated_at = now
        record.version += 1
        self._persist()
        return {"ok": True, "updated": True, "record": record.to_dict()}

    def delete_record(self, *, record_id: str, mode: str = "soft", expected_version: int | None = None) -> Dict[str, Any]:
        record = self._find_by_id(record_id)
        if record is None:
            return {"ok": False, "error": "record not found"}
        if expected_version is not None and record.version != expected_version:
            return {"ok": False, "error": "version conflict", "current_version": record.version}
        if mode == "hard":
            self._records = [row for row in self._records if row.id != record_id]
            self._persist()
            return {"ok": True, "deleted": True, "mode": "hard", "id": record_id}
        record.deleted_at = _now_utc_iso()
        record.updated_at = _now_utc_iso()
        record.version += 1
        self._persist()
        return {"ok": True, "deleted": True, "mode": "soft", "record": record.to_dict()}

    def search(
        self,
        *,
        query: str,
        scope: str | None = None,
        types: List[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        q = _normalize_text(query)
        if not q:
            return {"ok": False, "error": "query is required", "items": []}
        q_tokens = _tokenize(q)
        valid_types = set([row.strip() for row in (types or []) if row and row.strip()])
        rows: List[tuple[float, MemoryRecord]] = []
        for record in self._records:
            if not self._is_alive(record):
                continue
            if scope and record.scope != scope:
                continue
            if valid_types and record.memory_type not in valid_types:
                continue
            tokens = _tokenize(record.content + " " + " ".join(record.tags))
            if not tokens:
                continue
            overlap = len(set(q_tokens) & set(tokens))
            if overlap <= 0:
                continue
            score = overlap / max(1.0, math.sqrt(len(tokens))) + record.confidence * 0.25
            if score < float(min_score):
                continue
            rows.append((score, record))
        rows.sort(key=lambda item: item[0], reverse=True)
        return {
            "ok": True,
            "items": [
                {
                    "id": record.id,
                    "type": record.memory_type,
                    "scope": record.scope,
                    "content": record.content,
                    "tags": list(record.tags),
                    "confidence": record.confidence,
                    "version": record.version,
                    "updated_at": record.updated_at,
                    "mentioned_at": record.mentioned_at,
                    "occurred_at": record.occurred_at,
                    "score": score,
                }
                for score, record in rows[: max(1, int(top_k))]
            ],
        }

    def stats(self) -> Dict[str, Any]:
        alive = sum(1 for record in self._records if self._is_alive(record))
        return {
            "records_path": str(self.records_path),
            "records_total": len(self._records),
            "records_alive": alive,
        }


class MemoryBackend(Protocol):
    def search(self, *, query: str, scope: str | None, types: List[str] | None, top_k: int, min_score: float) -> Dict[str, Any]: ...
    def set_record(self, *, memory_type: str, scope: str, content: str, tags: List[str] | None, confidence: float, source: str, mentioned_at: str | None, occurred_at: str | None) -> Dict[str, Any]: ...
    def update_record(self, *, record_id: str, patch: Dict[str, Any], expected_version: int | None) -> Dict[str, Any]: ...
    def delete_record(self, *, record_id: str, mode: str, expected_version: int | None) -> Dict[str, Any]: ...
    def stats(self) -> Dict[str, Any]: ...


class SimpleMemBackend(JsonlMemoryStore):
    pass


class Mem0Backend(JsonlMemoryStore):
    def __init__(self, records_path: Path, actions_path: Path) -> None:
        self.actions_path = actions_path
        self.actions_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(records_path)

    def _append_action(self, action: str, payload: Dict[str, Any]) -> None:
        row = {"ts": _now_utc_iso(), "action": action, "payload": payload}
        with self.actions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")

    def set_record(self, **kwargs: Any) -> Dict[str, Any]:
        result = super().set_record(**kwargs)
        if result.get("ok"):
            self._append_action("ADD" if result.get("created") else "UPDATE", result)
        return result

    def update_record(self, **kwargs: Any) -> Dict[str, Any]:
        result = super().update_record(**kwargs)
        if result.get("ok"):
            self._append_action("UPDATE", result)
        return result

    def delete_record(self, **kwargs: Any) -> Dict[str, Any]:
        result = super().delete_record(**kwargs)
        if result.get("ok"):
            self._append_action("DELETE", result)
        return result

    def stats(self) -> Dict[str, Any]:
        base = super().stats()
        base["actions_path"] = str(self.actions_path)
        return base


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value or "").strip("._-")
    return cleaned or "default"


def _detect_openai_embedding_dims(*, base_url: str, api_key: str, model: str) -> int:
    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=30)
    response = client.embeddings.create(model=model, input=["dimension probe"])  # type: ignore[arg-type]
    return len(response.data[0].embedding)


def _extract_tags(text: str) -> List[str]:
    tags: List[str] = []
    patterns = {
        "health": ["医院", "生病", "受伤", "疼", "肿", "发烧", "膝盖"],
        "incident": ["摔", "丢", "坏了", "失败", "出错", "受伤"],
        "plan": ["准备", "打算", "一会", "今天去", "明天去", "计划"],
        "preference": ["喜欢", "不喜欢", "偏好", "习惯"],
    }
    for tag, keywords in patterns.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    return tags


def _split_atomic_clauses(text: str) -> List[str]:
    raw = _normalize_text(text)
    if not raw:
        return []
    parts = re.split(r"[。！？；;]|，(?=我|今天|明天|昨天|准备|打算|后来|然后)", raw)
    return [_normalize_text(part) for part in parts if _normalize_text(part)]


class MemoryAdapter(Protocol):
    def build_system_prompt_block(self, *, session_id: str) -> str: ...
    def passive_retrieve(self, event: PassiveTurnStartEvent) -> PassiveRetrieveResult: ...
    def passive_write(self, event: PassiveTurnEndEvent) -> PassiveWriteResult: ...
    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]: ...
    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]: ...
    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]: ...
    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]: ...
    def stats(self) -> Dict[str, Any]: ...


class BaseMemoryAdapter:
    def __init__(
        self,
        *,
        backend: MemoryBackend | None,
        system_dir: Path,
        workspace_path: str,
        artifact_dir: Path,
    ) -> None:
        self.backend = backend
        self.system_dir = system_dir
        self.workspace_path = workspace_path
        self.artifact_dir = artifact_dir
        self.policy_path = self.system_dir / "memory_policy.md"
        self.schema_path = self.system_dir / "tools_schema.json"
        self.current_session_id = "default"

    def set_session(self, session_id: str) -> None:
        self.current_session_id = session_id.strip() or "default"

    def _policy_text(self) -> str:
        if self.policy_path.exists():
            return self.policy_path.read_text(encoding="utf-8").strip()
        return "# Memory Policy\nUse memory tools when helpful."

    def _schema_text(self) -> str:
        if self.schema_path.exists():
            return self.schema_path.read_text(encoding="utf-8").strip()
        return "{}"

    def build_system_prompt_block(self, *, session_id: str) -> str:
        now_local = _now_local()
        return (
            "[Long Memory Runtime]\n"
            f"- workspace_path: {self.workspace_path}\n"
            f"- memory_artifact_dir: {self.artifact_dir}\n"
            f"- memory_session_id: {session_id}\n"
            f"- current_time_local: {now_local.isoformat(timespec='seconds')}\n"
            f"- current_time_utc: {_now_utc_iso()}\n"
            f"- timezone: {now_local.tzinfo or 'UTC'}\n"
            "- Passive retrieve/write are handled by the active memory adapter.\n"
            "- You may still use mem_get/mem_set/mem_update/mem_delete proactively.\n\n"
            "<memory_policy>\n"
            f"{self._policy_text()}\n"
            "</memory_policy>\n\n"
            "<memory_tools_contract>\n"
            f"{self._schema_text()}\n"
            "</memory_tools_contract>\n"
        )

    def _should_retrieve(self, user_input: str) -> bool:
        text = _normalize_text(user_input)
        if not text:
            return False
        trivial = ["你好", "hi", "hello", "谢谢", "好的", "在吗", "嗯"]
        if text.lower() in trivial:
            return False
        cues = ["记得", "之前", "上次", "昨天", "前天", "我现在", "还记得", "当时", "后来"]
        return any(cue in text for cue in cues) or len(text) >= 8

    def _render_hits(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["[Memory Context]"]
        for item in hits:
            when = item.get("occurred_at") or item.get("mentioned_at") or item.get("updated_at") or ""
            prefix = f"- ({item.get('type')}/{item.get('scope')}"
            if when:
                prefix += f", {when}"
            prefix += f") {item.get('content')}"
            lines.append(prefix)
        return "\n".join(lines)

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = _normalize_text(str(params.get("query", "")))
        scope = _normalize_text(str(params.get("scope", ""))) or None
        types_raw = params.get("types", [])
        types = [str(item).strip() for item in types_raw] if isinstance(types_raw, list) else []
        top_k = int(params.get("top_k", 5) or 5)
        min_score = float(params.get("min_score", 0.0) or 0.0)
        return self.backend.search(query=query, scope=scope, types=types, top_k=top_k, min_score=min_score)

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        now_local = _now_local()
        mentioned_at = _resolve_relative_time(str(params.get("mentioned_at", "")), now_local=now_local) or _now_utc_iso()
        occurred_at = _resolve_relative_time(str(params.get("occurred_at", "")), now_local=now_local)
        tags_raw = params.get("tags", [])
        tags = [str(item).strip() for item in tags_raw] if isinstance(tags_raw, list) else []
        return self.backend.set_record(
            memory_type=_normalize_text(str(params.get("type", "fact"))) or "fact",
            scope=_normalize_text(str(params.get("scope", "user"))) or "user",
            content=_normalize_text(str(params.get("content", ""))),
            tags=tags,
            confidence=float(params.get("confidence", 0.7) or 0.7),
            source=_normalize_text(str(params.get("source", "assistant"))) or "assistant",
            mentioned_at=mentioned_at,
            occurred_at=occurred_at,
        )

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        patch = params.get("patch", {})
        if not isinstance(patch, dict):
            patch = {}
        now_local = _now_local()
        if "mentioned_at" in patch:
            patch["mentioned_at"] = _resolve_relative_time(str(patch.get("mentioned_at", "")), now_local=now_local)
        if "occurred_at" in patch:
            patch["occurred_at"] = _resolve_relative_time(str(patch.get("occurred_at", "")), now_local=now_local)
        expected_version_raw = params.get("expected_version")
        expected_version = int(expected_version_raw) if expected_version_raw is not None else None
        return self.backend.update_record(
            record_id=_normalize_text(str(params.get("id", ""))),
            patch=patch,
            expected_version=expected_version,
        )

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        expected_version_raw = params.get("expected_version")
        expected_version = int(expected_version_raw) if expected_version_raw is not None else None
        return self.backend.delete_record(
            record_id=_normalize_text(str(params.get("id", ""))),
            mode=_normalize_text(str(params.get("mode", "soft"))) or "soft",
            expected_version=expected_version,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "system_dir": str(self.system_dir),
            "policy_path": str(self.policy_path),
            "schema_path": str(self.schema_path),
            "artifact_dir": str(self.artifact_dir),
            **self.backend.stats(),
        }


class SimpleMemAdapter(BaseMemoryAdapter):
    def __init__(
        self,
        *,
        system_dir: Path,
        workspace_path: str,
        artifact_dir: Path,
        api_key: str | None,
        api_key_env: str | None,
        model_name: str,
        base_url: str,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        table_name: str = "memory_entries",
        enable_planning: bool = False,
        enable_reflection: bool = False,
        hf_home: str | None = None,
        sentence_transformers_home: str | None = None,
    ) -> None:
        super().__init__(
            backend=None,
            system_dir=system_dir,
            workspace_path=workspace_path,
            artifact_dir=artifact_dir,
        )
        simplemem_module = import_module("simplemem")
        system_cls = getattr(simplemem_module, "SimpleMemSystem")
        config_cls = getattr(simplemem_module, "SimpleMemConfig")
        set_config = getattr(simplemem_module, "set_config")
        self._api_key = _resolve_api_key(api_key=api_key, api_key_env=api_key_env)
        self._db_path = self.artifact_dir / "lancedb"
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._table_name = table_name.strip() or "memory_entries"
        if hf_home:
            os.environ["HF_HOME"] = hf_home
        if sentence_transformers_home:
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = sentence_transformers_home
        sm_cfg = config_cls(
            openai_api_key=self._api_key,
            openai_base_url=base_url,
            llm_model=model_name,
            embedding_model=embedding_model,
            lancedb_path=str(self._db_path),
            memory_table_name=self._table_name,
            use_streaming=False,
            enable_thinking=False,
            use_json_format=True,
            enable_parallel_processing=False,
            enable_parallel_retrieval=False,
            enable_planning=bool(enable_planning),
            enable_reflection=bool(enable_reflection),
        )
        set_config(sm_cfg)
        self.system = system_cls(
            api_key=self._api_key,
            model=model_name,
            base_url=base_url,
            db_path=str(self._db_path),
            table_name=self._table_name,
            clear_db=False,
            enable_thinking=False,
            use_streaming=False,
            enable_planning=bool(enable_planning),
            enable_reflection=bool(enable_reflection),
            enable_parallel_processing=False,
            enable_parallel_retrieval=False,
        )

    @staticmethod
    def _entry_to_dict(entry: object) -> Dict[str, Any]:
        if hasattr(entry, "model_dump"):
            raw = entry.model_dump()
        elif hasattr(entry, "dict"):
            raw = entry.dict()
        else:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return raw

    @contextlib.contextmanager
    def _silence_simplemem(self) -> Any:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            yield buffer

    def _retrieve_entries(self, query: str) -> List[Dict[str, Any]]:
        with self._silence_simplemem():
            entries = self.system.hybrid_retriever.retrieve(query, enable_reflection=False)
        return [self._entry_to_dict(entry) for entry in entries]

    @staticmethod
    def _render_simplemem_hits(hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["[Memory Context]"]
        for item in hits:
            topic = item.get("topic") or "memory"
            timestamp = item.get("timestamp") or ""
            restatement = _normalize_text(str(item.get("lossless_restatement", "")))
            if not restatement:
                continue
            prefix = f"- ({topic}"
            if timestamp:
                prefix += f", {timestamp}"
            prefix += f") {restatement}"
            lines.append(prefix)
        return "\n".join(lines)

    def passive_retrieve(self, event: PassiveTurnStartEvent) -> PassiveRetrieveResult:
        if not self._should_retrieve(event.user_input):
            return PassiveRetrieveResult(should_retrieve=False)
        hits = self._retrieve_entries(event.user_input)
        return PassiveRetrieveResult(
            should_retrieve=bool(hits),
            hits=hits,
            injected_context=self._render_simplemem_hits(hits),
            debug={
                "adapter": "simplemem",
                "query": event.user_input,
                "db_path": str(self._db_path),
                "table_name": self._table_name,
            },
        )

    def passive_write(self, event: PassiveTurnEndEvent) -> PassiveWriteResult:
        if event.active_write_count > 0:
            return PassiveWriteResult(should_store=False, debug={"reason": "active_write_already_happened"})
        user_text = _normalize_text(event.user_input)
        assistant_text = _normalize_text(event.assistant_text)
        if not user_text and not assistant_text:
            return PassiveWriteResult(should_store=False)
        before_count = len(self.system.get_all_memories())
        with self._silence_simplemem():
            if user_text:
                self.system.add_dialogue("User", user_text, event.now_utc)
            if assistant_text:
                self.system.add_dialogue("Assistant", assistant_text, event.now_utc)
            self.system.finalize()
        all_memories = [self._entry_to_dict(entry) for entry in self.system.get_all_memories()]
        after_count = len(all_memories)
        new_entries = all_memories[before_count:]
        return PassiveWriteResult(
            should_store=after_count > before_count,
            mutations=new_entries,
            debug={
                "adapter": "simplemem",
                "db_path": str(self._db_path),
                "table_name": self._table_name,
                "memory_entries_before": before_count,
                "memory_entries_after": after_count,
            },
        )

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = _normalize_text(str(params.get("query", "")))
        if not query:
            return {"ok": False, "error": "query is required", "items": []}
        hits = self._retrieve_entries(query)
        top_k = max(1, int(params.get("top_k", 5) or 5))
        return {"ok": True, "items": hits[:top_k], "db_path": str(self._db_path), "table_name": self._table_name}

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = _normalize_text(str(params.get("content", "")))
        if not content:
            return {"ok": False, "error": "content is required"}
        speaker = "Memory"
        with self._silence_simplemem():
            self.system.add_dialogue(speaker, content, str(params.get("mentioned_at") or _now_utc_iso()))
            self.system.finalize()
        all_memories = [self._entry_to_dict(entry) for entry in self.system.get_all_memories()]
        return {
            "ok": True,
            "created": True,
            "record": all_memories[-1] if all_memories else {},
            "db_path": str(self._db_path),
            "table_name": self._table_name,
        }

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "SimpleMem backend does not expose record-level update via this runtime yet.",
        }

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "SimpleMem backend does not expose record-level delete via this runtime yet.",
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "system_dir": str(self.system_dir),
            "policy_path": str(self.policy_path),
            "schema_path": str(self.schema_path),
            "artifact_dir": str(self.artifact_dir),
            "backend_type": "simplemem_real",
            "db_path": str(self._db_path),
            "table_name": self._table_name,
            "memory_entries": len(self.system.get_all_memories()),
        }


class Mem0Adapter(BaseMemoryAdapter):
    def __init__(
        self,
        *,
        system_dir: Path,
        workspace_path: str,
        artifact_dir: Path,
        memory_user_id: str,
        api_key: str | None,
        api_key_env: str | None,
        model_name: str,
        base_url: str,
        embed_model: str = "embedding-3",
        embed_base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        embed_api_key: str | None = None,
        embed_api_key_env: str = "ZHIPU_API_KEY",
        embed_dims: int = 0,
        search_limit: int = 8,
        retrieve_top_k: int = 6,
        infer_passive_write: bool = True,
        llm_provider: str = "openai",
        embed_provider: str = "openai",
        qdrant_dir: str | None = None,
        mem0_dir: str | None = None,
    ) -> None:
        super().__init__(
            backend=None,
            system_dir=system_dir,
            workspace_path=workspace_path,
            artifact_dir=artifact_dir,
        )
        self.memory_user_id = _slugify(memory_user_id)
        self._search_limit = max(1, int(search_limit))
        self._retrieve_top_k = max(1, int(retrieve_top_k))
        self._infer_passive_write = bool(infer_passive_write)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._mem0_dir = Path(mem0_dir).expanduser() if mem0_dir else artifact_dir / ".mem0"
        self._mem0_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MEM0_DIR"] = str(self._mem0_dir)

        self._qdrant_dir = Path(qdrant_dir).expanduser() if qdrant_dir else artifact_dir / "qdrant"
        self._qdrant_dir.mkdir(parents=True, exist_ok=True)
        self._api_key = _resolve_api_key(api_key=api_key, api_key_env=api_key_env)
        self._embed_api_key = _resolve_api_key(api_key=embed_api_key, api_key_env=embed_api_key_env)
        self._embed_dims = int(embed_dims) if int(embed_dims or 0) > 0 else _detect_openai_embedding_dims(
            base_url=embed_base_url,
            api_key=self._embed_api_key,
            model=embed_model,
        )
        self._collection_name = f"mem0_{self.memory_user_id}"

        mem0_module = import_module("mem0")
        memory_cls = getattr(mem0_module, "Memory")
        mem0_config = {
            "version": "v1.1",
            "llm": {
                "provider": llm_provider,
                "config": {
                    "api_key": self._api_key,
                    "model": model_name,
                    "openai_base_url": base_url,
                    "temperature": 0.0,
                },
            },
            "embedder": {
                "provider": embed_provider,
                "config": {
                    "api_key": self._embed_api_key,
                    "model": embed_model,
                    "openai_base_url": embed_base_url,
                    "embedding_dims": self._embed_dims,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": self._collection_name,
                    "embedding_model_dims": self._embed_dims,
                    "path": str(self._qdrant_dir),
                    "on_disk": True,
                },
            },
        }
        self.memory = memory_cls.from_config(mem0_config)

    def passive_retrieve(self, event: PassiveTurnStartEvent) -> PassiveRetrieveResult:
        if not self._should_retrieve(event.user_input):
            return PassiveRetrieveResult(should_retrieve=False)
        result = self.memory.search(query=event.user_input, user_id=self.memory_user_id, limit=self._retrieve_top_k)
        hits = result.get("results", []) if isinstance(result, dict) else []
        return PassiveRetrieveResult(
            should_retrieve=bool(hits),
            hits=hits,
            injected_context=self._render_mem0_hits(hits),
            debug={"adapter": "mem0", "query": event.user_input},
        )

    def passive_write(self, event: PassiveTurnEndEvent) -> PassiveWriteResult:
        if event.active_write_count > 0:
            return PassiveWriteResult(should_store=False, debug={"reason": "active_write_already_happened"})
        messages = [
            {"role": "user", "content": event.user_input},
            {"role": "assistant", "content": event.assistant_text},
        ]
        metadata = {
            "session_id": event.session_id,
            "workspace_path": event.workspace_path,
            "tool_event_count": len(event.tool_events),
            "turn_finished_at": event.now_utc,
        }
        result = self.memory.add(
            messages=messages,
            user_id=self.memory_user_id,
            metadata=metadata,
            infer=self._infer_passive_write,
        )
        rows = result.get("results", []) if isinstance(result, dict) else []
        return PassiveWriteResult(should_store=bool(rows), mutations=rows, debug={"adapter": "mem0", "infer": self._infer_passive_write})

    @staticmethod
    def _render_mem0_hits(hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["[Memory Context]"]
        for item in hits:
            updated_at = item.get("updated_at") or item.get("created_at") or ""
            line = f"- {item.get('memory', '')}"
            if updated_at:
                line += f" ({updated_at})"
            lines.append(line)
        return "\n".join(lines)

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = _normalize_text(str(params.get("query", "")))
        top_k = int(params.get("top_k", self._search_limit) or self._search_limit)
        return self.memory.search(query=query, user_id=self.memory_user_id, limit=max(1, top_k))

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = _normalize_text(str(params.get("content", "")))
        if not content:
            return {"ok": False, "error": "content is required"}
        tags_raw = params.get("tags", [])
        metadata: Dict[str, Any] = {
            "scope": _normalize_text(str(params.get("scope", "user"))) or "user",
            "type": _normalize_text(str(params.get("type", "fact"))) or "fact",
            "source": _normalize_text(str(params.get("source", "assistant"))) or "assistant",
        }
        if isinstance(tags_raw, list) and tags_raw:
            metadata["tags"] = [str(tag).strip() for tag in tags_raw if str(tag).strip()]
        if params.get("mentioned_at"):
            metadata["mentioned_at"] = str(params.get("mentioned_at"))
        if params.get("occurred_at"):
            metadata["occurred_at"] = str(params.get("occurred_at"))
        if params.get("confidence") is not None:
            metadata["confidence"] = float(params.get("confidence") or 0.0)
        result = self.memory.add(
            messages=[{"role": "assistant", "content": content}],
            user_id=self.memory_user_id,
            metadata=metadata,
            infer=False,
        )
        return {"ok": True, **result}

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        record_id = _normalize_text(str(params.get("id", "")))
        patch = params.get("patch", {})
        if not record_id:
            return {"ok": False, "error": "id is required"}
        if not isinstance(patch, dict):
            return {"ok": False, "error": "patch must be an object"}
        content = _normalize_text(str(patch.get("content", "")))
        if not content:
            return {"ok": False, "error": "Mem0 runtime currently supports content-only update"}
        result = self.memory.update(memory_id=record_id, data=content)
        return {"ok": True, **result}

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        record_id = _normalize_text(str(params.get("id", "")))
        if not record_id:
            return {"ok": False, "error": "id is required"}
        result = self.memory.delete(memory_id=record_id)
        return {"ok": True, **result}

    def stats(self) -> Dict[str, Any]:
        all_rows = self.memory.get_all(user_id=self.memory_user_id, limit=200)
        results = all_rows.get("results", []) if isinstance(all_rows, dict) else []
        return {
            "system_dir": str(self.system_dir),
            "policy_path": str(self.policy_path),
            "schema_path": str(self.schema_path),
            "artifact_dir": str(self.artifact_dir),
            "backend_type": "mem0_real",
            "memory_user_id": self.memory_user_id,
            "mem0_dir": str(self._mem0_dir),
            "qdrant_dir": str(self._qdrant_dir),
            "collection_name": self._collection_name,
            "embedding_dims": self._embed_dims,
            "records_total": len(results),
        }


class OpenVikingWorkerClient:
    def __init__(
        self,
        *,
        python_bin: str,
        worker_script: Path,
        log_path: Path,
        startup_payload: Dict[str, Any],
    ) -> None:
        self.python_bin = python_bin
        self.worker_script = worker_script
        self.log_path = log_path
        self.startup_payload = startup_payload
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = self.log_path.open("a", encoding="utf-8")
        self._proc = subprocess.Popen(
            [self.python_bin, str(self.worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            text=True,
            bufsize=1,
        )
        atexit.register(self.close)
        startup = self.call({"cmd": "startup", **self.startup_payload})
        if not startup.get("ok"):
            raise RuntimeError(f"OpenViking worker startup failed: {startup}")

    def call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("OpenViking worker stdio unavailable")
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"OpenViking worker exited unexpectedly; see {self.log_path}")
            row = line.rstrip("\n")
            if not row.startswith("__JSON__"):
                continue
            return json.loads(row[len("__JSON__") :])

    def close(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                if proc.stdin is not None:
                    try:
                        proc.stdin.write(json.dumps({"cmd": "close"}, ensure_ascii=False) + "\n")
                        proc.stdin.flush()
                    except Exception:
                        pass
                proc.wait(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()
        self._proc = None
        with contextlib.suppress(Exception):
            self._stderr_handle.close()


class OpenVikingAdapter(BaseMemoryAdapter):
    def __init__(
        self,
        *,
        system_dir: Path,
        workspace_path: str,
        artifact_dir: Path,
        memory_user_id: str,
        api_key: str | None,
        api_key_env: str | None,
        model_name: str,
        base_url: str,
        python_bin: str = "/Users/admin/miniconda3/envs/py312/bin/python",
        embed_model: str = "embedding-3",
        embed_base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        embed_api_key: str | None = None,
        embed_api_key_env: str = "ZHIPU_API_KEY",
        embed_dim: int = 1024,
        search_limit: int = 8,
        retrieve_top_k: int = 5,
        score_threshold: float | None = None,
        user_memory_uri: str = "viking://user/default/memories",
        find_fallback: bool = True,
        commit_wait_timeout: float = 180.0,
        default_search_mode: str = "quick",
    ) -> None:
        super().__init__(
            backend=None,
            system_dir=system_dir,
            workspace_path=workspace_path,
            artifact_dir=artifact_dir,
        )
        self.memory_user_id = _slugify(memory_user_id)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_dir = self.artifact_dir / "workspace"
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        self._python_bin = python_bin
        self._search_limit = max(1, int(search_limit))
        self._retrieve_top_k = max(1, int(retrieve_top_k))
        self._score_threshold = score_threshold
        self._user_memory_uri = user_memory_uri
        self._find_fallback = bool(find_fallback)
        self._commit_wait_timeout = float(commit_wait_timeout)
        self._default_search_mode = str(default_search_mode or "quick")
        self._api_key = _resolve_api_key(api_key=api_key, api_key_env=api_key_env)
        self._embed_api_key = _resolve_api_key(api_key=embed_api_key, api_key_env=embed_api_key_env)
        self._worker_log = self.artifact_dir / "openviking_worker.log"
        self._worker = OpenVikingWorkerClient(
            python_bin=self._python_bin,
            worker_script=self.system_dir / "openviking_worker.py",
            log_path=self._worker_log,
            startup_payload={
                "workspace": str(self._workspace_dir),
                "artifact_dir": str(self.artifact_dir),
                "llm_model": model_name,
                "llm_base_url": base_url,
                "llm_api_key": self._api_key,
                "embed_model": embed_model,
                "embed_base_url": embed_base_url,
                "embed_api_key": self._embed_api_key,
                "embed_dim": int(embed_dim),
                "default_search_mode": self._default_search_mode,
            },
        )

    @staticmethod
    def _sanitize_memory_text(text: str, *, limit: int = 500) -> str:
        normalized = _normalize_text(text)
        if not normalized:
            return ""
        normalized = re.sub(r"`{3}.*?`{3}", "[code omitted]", normalized, flags=re.DOTALL)
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip() + " ..."

    def _ensure_session(self, session_id: str) -> Dict[str, Any]:
        return self._worker.call({"cmd": "ensure_session", "session_id": session_id})

    @staticmethod
    def _normalize_hit(item: Dict[str, Any], content: str) -> Dict[str, Any]:
        return {
            "uri": item.get("uri", ""),
            "type": "memory",
            "scope": "user",
            "category": item.get("category", ""),
            "content": _normalize_text(content or item.get("abstract", "")),
            "abstract": _normalize_text(str(item.get("abstract", ""))),
            "score": item.get("score", 0.0),
            "level": item.get("level", ""),
        }

    def _search(self, *, session_id: str, query: str, top_k: int) -> Dict[str, Any]:
        return self._worker.call(
            {
                "cmd": "search",
                "session_id": session_id,
                "query": query,
                "target_uri": self._user_memory_uri,
                "limit": max(1, int(top_k)),
                "score_threshold": self._score_threshold,
                "find_fallback": self._find_fallback,
            }
        )

    def passive_retrieve(self, event: PassiveTurnStartEvent) -> PassiveRetrieveResult:
        if not self._should_retrieve(event.user_input):
            return PassiveRetrieveResult(should_retrieve=False)
        self._ensure_session(event.session_id)
        result = self._search(session_id=event.session_id, query=event.user_input, top_k=self._retrieve_top_k)
        hits = result.get("items", []) if isinstance(result, dict) else []
        return PassiveRetrieveResult(
            should_retrieve=bool(hits),
            hits=hits,
            injected_context=self._render_hits(hits),
            debug={
                "adapter": "openviking",
                "worker_log": str(self._worker_log),
                "workspace": str(self._workspace_dir),
                "target_uri": self._user_memory_uri,
                "raw_hit_count": int(result.get("raw_hit_count", len(hits)) or len(hits)),
            },
        )

    def passive_write(self, event: PassiveTurnEndEvent) -> PassiveWriteResult:
        if event.active_write_count > 0:
            return PassiveWriteResult(should_store=False, debug={"reason": "active_write_already_happened"})
        messages: List[Dict[str, str]] = []
        user_text = self._sanitize_memory_text(event.user_input, limit=400)
        assistant_text = self._sanitize_memory_text(event.assistant_text, limit=500)
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
        if not messages:
            return PassiveWriteResult(should_store=False)
        self._ensure_session(event.session_id)
        result = self._worker.call(
            {
                "cmd": "append_and_commit",
                "session_id": event.session_id,
                "messages": messages,
                "timeout": self._commit_wait_timeout,
            }
        )
        stored = bool(result.get("ok")) and int(result.get("memory_file_count", 0) or 0) > 0
        return PassiveWriteResult(
            should_store=stored,
            mutations=result.get("memory_files", []) if isinstance(result.get("memory_files"), list) else [],
            debug={
                "adapter": "openviking",
                "worker_log": str(self._worker_log),
                "workspace": str(self._workspace_dir),
                "target_uri": self._user_memory_uri,
                "commit": result.get("commit"),
                "wait_processed": result.get("wait_processed"),
                "memory_file_count": result.get("memory_file_count", 0),
            },
        )

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = _normalize_text(str(params.get("query", "")))
        if not query:
            return {"ok": False, "error": "query is required", "items": []}
        result = self._search(
            session_id=self.current_session_id,
            query=query,
            top_k=int(params.get("top_k", self._search_limit) or self._search_limit),
        )
        return {"ok": True, **result}

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "OpenViking is session-commit based. Use passive write or explicit conversation turns instead of mem_set.",
        }

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error": "OpenViking adapter does not expose direct memory update."}

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error": "OpenViking adapter does not expose direct memory delete."}

    def stats(self) -> Dict[str, Any]:
        self._ensure_session(self.current_session_id)
        result = self._worker.call({"cmd": "stats", "session_id": self.current_session_id, "target_uri": self._user_memory_uri})
        return {
            "system_dir": str(self.system_dir),
            "policy_path": str(self.policy_path),
            "schema_path": str(self.schema_path),
            "artifact_dir": str(self.artifact_dir),
            "backend_type": "openviking_real",
            "worker_log": str(self._worker_log),
            "workspace": str(self._workspace_dir),
            **result,
        }


class EverMemOSWorkerClient:
    def __init__(
        self,
        *,
        python_bin: str,
        worker_script: Path,
        log_path: Path,
        startup_payload: Dict[str, Any],
    ) -> None:
        self.python_bin = python_bin
        self.worker_script = worker_script
        self.log_path = log_path
        self.startup_payload = startup_payload
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = self.log_path.open("a", encoding="utf-8")
        self._proc = subprocess.Popen(
            [self.python_bin, str(self.worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_handle,
            text=True,
            bufsize=1,
        )
        atexit.register(self.close)
        startup = self.call({"cmd": "startup", **self.startup_payload})
        if not startup.get("ok"):
            raise RuntimeError(f"EverMemOS worker startup failed: {startup}")

    def call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("EverMemOS worker stdio unavailable")
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"EverMemOS worker exited unexpectedly; see {self.log_path}")
            row = line.rstrip("\n")
            if not row.startswith("__JSON__"):
                continue
            raw = row[len("__JSON__") :]
            return json.loads(raw)

    def close(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                if proc.stdin is not None:
                    try:
                        proc.stdin.write(json.dumps({"cmd": "close"}, ensure_ascii=False) + "\n")
                        proc.stdin.flush()
                    except Exception:
                        pass
                proc.wait(timeout=3)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()
        self._proc = None
        with contextlib.suppress(Exception):
            self._stderr_handle.close()


class EverMemOSAdapter(BaseMemoryAdapter):
    def __init__(
        self,
        *,
        system_dir: Path,
        workspace_path: str,
        artifact_dir: Path,
        memory_user_id: str,
        api_key: str | None,
        api_key_env: str | None,
        model_name: str,
        base_url: str,
        repo_root: str = "/tmp/memory_scan_round2/EverMemOS_real_20260311",
        python_bin: str = "/Users/admin/miniconda3/envs/py312/bin/python",
        llm_provider: str = "openai",
        llm_temperature: float = 0.3,
        llm_max_tokens: int = 32768,
        vectorize_provider: str = "openai",
        vectorize_model: str = "embedding-3",
        vectorize_base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        vectorize_api_key: str | None = None,
        vectorize_api_key_env: str = "ZHIPU_API_KEY",
        vectorize_dimensions: int = 2048,
        hard_message_limit: int = 8,
        hard_token_limit: int = 8192,
        fetch_limit: int = 200,
        retrieve_top_k: int = 8,
        memory_types: List[str] | None = None,
        mongodb_host: str = "127.0.0.1",
        mongodb_port: int = 27017,
        mongodb_database: str | None = None,
        mongodb_username: str = "",
        mongodb_password: str = "",
        mongodb_uri_params: str = "",
        memory_language: str = "zh",
        scene: str = "assistant",
        assistant_id: str = "assistant_bot",
        assistant_name: str = "assistant",
        user_name: str = "用户",
    ) -> None:
        super().__init__(
            backend=None,
            system_dir=system_dir,
            workspace_path=workspace_path,
            artifact_dir=artifact_dir,
        )
        self.memory_user_id = _slugify(memory_user_id)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.python_bin = python_bin
        self.fetch_limit = max(1, int(fetch_limit))
        self.retrieve_top_k = max(1, int(retrieve_top_k))
        self.memory_types = memory_types or ["episodic_memory", "event_log", "profile", "foresight"]
        self.scene = scene
        self.assistant_id = assistant_id
        self.assistant_name = assistant_name
        self.user_name = user_name
        self._api_key = _resolve_api_key(api_key=api_key, api_key_env=api_key_env)
        self._vectorize_api_key = _resolve_api_key(
            api_key=vectorize_api_key,
            api_key_env=vectorize_api_key_env,
        )
        db_name = mongodb_database or f"memsys_ever_{_slugify(Path(self.workspace_path).name)}_{self.memory_user_id}"
        self._worker_log = self.artifact_dir / "evermemos_worker.log"
        self._worker = EverMemOSWorkerClient(
            python_bin=self.python_bin,
            worker_script=self.system_dir / "evermemos_worker.py",
            log_path=self._worker_log,
            startup_payload={
                "repo_root": str(self.repo_root),
                "mongodb_host": mongodb_host,
                "mongodb_port": str(mongodb_port),
                "mongodb_database": db_name,
                "mongodb_username": mongodb_username,
                "mongodb_password": mongodb_password,
                "mongodb_uri_params": mongodb_uri_params,
                "llm_provider": llm_provider,
                "llm_model": model_name,
                "llm_base_url": base_url,
                "llm_api_key": self._api_key,
                "llm_temperature": llm_temperature,
                "llm_max_tokens": llm_max_tokens,
                "vectorize_provider": vectorize_provider,
                "vectorize_model": vectorize_model,
                "vectorize_base_url": vectorize_base_url,
                "vectorize_api_key": self._vectorize_api_key,
                "vectorize_dimensions": vectorize_dimensions,
                "hard_message_limit": hard_message_limit,
                "hard_token_limit": hard_token_limit,
                "memory_language": memory_language,
            },
        )
        self._message_counter = 0
        self._db_name = db_name

    def _group_id(self, session_id: str) -> str:
        return f"v63_{self.memory_user_id}_{_slugify(session_id)}"

    def _ensure_group(self, session_id: str) -> Dict[str, Any]:
        return self._worker.call(
            {
                "cmd": "ensure_group",
                "group_id": self._group_id(session_id),
                "group_name": session_id,
                "scene": self.scene,
                "user_id": self.memory_user_id,
                "user_name": self.user_name,
                "assistant_id": self.assistant_id,
                "assistant_name": self.assistant_name,
                "timezone": str(_now_local().tzinfo or "Asia/Shanghai"),
            }
        )

    def _memorize_message(
        self,
        *,
        session_id: str,
        role: str,
        sender: str,
        sender_name: str,
        content: str,
        create_time: str,
    ) -> Dict[str, Any]:
        self._message_counter += 1
        return self._worker.call(
            {
                "cmd": "memorize",
                "group_id": self._group_id(session_id),
                "group_name": session_id,
                "scene": self.scene,
                "user_id": self.memory_user_id,
                "user_name": self.user_name,
                "assistant_id": self.assistant_id,
                "assistant_name": self.assistant_name,
                "message_id": f"{_slugify(session_id)}_{self._message_counter:06d}",
                "create_time": create_time,
                "sender": sender,
                "sender_name": sender_name,
                "role": role,
                "content": content,
            }
        )

    @staticmethod
    def _iter_memory_texts(node: Any) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        def visit(value: Any, mem_type: str = "") -> None:
            if isinstance(value, dict):
                text = ""
                for key in ("memory", "content", "summary", "text", "title", "description", "value"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and _normalize_text(candidate):
                        text = _normalize_text(candidate)
                        break
                if text:
                    rows.append(
                        {
                            "type": mem_type or str(value.get("memory_type") or value.get("type") or "memory"),
                            "content": text,
                            "raw": value,
                        }
                    )
                for key, child in value.items():
                    next_type = mem_type
                    if key in {"episodic_memory", "event_log", "profile", "foresight", "group_profile", "preference", "base_memory"}:
                        next_type = key
                    visit(child, next_type)
            elif isinstance(value, list):
                for child in value:
                    visit(child, mem_type)

        visit(node)
        deduped: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (str(row.get("type", "")), str(row.get("content", "")))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _fetch_all(self, session_id: str) -> List[Dict[str, Any]]:
        self._ensure_group(session_id)
        rows: List[Dict[str, Any]] = []
        for mem_type in self.memory_types:
            result = self._worker.call(
                {
                    "cmd": "fetch",
                    "group_id": self._group_id(session_id),
                    "user_id": self.memory_user_id,
                    "memory_type": mem_type,
                    "limit": self.fetch_limit,
                    "offset": 0,
                }
            )
            extracted = self._iter_memory_texts(result)
            for item in extracted:
                item["fetch_type"] = mem_type
            rows.extend(extracted)
        return rows

    @staticmethod
    def _rank_rows(query: str, rows: List[Dict[str, Any]], *, top_k: int) -> List[Dict[str, Any]]:
        q_tokens = set(_tokenize(query))
        scored: List[tuple[float, Dict[str, Any]]] = []
        for row in rows:
            content = _normalize_text(str(row.get("content", "")))
            if not content:
                continue
            tokens = set(_tokenize(content))
            if not tokens:
                continue
            overlap = len(q_tokens & tokens)
            if overlap <= 0:
                continue
            score = overlap / max(1.0, math.sqrt(len(tokens)))
            scored.append((score, {**row, "score": score}))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:top_k]]

    def _render_hits(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["[Memory Context]"]
        for item in hits:
            lines.append(f"- ({item.get('type')}) {item.get('content')}")
        return "\n".join(lines)

    def passive_retrieve(self, event: PassiveTurnStartEvent) -> PassiveRetrieveResult:
        if not self._should_retrieve(event.user_input):
            return PassiveRetrieveResult(should_retrieve=False)
        rows = self._fetch_all(event.session_id)
        hits = self._rank_rows(event.user_input, rows, top_k=self.retrieve_top_k)
        return PassiveRetrieveResult(
            should_retrieve=bool(hits),
            hits=hits,
            injected_context=self._render_hits(hits),
            debug={
                "adapter": "evermemos",
                "repo_root": str(self.repo_root),
                "worker_log": str(self._worker_log),
                "mongodb_database": self._db_name,
                "fetched_total": len(rows),
            },
        )

    def passive_write(self, event: PassiveTurnEndEvent) -> PassiveWriteResult:
        if event.active_write_count > 0:
            return PassiveWriteResult(should_store=False, debug={"reason": "active_write_already_happened"})
        user_text = _normalize_text(event.user_input)
        assistant_text = _normalize_text(event.assistant_text)
        if not user_text and not assistant_text:
            return PassiveWriteResult(should_store=False)
        self._ensure_group(event.session_id)
        mutations: List[Dict[str, Any]] = []
        if user_text:
            mutations.append(
                self._memorize_message(
                    session_id=event.session_id,
                    role="user",
                    sender=self.memory_user_id,
                    sender_name=self.user_name,
                    content=user_text,
                    create_time=event.now_local,
                )
            )
        if assistant_text:
            mutations.append(
                self._memorize_message(
                    session_id=event.session_id,
                    role="assistant",
                    sender=self.assistant_id,
                    sender_name=self.assistant_name,
                    content=assistant_text,
                    create_time=event.now_local,
                )
            )
        stored = any(int(row.get("count", 0) or 0) > 0 for row in mutations if isinstance(row, dict))
        return PassiveWriteResult(
            should_store=stored,
            mutations=mutations,
            debug={
                "adapter": "evermemos",
                "repo_root": str(self.repo_root),
                "worker_log": str(self._worker_log),
                "mongodb_database": self._db_name,
            },
        )

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = _normalize_text(str(params.get("query", "")))
        if not query:
            return {"ok": False, "error": "query is required", "items": []}
        rows = self._fetch_all(self.current_session_id)
        top_k = max(1, int(params.get("top_k", self.retrieve_top_k) or self.retrieve_top_k))
        hits = self._rank_rows(query, rows, top_k=top_k)
        return {"ok": True, "items": hits, "mongodb_database": self._db_name, "worker_log": str(self._worker_log)}

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        content = _normalize_text(str(params.get("content", "")))
        if not content:
            return {"ok": False, "error": "content is required"}
        result = self._memorize_message(
            session_id=self.current_session_id,
            role="assistant",
            sender=self.assistant_id,
            sender_name=self.assistant_name,
            content=content,
            create_time=_now_local().isoformat(timespec="seconds"),
        )
        return {"ok": bool(result.get("ok")), "result": result}

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error": "EverMemOS runtime update is not exposed via this adapter yet."}

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error": "EverMemOS runtime delete is not exposed via this adapter yet."}

    def stats(self) -> Dict[str, Any]:
        rows = self._fetch_all(self.current_session_id)
        return {
            "system_dir": str(self.system_dir),
            "policy_path": str(self.policy_path),
            "schema_path": str(self.schema_path),
            "artifact_dir": str(self.artifact_dir),
            "backend_type": "evermemos_real",
            "repo_root": str(self.repo_root),
            "worker_log": str(self._worker_log),
            "mongodb_database": self._db_name,
            "fetched_total": len(rows),
        }


class MemoryRuntimeV63:
    def __init__(
        self,
        *,
        backend_name: str,
        system_dir: str,
        workspace_path: str,
        artifact_dir: str,
        memory_user_id: str = "default",
        api_key: str | None = None,
        api_key_env: str | None = None,
        model_name: str = "",
        base_url: str = "",
        backend_config: Dict[str, Any] | None = None,
    ) -> None:
        self.backend_name = (backend_name or "simplemem").strip().lower()
        self.system_dir = Path(system_dir)
        self.workspace_path = workspace_path.strip() or "."
        self.artifact_dir = Path(artifact_dir)
        self.memory_user_id = memory_user_id.strip() or "default"
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.model_name = model_name
        self.base_url = base_url
        self.backend_config = backend_config or {}
        self._active_write_count = 0
        self._session_id = "default"
        self.adapter = self._build_adapter()

    def _build_adapter(self) -> MemoryAdapter:
        if self.backend_name == "evermemos":
            return EverMemOSAdapter(
                system_dir=self.system_dir,
                workspace_path=self.workspace_path,
                artifact_dir=self.artifact_dir,
                memory_user_id=self.memory_user_id,
                api_key=self.api_key,
                api_key_env=self.api_key_env,
                model_name=self.model_name,
                base_url=self.base_url,
                **self.backend_config,
            )
        if self.backend_name == "openviking":
            return OpenVikingAdapter(
                system_dir=self.system_dir,
                workspace_path=self.workspace_path,
                artifact_dir=self.artifact_dir,
                memory_user_id=self.memory_user_id,
                api_key=self.api_key,
                api_key_env=self.api_key_env,
                model_name=self.model_name,
                base_url=self.base_url,
                **self.backend_config,
            )
        if self.backend_name == "mem0":
            return Mem0Adapter(
                system_dir=self.system_dir,
                workspace_path=self.workspace_path,
                artifact_dir=self.artifact_dir,
                memory_user_id=self.memory_user_id,
                api_key=self.api_key,
                api_key_env=self.api_key_env,
                model_name=self.model_name,
                base_url=self.base_url,
                **self.backend_config,
            )
        return SimpleMemAdapter(
            system_dir=self.system_dir,
            workspace_path=self.workspace_path,
            artifact_dir=self.artifact_dir,
            api_key=self.api_key,
            api_key_env=self.api_key_env,
            model_name=self.model_name,
            base_url=self.base_url,
            **self.backend_config,
        )

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id.strip() or "default"
        setter = getattr(self.adapter, "set_session", None)
        if callable(setter):
            setter(self._session_id)

    def start_turn(self) -> None:
        self._active_write_count = 0

    def build_system_prompt_block(self) -> str:
        return self.adapter.build_system_prompt_block(session_id=self._session_id)

    def passive_retrieve(self, *, user_input: str, recent_messages: List[Message]) -> PassiveRetrieveResult:
        now_local = _now_local()
        return self.adapter.passive_retrieve(
            PassiveTurnStartEvent(
                workspace_path=self.workspace_path,
                session_id=self._session_id,
                user_input=user_input,
                recent_messages=recent_messages,
                now_local=now_local.isoformat(timespec="seconds"),
                now_utc=_now_utc_iso(),
                timezone=str(now_local.tzinfo or "UTC"),
            ),
        )

    def passive_write(
        self,
        *,
        user_input: str,
        assistant_text: str,
        recent_messages: List[Message],
        tool_events: List[MemoryToolEvent],
    ) -> PassiveWriteResult:
        now_local = _now_local()
        return self.adapter.passive_write(
            PassiveTurnEndEvent(
                workspace_path=self.workspace_path,
                session_id=self._session_id,
                user_input=user_input,
                assistant_text=assistant_text,
                recent_messages=recent_messages,
                tool_events=tool_events,
                now_local=now_local.isoformat(timespec="seconds"),
                now_utc=_now_utc_iso(),
                timezone=str(now_local.tzinfo or "UTC"),
                active_write_count=self._active_write_count,
            ),
        )

    def active_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self.adapter.active_get(params)

    def active_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._active_write_count += 1
        return self.adapter.active_set(params)

    def active_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._active_write_count += 1
        return self.adapter.active_update(params)

    def active_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._active_write_count += 1
        return self.adapter.active_delete(params)

    def stats(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "workspace_path": self.workspace_path,
            "session_id": self._session_id,
            "active_write_count": self._active_write_count,
            **self.adapter.stats(),
        }
