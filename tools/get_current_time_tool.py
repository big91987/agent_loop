from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from core.tool_base import BaseTool


class GetCurrentTimeTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "Return the current UTC timestamp in ISO-8601 format."

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def handler(self, _params: Dict[str, object]) -> str:
        return datetime.now(timezone.utc).isoformat()
