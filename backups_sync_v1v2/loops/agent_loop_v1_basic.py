from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from core.types import LLMClient, Message


@dataclass
class AgentStateV1:
    system_prompt: str = "You are a helpful assistant."
    messages: List[Message] = field(default_factory=list)


def run_turn_v1(
    *,
    state: AgentStateV1,
    client: LLMClient,
    model_name: str,
    user_input: str,
    timeout_seconds: int = 60,
) -> str:
    user_message: Message = {
        "role": "user",
        "content": user_input,
    }
    state.messages.append(user_message)

    llm_messages: List[Message] = [{"role": "system", "content": state.system_prompt}, *state.messages]
    response = client.generate(
        model_name=model_name,
        messages=llm_messages,
        tools=None,
        timeout_seconds=timeout_seconds,
    )

    assistant_text = response.text or ""
    state.messages.append({"role": "assistant", "content": assistant_text})
    return assistant_text
