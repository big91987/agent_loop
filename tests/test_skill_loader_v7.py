from __future__ import annotations

from pathlib import Path

from core.skill_loader_v7 import SkillLoaderV7


def test_skill_loader_v7_merges_multiple_roots(tmp_path: Path) -> None:
    openclaw_root = tmp_path / "openclaw"
    claude_root = tmp_path / "claude"
    (openclaw_root / "tavily-search").mkdir(parents=True)
    (claude_root / "pptx").mkdir(parents=True)

    (openclaw_root / "tavily-search" / "SKILL.md").write_text(
        "---\nname: tavily-search\ndescription: Tavily search skill\n---\n# Tavily\n",
        encoding="utf-8",
    )
    (claude_root / "pptx" / "SKILL.md").write_text(
        "---\nname: pptx\ndescription: PPT skill\n---\n# PPTX\n",
        encoding="utf-8",
    )

    loader = SkillLoaderV7(f"{openclaw_root}:{claude_root}")

    assert loader.list_skill_names() == ["pptx", "tavily-search"]
    assert loader.get("tavily-search") is not None
    assert loader.get("pptx") is not None


def test_skill_loader_v7_keeps_first_duplicate(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "shared").mkdir(parents=True)
    (second / "shared").mkdir(parents=True)

    (first / "shared" / "SKILL.md").write_text(
        "---\nname: shared\ndescription: first\n---\n# First\n",
        encoding="utf-8",
    )
    (second / "shared" / "SKILL.md").write_text(
        "---\nname: shared\ndescription: second\n---\n# Second\n",
        encoding="utf-8",
    )

    loader = SkillLoaderV7(f"{first}:{second}")
    skill = loader.get("shared")

    assert skill is not None
    assert skill.path == str(first / "shared" / "SKILL.md")
