from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_find


class FindTool(BaseTool):
    @property
    def name(self) -> str:
        return "find"

    @property
    def description(self) -> str:
        return (
            "Glob-based file discovery rooted at path. "
            "Returns matching file paths to drive downstream read/grep/edit actions."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["pattern", "path"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        pattern = str(params["pattern"])
        path = str(params["path"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        return run_find(pattern=pattern, path=path, cwd=cwd)
