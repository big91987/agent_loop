from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List

from core.types import LLMClient, Message, ToolSpec


@dataclass
class AgentStateV2:
    system_prompt: str = "You are a helpful assistant."
    messages: List[Message] = field(default_factory=list)


def _tools_by_name(tools: List[ToolSpec]) -> Dict[str, ToolSpec]:
    return {tool.name: tool for tool in tools}


def run_turn_v2(
    *,
    state: AgentStateV2,
    client: LLMClient,
    model_name: str,
    user_input: str,
    tools: List[ToolSpec],
    timeout_seconds: int = 60,
    max_tool_rounds: int = 8,
) -> str:
    state.messages.append({"role": "user", "content": user_input})
    registry = _tools_by_name(tools)
    final_text = ""

    for _ in range(max_tool_rounds):
        llm_messages: List[Message] = [{"role": "system", "content": state.system_prompt}, *state.messages]
        response = client.generate(
            model_name=model_name,
            messages=llm_messages,
            tools=tools,
            timeout_seconds=timeout_seconds,
        )

        assistant_message: Message = {"role": "assistant", "content": response.text}
        if response.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=True),
                    },
                }
                for call in response.tool_calls
            ]
        state.messages.append(assistant_message)

        if not response.tool_calls:
            final_text = response.text
            break

        for call in response.tool_calls:
            tool = registry.get(call.name)
            if not tool:
                tool_output = f"Tool not found: {call.name}"
            else:
                try:
                    tool_output = tool.handler(call.arguments)
                except Exception as err:  # noqa: BLE001
                    tool_output = f"Tool execution error: {err}"

            state.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": tool_output,
                },
            )

    return final_text
