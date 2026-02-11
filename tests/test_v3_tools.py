from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.types import AssistantResponse, ToolCall
from loops.agent_loop_v3_tools import V3ToolsLoop
from loops.agent_loop_v5_skill_tools import V5SkillToolsLoop


class FakeClientV3:
    def __init__(self, target_file: str) -> None:
        self.calls = 0
        self.target_file = target_file

    async def generate(self, *, model_name, messages, tools=None, timeout_seconds=60):  # type: ignore[no-untyped-def]
        _ = (model_name, tools, timeout_seconds)
        self.calls += 1
        if self.calls == 1:
            return AssistantResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        id="tool-read-1",
                        name="read",
                        arguments={"path": self.target_file},
                    ),
                ],
            )
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        last_tool_content = str(tool_msgs[-1]["content"]) if tool_msgs else ""
        return AssistantResponse(text=f"tool says: {last_tool_content}")


class InspectingClient:
    def __init__(self) -> None:
        self.last_messages = []

    async def generate(self, *, model_name, messages, tools=None, timeout_seconds=60):  # type: ignore[no-untyped-def]
        _ = (model_name, tools, timeout_seconds)
        self.last_messages = messages
        return AssistantResponse(text="ok")


class V3ToolsLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_v3_reads_file_via_local_tools(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v3-tools-") as temp_dir:
            temp_path = Path(temp_dir)
            target_file = temp_path / "note.txt"
            target_file.write_text("hello-from-local-tools", encoding="utf-8")

            loop = V3ToolsLoop(
                client=FakeClientV3(str(target_file)),
                model_name="test-model",
                timeout_seconds=30,
            )
            text = await loop.run_turn("read the note")

            self.assertIn("hello-from-local-tools", text)
            roles = [str(msg.get("role")) for msg in loop.get_messages()]
            self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])

    async def test_v3_injects_default_cwd_for_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v3-tools-cwd-") as temp_dir:
            temp_path = Path(temp_dir)
            target_file = temp_path / "note.txt"
            target_file.write_text("cwd-injected-read", encoding="utf-8")

            loop = V3ToolsLoop(
                client=FakeClientV3("note.txt"),
                model_name="test-model",
                timeout_seconds=30,
                default_tool_cwd=str(temp_path),
            )
            text = await loop.run_turn("read relative note")
            self.assertIn("cwd-injected-read", text)

    async def test_v5_skill_injected_into_system_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v3-skills-") as temp_dir:
            skills_root = Path(temp_dir)
            skill_dir = skills_root / "demo-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text("Always answer in terse bullet points.", encoding="utf-8")

            client = InspectingClient()
            loop = V5SkillToolsLoop(
                client=client,
                model_name="test-model",
                timeout_seconds=30,
                skills_dir=str(skills_root),
            )
            self.assertTrue(loop.use_skill("demo-skill"))
            _ = await loop.run_turn("hello")

            system_message = client.last_messages[0]
            self.assertEqual(system_message.get("role"), "system")
            self.assertIn("Active Skill: demo-skill", str(system_message.get("content", "")))


if __name__ == "__main__":
    unittest.main()
