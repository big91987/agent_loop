from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class SkillDefinitionV7:
    name: str
    path: str
    content: str
    description: str
    license: str | None = None
    source_dir: str | None = None


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


def _iter_skill_roots(skills_dir: str | None) -> Iterable[Path]:
    if not skills_dir:
        return []
    roots: list[Path] = []
    seen: set[Path] = set()
    for raw_part in str(skills_dir).split(os.pathsep):
        part = raw_part.strip()
        if not part:
            continue
        root = Path(part).expanduser().resolve()
        if root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


class SkillLoaderV7:
    def __init__(self, skills_dir: str | None) -> None:
        self.skills_dir = skills_dir
        self._skills: Dict[str, SkillDefinitionV7] = {}
        if skills_dir:
            self._skills = self._load(skills_dir)

    @staticmethod
    def _load(skills_dir: str) -> Dict[str, SkillDefinitionV7]:
        found: Dict[str, SkillDefinitionV7] = {}
        for base in _iter_skill_roots(skills_dir):
            if not base.exists() or not base.is_dir():
                continue
            for skill_md in sorted(base.rglob("SKILL.md")):
                name = skill_md.parent.name
                if name in found:
                    continue
                raw_text = skill_md.read_text(encoding="utf-8").strip()
                if not raw_text:
                    continue
                metadata, body = _extract_frontmatter(raw_text)
                description = _extract_description(name, body or raw_text, metadata)
                license_value = metadata.get("license")
                found[name] = SkillDefinitionV7(
                    name=name,
                    path=str(skill_md),
                    content=raw_text,
                    description=description,
                    license=license_value,
                    source_dir=str(base),
                )
        return found

    def list_skill_names(self) -> List[str]:
        return sorted(self._skills.keys())

    def list_skills(self) -> List[SkillDefinitionV7]:
        return [self._skills[name] for name in self.list_skill_names()]

    def get(self, name: str) -> SkillDefinitionV7 | None:
        return self._skills.get(name)

