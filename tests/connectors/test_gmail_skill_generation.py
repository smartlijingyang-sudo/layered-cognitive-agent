"""Tests for Gmail SKILL.md generation and materialization (INV-03)."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.connectors.gmail.skill import (
    generate_gmail_skill_content,
    materialize_gmail_skill,
)


def test_generate_gmail_skill_content_inv03() -> None:
    content = generate_gmail_skill_content()
    assert "name: gmail" in content
    assert "includeInPrompt: true" in content
    assert "[widget:connector_auth?" in content
    assert "Do NOT generate markdown links" in content
    assert "250 units/minute" in content
    assert "+send --to <email>" in content
    assert "--upload <path>" in content


def test_materialize_gmail_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "gmail"
    materialize_gmail_skill(skill_dir)

    skill_file = skill_dir / "SKILL.md"
    manifest_file = skill_dir / "manifest.yaml"

    assert skill_file.is_file()
    assert manifest_file.is_file()
    assert "name: gmail" in skill_file.read_text(encoding="utf-8")
    assert "rate_limits:" in manifest_file.read_text(encoding="utf-8")
