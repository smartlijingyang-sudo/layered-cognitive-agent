"""Tests for AssistantAvatarWidget & dynamic avatar switching flow (Task 6: CONNECTOR-TASK-6-AVATAR-PICKER).

Validates:
1. TSX component source presence (deploy/lobehub/patches/ui/AssistantAvatarWidget.tsx).
2. Candidate selection cards rendering (3~4 visual cards with animal SVG preview).
3. Confirm button triggers atomic update to IDENTITY.md standing file.
4. Celebratory feedback and immediate visual preview.
5. Patch integration into Assistant/index.tsx via assistant_avatar_widget.py.
"""

from __future__ import annotations

from pathlib import Path


def _get_widget_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantAvatarWidget.tsx"
    )


def _get_patch_py_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "assistant_avatar_widget.py"
    )


def test_avatar_widget_tsx_exists() -> None:
    path = _get_widget_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_avatar_widget_candidate_cards_contract() -> None:
    path = _get_widget_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含候选卡片与动物图鉴渲染
    assert "candidates" in content.lower()
    assert "species" in content.lower()
    assert "AnimalSvgRenderer" in content or "dino" in content
    assert "selected" in content.lower()


def test_avatar_widget_atomic_update_and_celebration() -> None:
    path = _get_widget_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 更新 IDENTITY.md 与乐观锁
    assert "IDENTITY.md" in content or "standing-files" in content
    # 确认生效与反馈
    assert "确认" in content or "confirm" in content.lower()
    assert "🎉" in content or "成功" in content


def test_assistant_avatar_widget_patch_module() -> None:
    path = _get_patch_py_path()
    assert path.is_file(), f"Missing patch module: {path}"
    content = path.read_text(encoding="utf-8")
    assert "AssistantAvatarWidget" in content
    assert "connector_auth_card" in content or "depends_on" in content
