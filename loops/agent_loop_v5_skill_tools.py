from __future__ import annotations

from typing import Dict

from core.skill_loader import SkillLoader
from core.types import ToolSpec
from tools.registry import build_tool_registry
from tools.bash_tool import BashTool

from .agent_loop_v4_mcp_tools import V4MCPToolsLoop


class V5SkillToolsLoop(V4MCPToolsLoop):
    def __init__(
        self,
        *,
        skills_dir: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._base_system_prompt = self.state.system_prompt
        self.skill_loader = SkillLoader(skills_dir)
        self.active_skill_name: str | None = None
        self._base_tools = [*self._base_tools, BashTool().to_spec(), self._build_read_skill_tool()]
        self.tools = list(self._base_tools)
        self._tool_registry = build_tool_registry(self.tools)

    def list_skills(self) -> list[str]:
        return self.skill_loader.list_skill_names()

    def use_skill(self, name: str) -> bool:
        if self.skill_loader.get(name) is None:
            return False
        self.active_skill_name = name
        return True

    def disable_skill(self) -> None:
        self.active_skill_name = None

    @staticmethod
    def _print_skill_call(skill_name: str) -> None:
        print(f"[SKILL CALL] read_skill name={skill_name}")

    def _build_read_skill_tool(self) -> ToolSpec:
        async def _handler(params: Dict[str, object]) -> str:
            skill_name = str(params.get("name", "")).strip()
            self._print_skill_call(skill_name or "<empty>")
            if not skill_name:
                return "Missing required parameter: name"
            skill = self.skill_loader.get(skill_name)
            if not skill:
                return f"Skill not found: {skill_name}"
            return (
                f'<skill name="{skill.name}" location="{skill.path}">\n'
                f"{skill.content}\n"
                "</skill>"
            )

        return ToolSpec(
            name="read_skill",
            description=(
                "Load full instructions for a skill by name. "
                "Use this when a task matches an available skill from <available_skills>."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name from <available_skills> (for example: pptx).",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=_handler,
        )

    def _build_available_skills_block(self) -> str:
        lines = ["<available_skills>"]
        for skill in self.skill_loader.list_skills():
            lines.extend(
                [
                    "  <skill>",
                    f"    <name>{skill.name}</name>",
                    f"    <description>{skill.description}</description>",
                    f"    <location>{skill.path}</location>",
                    "  </skill>",
                ],
            )
        lines.append("</available_skills>")
        return "\n".join(lines)

    def _apply_skill_prompt(self) -> None:
        available_skills = self._build_available_skills_block()
        preferred = ""
        if self.active_skill_name:
            preferred = (
                "\n\n[Preferred Skill]\n"
                f"- name: {self.active_skill_name}\n"
                "Use read_skill to load it if relevant to the user's request."
            )
        self.state.system_prompt = (
            f"{self._base_system_prompt}\n\n"
            "Skills are loaded with progressive disclosure.\n"
            "First inspect available skill metadata, then call read_skill(name) only when needed.\n\n"
            f"{available_skills}"
            f"{preferred}"
        )

    async def run_turn(self, user_input: str) -> str:
        self._apply_skill_prompt()
        return await super().run_turn(user_input)
