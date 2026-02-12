from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    type: str = "stdio"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: str | None = None
    message_url: str | None = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30


class MCPError(RuntimeError):
    pass
