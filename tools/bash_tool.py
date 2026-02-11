from __future__ import annotations

from typing import Dict

from core.tool_base import BaseTool

from .local_ops import run_bash


class BashTool(BaseTool):
    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in a controlled working directory with timeout. "
            "Returns captured stdout/stderr plus exit status for deterministic follow-up handling."
        )

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["command"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        command = str(params["command"])
        cwd = str(params["cwd"]) if params.get("cwd") is not None else None
        timeout = int(params.get("timeout", 30))
        return run_bash(command=command, cwd=cwd, timeout=timeout)
