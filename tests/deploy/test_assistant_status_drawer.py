"""Tests for AssistantStatusDrawer component (Task 4: Right-side status drawer).

Validates TSX component source presence, three horizontal sections
(Identity / Memory / Workspace), standing files card rendering, and
fullscreen edit trigger contracts.
"""

from __future__ import annotations

from pathlib import Path


def _get_drawer_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantStatusDrawer.tsx"
    )


def test_assistant_status_drawer_tsx_exists() -> None:
    path = _get_drawer_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_assistant_status_drawer_sections_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-01: 必须提供 Identity、Memory、Workspace 三大横向 Section 切换
    assert "Identity" in content or "identity" in content
    assert "Memory" in content or "memory" in content
    assert "Workspace" in content or "workspace" in content


def test_assistant_status_drawer_standing_files_contract() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-02: 必须覆盖 4 大核心 Standing Files 与「全屏编辑」入口
    assert "IDENTITY.md" in content
    assert "SOUL.md" in content
    assert "USER.md" in content
    assert "MEMORY.md" in content
    assert "onEditFile" in content
    assert "standing-files" in content


def test_assistant_status_drawer_props_and_layout() -> None:
    path = _get_drawer_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含抽屉显隐控制与 480px 宽度规范
    assert "open" in content
    assert "onClose" in content
    assert "480" in content
    assert "AssistantStatusDrawer" in content
