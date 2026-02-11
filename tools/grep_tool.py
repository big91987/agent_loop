from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_grep


class GrepTool(BaseTool):
    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Regex search across a file or directory tree with bounded output. "
            "Returns file+line formatted matches, optional context lines, and limit-hit continuation hints."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "cwd": {"type": "string"},
                "limit": {"type": "integer"},
                "context": {"type": "integer"},
            },
            "required": ["pattern", "path"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        pattern = str(params["pattern"])
        path = str(params["path"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        limit = int(params.get("limit", 20))
        context = int(params.get("context", 0))
        return run_grep(pattern=pattern, path=path, cwd=cwd, limit=limit, context=context)
