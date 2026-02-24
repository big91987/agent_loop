from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from urllib import request

from .types import AssistantResponse, LLMClient, Message, TokenUsage, ToolCall, ToolSpec


@dataclass(frozen=True)
class OpenAICompatClient(LLMClient):
    base_url: str
    api_key_env: str | None = None
    api_key: str | None = None
    debug: bool = False
    logger: logging.Logger | None = None

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

    async def generate(
        self,
        *,
        model_name: str,
        messages: List[Message],
        tools: Optional[List[ToolSpec]] = None,
        timeout_seconds: int = 60,
        stream: bool = False,
        on_text_delta: Callable[[str], None] | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> AssistantResponse:
        return await asyncio.to_thread(
            self._generate_sync,
            model_name=model_name,
            messages=messages,
            tools=tools,
            timeout_seconds=timeout_seconds,
            stream=stream,
            on_text_delta=on_text_delta,
            should_abort=should_abort,
        )

    def _generate_sync(
        self,
        *,
        model_name: str,
        messages: List[Message],
        tools: Optional[List[ToolSpec]],
        timeout_seconds: int,
        stream: bool,
        on_text_delta: Callable[[str], None] | None,
        should_abort: Callable[[], bool] | None,
    ) -> AssistantResponse:
        if should_abort is not None and should_abort():
            raise InterruptedError("Generation aborted before request")

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
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        if self.logger:
            self.logger.debug("request payload: %s", json.dumps(payload, ensure_ascii=False, indent=2))

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
            if not stream:
                if should_abort is not None and should_abort():
                    raise InterruptedError("Generation aborted")
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                if self.logger:
                    self.logger.debug("raw response message: %s", json.dumps(choice, ensure_ascii=False, indent=2))
                text = str(choice.get("content") or "")
                raw_tool_calls = choice.get("tool_calls") or []
                tool_calls: List[ToolCall] = []
                for raw_call in raw_tool_calls:
                    function_part = raw_call.get("function") or {}
                    args_text = function_part.get("arguments") or "{}"
                    parsed_args = json.loads(args_text)
                    if not isinstance(parsed_args, dict):
                        raise ValueError(
                            f"Tool arguments must be JSON object, got: {type(parsed_args).__name__}",
                        )
                    tool_calls.append(
                        ToolCall(
                            id=str(raw_call["id"]),
                            name=str(function_part["name"]),
                            arguments=parsed_args,
                        ),
                    )
                return AssistantResponse(
                    text=text,
                    tool_calls=tool_calls,
                    usage=self._parse_usage(data.get("usage")),
                )

            text_parts: List[str] = []
            # index -> {"id": str, "name": str, "arguments": str}
            tool_call_buffers: Dict[int, Dict[str, str]] = {}
            usage: TokenUsage | None = None

            for raw_line in resp:
                if should_abort is not None and should_abort():
                    raise InterruptedError("Generation aborted")
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload_line = line[5:].strip()
                if payload_line == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_line)
                except json.JSONDecodeError:
                    continue
                if isinstance(chunk, dict):
                    chunk_usage = chunk.get("usage")
                    parsed_usage = self._parse_usage(chunk_usage)
                    if parsed_usage is not None:
                        usage = parsed_usage
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta")
                if not isinstance(delta, dict):
                    continue

                content_piece = delta.get("content")
                if isinstance(content_piece, str) and content_piece:
                    text_parts.append(content_piece)
                    if on_text_delta is not None:
                        on_text_delta(content_piece)

                raw_tool_calls = delta.get("tool_calls")
                if isinstance(raw_tool_calls, list):
                    for tc in raw_tool_calls:
                        if not isinstance(tc, dict):
                            continue
                        idx = tc.get("index", 0)
                        if not isinstance(idx, int):
                            idx = 0
                        buf = tool_call_buffers.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        tc_id = tc.get("id")
                        if isinstance(tc_id, str) and tc_id:
                            buf["id"] = tc_id
                        fn = tc.get("function")
                        if isinstance(fn, dict):
                            fn_name = fn.get("name")
                            if isinstance(fn_name, str) and fn_name:
                                # Some providers stream function name in fragments.
                                if buf["name"] and not fn_name.startswith(buf["name"]):
                                    buf["name"] += fn_name
                                else:
                                    buf["name"] = fn_name
                            fn_args = fn.get("arguments")
                            if isinstance(fn_args, str) and fn_args:
                                buf["arguments"] += fn_args

            tool_calls: List[ToolCall] = []
            for idx in sorted(tool_call_buffers.keys()):
                item = tool_call_buffers[idx]
                raw_args = item["arguments"].strip() or "{}"
                try:
                    parsed_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}
                if not isinstance(parsed_args, dict):
                    parsed_args = {"_value": parsed_args}
                tool_calls.append(
                    ToolCall(
                        id=item["id"] or f"stream-call-{idx}",
                        name=item["name"] or "unknown_tool",
                        arguments=parsed_args,
                    ),
                )

            return AssistantResponse(text="".join(text_parts), tool_calls=tool_calls, usage=usage)

    @staticmethod
    def _parse_usage(raw_usage: object) -> TokenUsage | None:
        if not isinstance(raw_usage, dict):
            return None
        prompt = int(
            raw_usage.get("prompt_tokens", raw_usage.get("promptTokens", raw_usage.get("input_tokens", 0))) or 0,
        )
        completion = int(
            raw_usage.get("completion_tokens", raw_usage.get("completionTokens", raw_usage.get("output_tokens", 0)))
            or 0,
        )
        total = int(raw_usage.get("total_tokens", raw_usage.get("totalTokens", 0)) or 0)
        if total <= 0:
            total = prompt + completion
        return TokenUsage(
            prompt_tokens=max(0, prompt),
            completion_tokens=max(0, completion),
            total_tokens=max(0, total),
            source="provider",
        )
