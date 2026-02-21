from __future__ import annotations

import inspect
import json
from typing import Callable, Dict, List, Set

from core.types import ToolSpec
from tools.registry import build_tool_registry, tool_specs_for_names

from .base import BaseAgentLoop


class V3ToolsLoop(BaseAgentLoop):
    def __init__(
        self,
        *,
        max_tool_rounds: int = 8,
        default_tool_cwd: str | None = None,
        verbose: bool = True,
        trace_callback: Callable[[str], None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        # Teaching point: v3 switches to six CLI-style file/navigation tools.
        self.tool_names: Set[str] = {"read", "write", "edit", "grep", "find", "ls"}
        self.tools: List[ToolSpec] = tool_specs_for_names(self.tool_names)
        self.max_tool_rounds = max_tool_rounds
        self.default_tool_cwd = default_tool_cwd
        self.verbose = verbose
        self.trace_callback = trace_callback
        self._tool_registry: Dict[str, ToolSpec] = build_tool_registry(self.tools)

    @staticmethod
    def _summarize_text(text: str, *, limit: int = 120) -> str:
        one_line = " ".join(text.split())
        if len(one_line) <= limit:
            return one_line
        return f"{one_line[:limit]}..."

    def _print_tool_call(self, name: str, args: Dict[str, object]) -> None:
        args_text = json.dumps(args, ensure_ascii=False, sort_keys=True)
        self._emit_trace(f"[TOOL CALL] {name} args={self._summarize_text(args_text, limit=160)}")

    def _print_tool_result(self, name: str, output: str) -> None:
        summary = self._summarize_text(output)
        self._emit_trace(f"[TOOL RESULT] {name} {summary}")

    async def run_turn(self, user_input: str) -> str:
        self.state.messages.append({"role": "user", "content": user_input})
        final_text = ""
        hit_round_limit = True

        for round_index in range(self.max_tool_rounds):
            if self.verbose:
                print(f"\n[ROUND {round_index + 1}]")
                print("[MODEL]")
            streamed = False

            def _on_text_delta(delta: str) -> None:
                nonlocal streamed
                streamed = True
                if self.verbose:
                    print(delta, end="", flush=True)

            response = await self._call_llm(tools=self.tools, on_text_delta=_on_text_delta)
            if self.verbose:
                if streamed:
                    print()
                elif response.text.strip():
                    print(response.text.strip())

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
                hit_round_limit = False
                break

            for call in response.tool_calls:
                tool = self._tool_registry.get(call.name)
                if not tool:
                    tool_output = f"Tool not found: {call.name}"
                    self._print_tool_call(call.name, call.arguments)
                else:
                    call_args = dict(call.arguments)
                    # v3 teaching point: CLI-like tools often need cwd; we inject default cwd here.
                    if call.name in self.tool_names and "cwd" not in call_args and self.default_tool_cwd:
                        call_args["cwd"] = self.default_tool_cwd
                    self._print_tool_call(call.name, call_args)
                    try:
                        maybe_output = tool.handler(call_args)
                        if inspect.isawaitable(maybe_output):
                            tool_output = await maybe_output
                        else:
                            tool_output = str(maybe_output)
                    except Exception as err:  # noqa: BLE001
                        tool_output = f"Tool execution error: {err}"
                self._print_tool_result(call.name, tool_output)

                self.state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": tool_output,
                    },
                )

        if hit_round_limit and not final_text:
            final_text = (
                f"[loop warning] reached max_tool_rounds={self.max_tool_rounds}; "
                "the model kept issuing tool calls and did not produce a final text answer. "
                "Try asking it to summarize progress or continue from current state."
            )
            self.state.messages.append({"role": "assistant", "content": final_text})

        return final_text
    def _emit_trace(self, line: str) -> None:
        if self.verbose:
            print(line)
        if self.trace_callback is not None:
            self.trace_callback(line)
