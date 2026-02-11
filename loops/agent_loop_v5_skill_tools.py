from __future__ import annotations

from core.skill_loader import SkillLoader

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

    def list_skills(self) -> list[str]:
        return self.skill_loader.list_skill_names()

    def use_skill(self, name: str) -> bool:
        if self.skill_loader.get(name) is None:
            return False
        self.active_skill_name = name
        return True

    def disable_skill(self) -> None:
        self.active_skill_name = None

    def _apply_skill_prompt(self) -> None:
        if not self.active_skill_name:
            self.state.system_prompt = self._base_system_prompt
            return
        skill = self.skill_loader.get(self.active_skill_name)
        if not skill:
            self.state.system_prompt = self._base_system_prompt
            return
        self.state.system_prompt = (
            f"{self._base_system_prompt}\n\n"
            f"[Active Skill: {skill.name}]\n"
            f"{skill.content}\n"
        )

    async def run_turn(self, user_input: str) -> str:
        self._apply_skill_prompt()
        return await super().run_turn(user_input)
