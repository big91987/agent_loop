from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_edit


class EditTool(BaseTool):
    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Perform strict single-occurrence text replacement in a UTF-8 file. "
            "Fails when old_text is missing or appears multiple times to avoid accidental broad edits."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        path = str(params["path"])
        old_text = str(params["old_text"])
        new_text = str(params["new_text"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        return run_edit(path=path, old_text=old_text, new_text=new_text, cwd=cwd)
