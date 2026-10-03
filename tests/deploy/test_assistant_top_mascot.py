"""Tests for AssistantTopMascot component (Task 3: Muse-style animated top mascot).

Validates TSX component source presence, gentle breathing CSS animations,
event callback contracts, and avatar/name presentation.
"""

from __future__ import annotations

from pathlib import Path


def _get_mascot_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "AssistantTopMascot.tsx"
    )


def test_assistant_top_mascot_tsx_exists() -> None:
    path = _get_mascot_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_assistant_top_mascot_breathing_animation_contract() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-01: 必须具备平滑呼吸与浮动 CSS 动画
    assert "keyframes" in content or "@keyframes" in content
    assert "mascotBreath" in content or "breathe" in content.lower()
    # 呼吸动画需有微位移与缩放 (translateY / scale)
    assert "translateY" in content or "scale" in content


def test_assistant_top_mascot_props_and_events_contract() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-02: 必须支持 onOpenDrawer 回调与 assistantId / name / status
    assert "onOpenDrawer" in content
    assert "assistantId" in content
    assert "name" in content
    assert "AssistantTopMascot" in content


def test_assistant_top_mascot_renders_mascot_visual_and_status() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含 SVG Mascot 与状态指示点
    assert "<svg" in content or "svg" in content.lower()
    assert "statusDot" in content or "status" in content


def test_assistant_top_mascot_supports_custom_avatar_image() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 必须支持 avatarUrl prop 与 isImageUrl 检测
    assert "avatarUrl" in content
    assert "isImageUrl" in content or "effectiveAvatarUrl" in content
    # 必须包含自定义头像图片渲染类与 fallback
    assert "mascot-custom-avatar" in content or "<img" in content
    assert "AnimalSvgRenderer" in content


def test_assistant_top_mascot_retains_drawer_click_and_effects_with_avatar_image() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 无论使用 SVG 还是自定义图片头像，都必须保留量子环、呼吸浮动与抽屉唤起回调
    assert "onOpenDrawer" in content
    assert "mascot-quantum-orbit" in content or "quantumOrbit" in content
    assert "haloGlow" in content
    assert "mascotSvg" in content
    assert "onClick" in content
    assert "namePill" in content
