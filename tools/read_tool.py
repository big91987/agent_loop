from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, run_read


class ReadTool(BaseTool):
    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 text file with deterministic pagination and truncation controls. "
            "Use offset/limit for explicit paging; when limit is omitted, output is bounded by "
            "max_lines/max_bytes. On truncation, response includes continuation hints with next offset."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "max_lines": {"type": "integer"},
                "max_bytes": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        path = str(params["path"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        offset = int(params.get("offset", 1))
        limit = int(params["limit"]) if params.get("limit") is not None else None
        max_lines = int(params.get("max_lines", DEFAULT_MAX_LINES))
        max_bytes = int(params.get("max_bytes", DEFAULT_MAX_BYTES))
        return run_read(
            path=path,
            cwd=cwd,
            offset=offset,
            limit=limit,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )
