from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: str
    content: str
    description: str
    license: str | None = None


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, text
    end = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end < 0:
        return {}, text

    metadata: dict[str, str] = {}
    for raw_line in lines[1:end]:
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = _strip_quotes(value.strip())
        if key and value:
            metadata[key] = value
    body = "\n".join(lines[end + 1 :]).strip()
    return metadata, body


def _extract_description(name: str, content: str, metadata: dict[str, str]) -> str:
    explicit = metadata.get("description", "").strip()
    if explicit:
        return explicit

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        return stripped[:300]

    return f"Skill instructions for {name}."


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
            raw_text = skill_md.read_text(encoding="utf-8").strip()
            if not raw_text:
                continue
            metadata, body = _extract_frontmatter(raw_text)
            description = _extract_description(name, body or raw_text, metadata)
            license_value = metadata.get("license")
            found[name] = SkillDefinition(
                name=name,
                path=str(skill_md),
                content=raw_text,
                description=description,
                license=license_value,
            )
        return found

    def list_skill_names(self) -> List[str]:
        return sorted(self._skills.keys())

    def list_skills(self) -> List[SkillDefinition]:
        return [self._skills[name] for name in self.list_skill_names()]

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)
