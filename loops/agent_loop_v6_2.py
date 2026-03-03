from __future__ import annotations

import json
from typing import Dict, List

from core.memory_system_v6_2 import MemorySystemRuntimeV62
from core.types import ToolSpec
from tools.registry import build_tool_registry

from .agent_loop_v6_1 import V6_1


class V6_2(V6_1):
    def __init__(
        self,
        *,
        memory_system_dir: str = "./memory_systems/simplemem_v1",
        memory_store_path: str = "./memory/v6_2_long_memory.jsonl",
        workspace_path: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.workspace_path = (workspace_path or "").strip() or "."
        self.memory_runtime = MemorySystemRuntimeV62(
            system_dir=memory_system_dir,
            store_path=memory_store_path,
        )
        self.memory_session_id = "default"
        self._memory_tools: List[ToolSpec] = self._build_memory_tools()
        self._base_tools = [*self._base_tools, *self._memory_tools]
        self.tools = [*self._base_tools, *self._mcp_tools]
        self._tool_registry = build_tool_registry(self.tools)

    def set_memory_session(self, session_id: str) -> None:
        self.memory_session_id = session_id.strip() or "default"

    def get_memory_system_status(self) -> Dict[str, object]:
        stats = self.memory_runtime.store.stats()
        return {
            "system_dir": str(self.memory_runtime.system_dir),
            "policy_path": str(self.memory_runtime.policy_path),
            "schema_path": str(self.memory_runtime.schema_path),
            "session_id": self.memory_session_id,
            **stats,
        }

    def _apply_skill_prompt(self) -> None:
        super()._apply_skill_prompt()
        policy = self.memory_runtime.get_policy_text()
        schema = self.memory_runtime.get_schema_text()
        self.state.system_prompt = (
            f"{self.state.system_prompt}\n\n"
            "[Long Memory System]\n"
            f"- workspace_path: {self.workspace_path}\n"
            f"- memory_store_path: {self.memory_runtime.store.path}\n"
            f"- memory_session_id: {self.memory_session_id}\n"
            "- Use memory tools when beneficial; do NOT treat this as mandatory fixed flow.\n"
            "- Decide autonomously whether to retrieve/store/update/delete.\n\n"
            "<memory_policy>\n"
            f"{policy}\n"
            "</memory_policy>\n\n"
            "<memory_tools_contract>\n"
            f"{schema}\n"
            "</memory_tools_contract>\n"
        )

    def _build_memory_tools(self) -> List[ToolSpec]:
        async def _mem_get(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_get args={json.dumps(params, ensure_ascii=False)}")
            query = str(params.get("query", "")).strip()
            scope = str(params.get("scope", "")).strip() or None
            types_raw = params.get("types", [])
            types = [str(x).strip() for x in types_raw] if isinstance(types_raw, list) else []
            top_k = int(params.get("top_k", 5) or 5)
            min_score = float(params.get("min_score", 0.0) or 0.0)
            result = self.memory_runtime.store.get_records(
                query=query,
                scope=scope,
                types=types,
                top_k=top_k,
                min_score=min_score,
            )
            return json.dumps(result, ensure_ascii=False)

        async def _mem_set(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_set args={json.dumps(params, ensure_ascii=False)}")
            memory_type = str(params.get("type", "fact")).strip() or "fact"
            scope = str(params.get("scope", "user")).strip() or "user"
            content = str(params.get("content", "")).strip()
            tags_raw = params.get("tags", [])
            tags = [str(x).strip() for x in tags_raw] if isinstance(tags_raw, list) else []
            confidence = float(params.get("confidence", 0.7) or 0.7)
            source = str(params.get("source", "assistant")).strip() or "assistant"
            result = self.memory_runtime.store.set_record(
                memory_type=memory_type,
                scope=scope,
                content=content,
                tags=tags,
                confidence=confidence,
                source=source,
            )
            return json.dumps(result, ensure_ascii=False)

        async def _mem_update(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_update args={json.dumps(params, ensure_ascii=False)}")
            record_id = str(params.get("id", "")).strip()
            patch = params.get("patch", {})
            if not isinstance(patch, dict):
                patch = {}
            expected_version_raw = params.get("expected_version")
            expected_version = int(expected_version_raw) if expected_version_raw is not None else None
            result = self.memory_runtime.store.update_record(
                record_id=record_id,
                patch=patch,
                expected_version=expected_version,
            )
            return json.dumps(result, ensure_ascii=False)

        async def _mem_delete(params: Dict[str, object]) -> str:
            self._emit_trace(f"[MEMORY] mem_delete args={json.dumps(params, ensure_ascii=False)}")
            record_id = str(params.get("id", "")).strip()
            mode = str(params.get("mode", "soft")).strip() or "soft"
            expected_version_raw = params.get("expected_version")
            expected_version = int(expected_version_raw) if expected_version_raw is not None else None
            result = self.memory_runtime.store.delete_record(
                record_id=record_id,
                mode=mode,
                expected_version=expected_version,
            )
            return json.dumps(result, ensure_ascii=False)

        return [
            ToolSpec(
                name="mem_get",
                description="Retrieve long-term memories by semantic keyword query.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                        "top_k": {"type": "integer"},
                        "min_score": {"type": "number"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=_mem_get,
            ),
            ToolSpec(
                name="mem_set",
                description="Create or upsert a long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "scope": {"type": "string"},
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                        "source": {"type": "string"},
                    },
                    "required": ["type", "scope", "content"],
                    "additionalProperties": False,
                },
                handler=_mem_set,
            ),
            ToolSpec(
                name="mem_update",
                description="Update an existing long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "patch": {"type": "object", "additionalProperties": True},
                        "expected_version": {"type": "integer"},
                    },
                    "required": ["id", "patch"],
                    "additionalProperties": False,
                },
                handler=_mem_update,
            ),
            ToolSpec(
                name="mem_delete",
                description="Delete or soft-delete a long-term memory record.",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["soft", "hard"]},
                        "expected_version": {"type": "integer"},
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
                handler=_mem_delete,
            ),
        ]
