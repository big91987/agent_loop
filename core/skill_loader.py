from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: str
    content: str


class SkillLoader:
    def __init__(self, skills_dir: str | None) -> None:
        self.skills_dir = skills_dir
        self._skills: Dict[str, SkillDefinition] = {}
        if skills_dir:
            self._skills = self._load(skills_dir)

    @staticmethod
    def _load(skills_dir: str) -> Dict[str, SkillDefinition]:
        base = Path(skills_dir).expanduser().resolve()
        if not base.exists() or not base.is_dir():
            return {}

        found: Dict[str, SkillDefinition] = {}
        for skill_md in sorted(base.rglob("SKILL.md")):
            name = skill_md.parent.name
            content = skill_md.read_text(encoding="utf-8").strip()
            if not content:
                continue
            found[name] = SkillDefinition(
                name=name,
                path=str(skill_md),
                content=content,
            )
        return found

    def list_skill_names(self) -> List[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)
