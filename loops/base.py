from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import math
from typing import Callable, List, Optional

from core.types import AssistantResponse, LLMClient, Message, TokenUsage, ToolSpec


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
        stream_text: bool = False,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.stream_text = stream_text
        self.state = AgentLoopState(system_prompt=system_prompt)
        self._last_usage: TokenUsage | None = None
        self._usage_seen = False
        self._session_prompt_tokens = 0
        self._session_completion_tokens = 0
        self._session_total_tokens = 0

    def get_messages(self) -> List[Message]:
        return self.state.messages

    def get_token_usage_snapshot(self) -> dict[str, int | bool]:
        return {
            "has_usage": self._usage_seen,
            "last_prompt_tokens": self._last_usage.prompt_tokens if self._last_usage else 0,
            "last_completion_tokens": self._last_usage.completion_tokens if self._last_usage else 0,
            "last_total_tokens": self._last_usage.total_tokens if self._last_usage else 0,
            "last_usage_source": self._last_usage.source if self._last_usage else "none",
            "session_prompt_tokens": self._session_prompt_tokens,
            "session_completion_tokens": self._session_completion_tokens,
            "session_total_tokens": self._session_total_tokens,
        }

    @staticmethod
    def _estimate_tokens_from_obj(obj: object) -> int:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        # Lightweight fallback: ~1 token per 4 chars (language-agnostic rough estimate).
        return max(1, int(math.ceil(len(text) / 4)))

    async def _call_llm(
        self,
        tools: Optional[List[ToolSpec]] = None,
        *,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> AssistantResponse:
        llm_messages: List[Message] = [
            {"role": "system", "content": self.state.system_prompt},
            *self.state.messages,
        ]
        response = await self.client.generate(
            model_name=self.model_name,
            messages=llm_messages,
            tools=tools,
            timeout_seconds=self.timeout_seconds,
            stream=self.stream_text,
            on_text_delta=on_text_delta,
        )
        usage = response.usage
        if usage is None:
            est_prompt = self._estimate_tokens_from_obj(llm_messages)
            est_completion = self._estimate_tokens_from_obj(
                {
                    "text": response.text,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                },
            )
            usage = TokenUsage(
                prompt_tokens=est_prompt,
                completion_tokens=est_completion,
                total_tokens=est_prompt + est_completion,
                source="estimated",
            )
        self._last_usage = usage
        self._usage_seen = True
        self._session_prompt_tokens += usage.prompt_tokens
        self._session_completion_tokens += usage.completion_tokens
        self._session_total_tokens += usage.total_tokens
        return response

    @abstractmethod
    async def run_turn(self, user_input: str) -> str:
        raise NotImplementedError
