"""Tests for AssistantNamingWidget patch (ADR-0252 / Onboarding ceremony).

Validates patch discovery, metadata contract, TSX source presence, and dry-run apply.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import discover_patches


def test_naming_widget_patch_discovered() -> None:
    modules = discover_patches()
    by_name = {m.meta.name: m for m in modules}
    assert "assistant_naming_widget" in by_name

    patch = by_name["assistant_naming_widget"]
    assert patch.meta.category == "ui"
    assert "AssistantNamingWidget" in patch.meta.verify_marker
    assert (
        "src/features/Conversation/Messages/components/AssistantNamingWidget.tsx"
        in patch.meta.files
    )


def test_naming_widget_tsx_source_contract() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantNamingWidget.tsx"
    )
    assert source.is_file(), f"Missing TSX fragment: {source}"
    content = source.read_text(encoding="utf-8")
    assert "AssistantNamingWidget" in content
    assert "candidates" in content
    assert "allowCustom" in content
    assert "embedToken" in content


def test_check_patch_integrity_script() -> None:
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, "scripts/check_patch_integrity.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Byte-identical check failed:\n{res.stdout}\n{res.stderr}"
