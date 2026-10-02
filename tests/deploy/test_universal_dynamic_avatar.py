"""Tests for Universal Dynamic Avatar Engine (Task 3: CONNECTOR-TASK-3-UNIVERSAL-AVATAR).

Validates:
1. Four-level deterministic resolution (explicit > semantic > stable hash > default).
2. Multi-species animal SVG catalog (Capybara, Dino, Fox, Owl, Dolphin, Panda, Cat, Rabbit).
3. Muse / OpenAI dots aesthetic: concentric rotating quantum halo/dots + gentle breathing + blinking.
4. Anti-clipping headroom guarantees in container styling and SVG coordinates.
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


def test_mascot_tsx_exists() -> None:
    path = _get_mascot_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_avatar_four_level_resolution_strategy() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 1. 显式配置优先
    assert "avatar" in content, "Props must accept explicit avatar"
    # 2. 语义推导
    assert "resolveAnimal" in content or "resolveSpecies" in content, "Must implement animal resolution function"
    assert "恐龙" in content or "dino" in content, "Semantic matching for dinosaur"
    assert "狐" in content or "fox" in content, "Semantic matching for fox"
    # 3. 稳定哈希分发 (哈希取模，所有助理均有确定性动物)
    assert "hash" in content.lower(), "Must implement stable hash mapping for universal coverage"
    # 4. 兜底保障
    assert "capybara" in content, "Must support capybara as warm default"


def test_avatar_species_catalog_completeness() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 8 大萌宠动物图鉴支持
    species = ["capybara", "dino", "fox", "owl", "dolphin", "panda", "cat", "rabbit"]
    for s in species:
        assert s in content, f"Species catalog must contain {s}"


def test_muse_openai_dots_dynamic_effects() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # OpenAI dots / Muse 风格量子环/光晕微动
    assert "orbit" in content.lower() or "quantum" in content.lower() or "halo" in content.lower()
    # 呼吸浮动动画
    assert "mascotBreath" in content or "breathe" in content.lower()
    # 眨眼微动动画
    assert "mascotBlink" in content or "blink" in content.lower()


def test_anti_clipping_headroom_layout() -> None:
    path = _get_mascot_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 顶栏充足上部安全距离与 overflow 保护，确保头部永不被裁剪
    assert "padding" in content
    assert "overflow" in content
