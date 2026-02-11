from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib import request

from .types import AssistantResponse, LLMClient, Message, ToolCall, ToolSpec


@dataclass(frozen=True)
class OpenAICompatClient(LLMClient):
    base_url: str
    api_key_env: str | None = None
    api_key: str | None = None
    debug: bool = False

    def resolve_api_key(self) -> str:
        if self.api_key and self.api_key.strip():
            return self.api_key.strip()

        if self.api_key_env:
            api_key_from_env = os.environ.get(self.api_key_env, "").strip()
            if api_key_from_env:
                return api_key_from_env

        fallback = os.environ.get("OPENAI_API_KEY", "").strip()
        if fallback:
            return fallback

        env_name = self.api_key_env or "OPENAI_API_KEY"
        raise ValueError(
            f"Missing API key. Set config.api_key, or set env var {env_name} (or OPENAI_API_KEY).",
        )

    def generate(
        self,
        *,
        model_name: str,
        messages: List[Message],
        tools: Optional[List[ToolSpec]] = None,
        timeout_seconds: int = 60,
    ) -> AssistantResponse:
        api_key = self.resolve_api_key()

        payload: Dict[str, object] = {
            "model": model_name,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
            payload["tool_choice"] = "auto"

        if self.debug:
            print("[debug] request payload:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        choice = data["choices"][0]["message"]
        if self.debug:
            print("[debug] raw response message:", file=sys.stderr)
            print(json.dumps(choice, ensure_ascii=False, indent=2), file=sys.stderr)
        text = str(choice.get("content") or "")
        raw_tool_calls = choice.get("tool_calls") or []
        tool_calls: List[ToolCall] = []
        for raw_call in raw_tool_calls:
            function_part = raw_call.get("function") or {}
            args_text = function_part.get("arguments") or "{}"
            parsed_args = json.loads(args_text)
            if not isinstance(parsed_args, dict):
                raise ValueError(f"Tool arguments must be JSON object, got: {type(parsed_args).__name__}")
            tool_calls.append(
                ToolCall(
                    id=str(raw_call["id"]),
                    name=str(function_part["name"]),
                    arguments=parsed_args,
                ),
            )

        return AssistantResponse(text=text, tool_calls=tool_calls)
