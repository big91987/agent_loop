from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_write


class WriteTool(BaseTool):
    @property
    def name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return (
            "Write full UTF-8 content to a target file. Creates parent directories when missing and "
            "returns a resolved path plus byte-count metadata for post-write verification."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        path = str(params["path"])
        content = str(params["content"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        return run_write(path=path, content=content, cwd=cwd)
