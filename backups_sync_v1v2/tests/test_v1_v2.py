from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.client import OpenAICompatClient
from core.config import load_config
from core.types import AssistantResponse, ToolCall
from loops.agent_loop_v1_basic import AgentStateV1, run_turn_v1
from loops.agent_loop_v2_tools import AgentStateV2, run_turn_v2
from tools.registry import get_default_tools


class FakeClientV1:
    def generate(self, *, model_name, messages, tools=None, timeout_seconds=60):  # type: ignore[no-untyped-def]
        _ = (model_name, tools, timeout_seconds)
        user_messages = [m for m in messages if m.get("role") == "user"]
        latest_text = str(user_messages[-1]["content"])
        return AssistantResponse(text=f"echo:{latest_text}")


class FakeClientV2:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, model_name, messages, tools=None, timeout_seconds=60):  # type: ignore[no-untyped-def]
        _ = (model_name, tools, timeout_seconds)
        self.calls += 1
        if self.calls == 1:
            return AssistantResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="calculate",
                        arguments={"expression": "2+3"},
                    ),
                ],
            )
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        result = str(tool_msgs[-1]["content"]) if tool_msgs else "unknown"
        return AssistantResponse(text=f"Final answer: {result}")


class AgentLoopTeachingSuiteTests(unittest.TestCase):
    def test_load_config(self) -> None:
        cfg = load_config("./config.json")
        self.assertGreater(len(cfg.provider), 0)
        self.assertGreater(len(cfg.model_name), 0)
        self.assertGreater(len(cfg.base_url), 0)
        self.assertGreater(len(cfg.default_loop_version), 0)

    def test_load_config_compat_when_api_key_env_contains_literal_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-suite-config-") as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "model_name": "gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1",
                        "api_key_env": "sk-test-literal-key",
                    },
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            cfg = load_config(str(config_path))
            self.assertEqual(cfg.api_key, "sk-test-literal-key")
            self.assertEqual(cfg.api_key_env, "OPENAI_API_KEY")

    def test_v1_basic_turn(self) -> None:
        state = AgentStateV1()
        client = FakeClientV1()
        text = run_turn_v1(
            state=state,
            client=client,
            model_name="test-model",
            user_input="hello",
        )
        self.assertEqual(text, "echo:hello")
        self.assertEqual(len(state.messages), 2)
        self.assertEqual(state.messages[0]["role"], "user")
        self.assertEqual(state.messages[1]["role"], "assistant")

    def test_v2_tool_roundtrip(self) -> None:
        state = AgentStateV2()
        client = FakeClientV2()
        tools = get_default_tools()
        text = run_turn_v2(
            state=state,
            client=client,
            model_name="test-model",
            user_input="what is 2+3",
            tools=tools,
        )
        self.assertEqual(text, "Final answer: 5")
        roles = [str(msg.get("role")) for msg in state.messages]
        self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])

    def test_client_prefers_explicit_api_key_over_env(self) -> None:
        client = OpenAICompatClient(base_url="https://example.com/v1", api_key="sk-explicit", api_key_env="DUMMY_ENV")
        self.assertEqual(client.resolve_api_key(), "sk-explicit")


if __name__ == "__main__":
    unittest.main()
