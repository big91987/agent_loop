from __future__ import annotations

import inspect
import json
from typing import Dict, List, Set

from core.types import ToolSpec
from tools.registry import build_tool_registry, tool_specs_for_names

from .base import BaseAgentLoop


class V2ToolsLoop(BaseAgentLoop):
    def __init__(
        self,
        *,
        max_tool_rounds: int = 8,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        # Teaching point: v2 uses only two built-in demo tools.
        self.tool_names: Set[str] = {"calculate", "get_current_time"}
        self.tools: List[ToolSpec] = tool_specs_for_names(self.tool_names)
        self.max_tool_rounds = max_tool_rounds
        self._tool_registry: Dict[str, ToolSpec] = build_tool_registry(self.tools)

    async def run_turn(self, user_input: str) -> str:
        self.state.messages.append({"role": "user", "content": user_input})
        final_text = ""

        for _ in range(self.max_tool_rounds):
            response = await self._call_llm(tools=self.tools)

            assistant_message = {"role": "assistant", "content": response.text}
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
            self.state.messages.append(assistant_message)

            if not response.tool_calls:
                final_text = response.text
                break

            for call in response.tool_calls:
                tool = self._tool_registry.get(call.name)
                if not tool:
                    tool_output = f"Tool not found: {call.name}"
                else:
                    try:
                        maybe_output = tool.handler(call.arguments)
                        if inspect.isawaitable(maybe_output):
                            tool_output = await maybe_output
                        else:
                            tool_output = str(maybe_output)
                    except Exception as err:  # noqa: BLE001
                        tool_output = f"Tool execution error: {err}"

                self.state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": tool_output,
                    },
                )

        return final_text
