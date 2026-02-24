from __future__ import annotations

from .base import BaseAgentLoop


class V1(BaseAgentLoop):
    async def run_turn(self, user_input: str) -> str:
        self.state.messages.append({"role": "user", "content": user_input})
        response = await self._call_llm(tools=None)
        assistant_text = response.text or ""
        self.state.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text
