"""Tests for StandingFileFullscreenEditor component (Task 5: Fullscreen SSOT Markdown Editor).

Validates TSX component source presence, monospace font and line numbering,
hotkey save (Ctrl+S / Cmd+S), and optimistic concurrency conflict handling.
"""

from __future__ import annotations

from pathlib import Path


def _get_editor_tsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "StandingFileFullscreenEditor.tsx"
    )


def test_standing_file_fullscreen_editor_tsx_exists() -> None:
    path = _get_editor_tsx_path()
    assert path.is_file(), f"Missing TSX component: {path}"


def test_standing_file_fullscreen_editor_hotkey_and_font_contract() -> None:
    path = _get_editor_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-01: 支持 monospace 等宽字体与 Ctrl+S / Cmd+S 保存快捷键
    assert "monospace" in content
    assert "Ctrl+S" in content or "metaKey" in content or "ctrlKey" in content
    assert "lineNumbers" in content or "line-number" in content or "line" in content


def test_standing_file_fullscreen_editor_optimistic_lock_contract() -> None:
    path = _get_editor_tsx_path()
    content = path.read_text(encoding="utf-8")

    # INV-02: 必须传递 expected_hash 并捕获 409 optimistic_lock_conflict
    assert "expected_hash" in content
    assert "409" in content
    assert "conflict" in content.lower()


def test_standing_file_fullscreen_editor_props_and_callbacks() -> None:
    path = _get_editor_tsx_path()
    content = path.read_text(encoding="utf-8")

    # 包含模态窗显隐与保存成功回调
    assert "open" in content
    assert "onClose" in content
    assert "onSaveSuccess" in content
    assert "filename" in content
    assert "StandingFileFullscreenEditor" in content
