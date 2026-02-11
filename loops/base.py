from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from core.types import AssistantResponse, LLMClient, Message, ToolSpec


@dataclass
class AgentLoopState:
    system_prompt: str = "You are a helpful assistant."
    messages: List[Message] = field(default_factory=list)


class BaseAgentLoop(ABC):
    def __init__(
        self,
        *,
        client: LLMClient,
        model_name: str,
        timeout_seconds: int = 60,
        system_prompt: str = "You are a helpful assistant.",
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.state = AgentLoopState(system_prompt=system_prompt)

    def get_messages(self) -> List[Message]:
        return self.state.messages

    async def _call_llm(self, tools: Optional[List[ToolSpec]] = None) -> AssistantResponse:
        llm_messages: List[Message] = [
            {"role": "system", "content": self.state.system_prompt},
            *self.state.messages,
        ]
        return await self.client.generate(
            model_name=self.model_name,
            messages=llm_messages,
            tools=tools,
            timeout_seconds=self.timeout_seconds,
        )

    @abstractmethod
    async def run_turn(self, user_input: str) -> str:
        raise NotImplementedError

