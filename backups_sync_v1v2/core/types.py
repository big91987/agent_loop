from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol


Message = Dict[str, object]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, object]


@dataclass(frozen=True)
class AssistantResponse:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)


ToolHandler = Callable[[Dict[str, object]], str]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, object]
    handler: ToolHandler


class LLMClient(Protocol):
    def generate(
        self,
        *,
        model_name: str,
        messages: List[Message],
        tools: Optional[List[ToolSpec]] = None,
        timeout_seconds: int = 60,
    ) -> AssistantResponse: ...

