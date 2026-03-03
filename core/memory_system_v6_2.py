from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokenize(text: str) -> List[str]:
    lowered = (text or "").lower()
    return re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", lowered)


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
    expires_at: str | None = None
    deleted_at: str | None = None

    def to_dict(self) -> Dict[str, object]:
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
            "expires_at": self.expires_at,
            "deleted_at": self.deleted_at,
        }

    @staticmethod
    def from_dict(raw: Dict[str, object]) -> "MemoryRecord":
        tags_raw = raw.get("tags", [])
        tags = [str(x).strip() for x in tags_raw] if isinstance(tags_raw, list) else []
        return MemoryRecord(
            id=str(raw.get("id", "")).strip(),
            memory_type=str(raw.get("type", "fact")).strip() or "fact",
            scope=str(raw.get("scope", "user")).strip() or "user",
            content=" ".join(str(raw.get("content", "")).split()).strip(),
            tags=[t for t in tags if t],
            confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
            source=str(raw.get("source", "assistant")).strip() or "assistant",
            version=max(1, int(raw.get("version", 1) or 1)),
            created_at=str(raw.get("created_at", "")) or _now_iso(),
            updated_at=str(raw.get("updated_at", "")) or _now_iso(),
            expires_at=str(raw.get("expires_at")) if raw.get("expires_at") else None,
            deleted_at=str(raw.get("deleted_at")) if raw.get("deleted_at") else None,
        )


class MemoryStoreV62:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[MemoryRecord] = []
        self._load()

    def _load(self) -> None:
        self._records = []
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
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
        lines = [json.dumps(record.to_dict(), ensure_ascii=False) for record in self._records]
        payload = "\n".join(lines)
        if payload:
            payload += "\n"
        self.path.write_text(payload, encoding="utf-8")

    @staticmethod
    def _is_alive(record: MemoryRecord) -> bool:
        if record.deleted_at:
            return False
        if record.expires_at:
            return record.expires_at > _now_iso()
        return True

    def stats(self) -> Dict[str, object]:
        alive = sum(1 for r in self._records if self._is_alive(r))
        return {
            "path": str(self.path),
            "records_total": len(self._records),
            "records_alive": alive,
        }

    def _find_by_id(self, record_id: str) -> MemoryRecord | None:
        for record in self._records:
            if record.id == record_id:
                return record
        return None

    def _find_dedupe(self, *, scope: str, memory_type: str, content: str) -> MemoryRecord | None:
        normalized = " ".join(content.split()).strip()
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
    ) -> Dict[str, object]:
        normalized = " ".join((content or "").split()).strip()
        if not normalized:
            return {"ok": False, "error": "content is required"}
        found = self._find_dedupe(scope=scope, memory_type=memory_type, content=normalized)
        now = _now_iso()
        if found:
            found.updated_at = now
            found.version += 1
            found.confidence = max(found.confidence, max(0.0, min(1.0, float(confidence))))
            if tags:
                merged = sorted(set([*found.tags, *[t for t in tags if t.strip()]]))
                found.tags = merged
            self._persist()
            return {"ok": True, "created": False, "record": found.to_dict()}

        record = MemoryRecord(
            id=f"m_{uuid4().hex[:12]}",
            memory_type=memory_type.strip() or "fact",
            scope=scope.strip() or "user",
            content=normalized,
            tags=sorted(set([t.strip() for t in (tags or []) if t and t.strip()])),
            confidence=max(0.0, min(1.0, float(confidence))),
            source=source.strip() or "assistant",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._records.append(record)
        self._persist()
        return {"ok": True, "created": True, "record": record.to_dict()}

    def update_record(
        self,
        *,
        record_id: str,
        patch: Dict[str, object],
        expected_version: int | None = None,
    ) -> Dict[str, object]:
        record = self._find_by_id(record_id)
        if record is None:
            return {"ok": False, "error": "record not found"}
        if expected_version is not None and int(record.version) != int(expected_version):
            return {
                "ok": False,
                "error": "version conflict",
                "current_version": int(record.version),
            }
        now = _now_iso()
        if "content" in patch:
            record.content = " ".join(str(patch.get("content", "")).split()).strip()
        if "type" in patch:
            record.memory_type = str(patch.get("type", "fact")).strip() or "fact"
        if "scope" in patch:
            record.scope = str(patch.get("scope", "user")).strip() or "user"
        if "tags" in patch and isinstance(patch["tags"], list):
            record.tags = sorted(set([str(x).strip() for x in patch["tags"] if str(x).strip()]))
        if "confidence" in patch:
            record.confidence = max(0.0, min(1.0, float(patch["confidence"] or 0.0)))
        if "expires_at" in patch:
            raw = str(patch.get("expires_at", "")).strip()
            record.expires_at = raw or None
        record.updated_at = now
        record.version += 1
        self._persist()
        return {"ok": True, "updated": True, "record": record.to_dict()}

    def delete_record(
        self,
        *,
        record_id: str,
        mode: str = "soft",
        expected_version: int | None = None,
    ) -> Dict[str, object]:
        record = self._find_by_id(record_id)
        if record is None:
            return {"ok": False, "error": "record not found"}
        if expected_version is not None and int(record.version) != int(expected_version):
            return {
                "ok": False,
                "error": "version conflict",
                "current_version": int(record.version),
            }
        if mode == "hard":
            self._records = [x for x in self._records if x.id != record_id]
            self._persist()
            return {"ok": True, "deleted": True, "mode": "hard", "id": record_id}
        record.deleted_at = _now_iso()
        record.updated_at = _now_iso()
        record.version += 1
        self._persist()
        return {"ok": True, "deleted": True, "mode": "soft", "record": record.to_dict()}

    def get_records(
        self,
        *,
        query: str,
        scope: str | None = None,
        types: List[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> Dict[str, object]:
        q = " ".join((query or "").split()).strip()
        if not q:
            return {"ok": False, "error": "query is required", "items": []}
        q_tokens = _tokenize(q)
        if not q_tokens:
            return {"ok": True, "items": []}
        valid_types = set([t.strip() for t in (types or []) if t and t.strip()])
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
        rows.sort(key=lambda x: x[0], reverse=True)
        result = [
            {
                "id": record.id,
                "type": record.memory_type,
                "scope": record.scope,
                "content": record.content,
                "tags": list(record.tags),
                "confidence": record.confidence,
                "version": record.version,
                "updated_at": record.updated_at,
                "score": score,
            }
            for score, record in rows[: max(1, int(top_k))]
        ]
        return {"ok": True, "items": result}


class MemorySystemRuntimeV62:
    def __init__(self, *, system_dir: str, store_path: str) -> None:
        self.system_dir = Path(system_dir)
        self.policy_path = self.system_dir / "memory_policy.md"
        self.schema_path = self.system_dir / "tools_schema.json"
        self.store = MemoryStoreV62(store_path)

    def get_policy_text(self) -> str:
        if self.policy_path.exists():
            raw = self.policy_path.read_text(encoding="utf-8").strip()
            try:
                return raw.format(memory_store_path=str(self.store.path))
            except Exception:
                return raw
        return (
            "# Memory Policy\n"
            "Use memory tools when helpful; keep durable, concise, non-duplicated memories."
        )

    def get_schema_text(self) -> str:
        if self.schema_path.exists():
            return self.schema_path.read_text(encoding="utf-8").strip()
        return "{}"
