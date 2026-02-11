from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_ls


class LsTool(BaseTool):
    @property
    def name(self) -> str:
        return "ls"

    @property
    def description(self) -> str:
        return (
            "List directory entries (including dotfiles) in stable sorted order. "
            "Directories are rendered with trailing slash for quick path disambiguation."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        path = str(params.get("path", "."))
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        return run_ls(path=path, cwd=cwd)
