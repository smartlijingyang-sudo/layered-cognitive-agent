"""Tests for the persistent assistant workspace (ADR-0244 D7.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.workspace import WorkspaceService


def _make_home(tmp_path: Path, assistant_id: str = "asst_1") -> Path:
    home = tmp_path / assistant_id
    (home / "workspace").mkdir(parents=True, exist_ok=True)
    return home


def test_workspace_write_read_roundtrip(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    service = WorkspaceService()
    ws = service.open("asst_1", home)

    ws.write_text("notes.md", "hello workspace")

    assert ws.read_text("notes.md") == "hello workspace"
    assert ws.read("notes.md") == b"hello workspace"


def test_workspace_list_returns_relative_paths(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    service = WorkspaceService()
    ws = service.open("asst_1", home)

    ws.write_text("a.txt", "a")
    ws.write_text("sub/b.txt", "b")

    assert ws.list() == ["a.txt", "sub/b.txt"]


def test_workspace_rejects_path_traversal(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    service = WorkspaceService()
    ws = service.open("asst_1", home)

    with pytest.raises(ValueError):
        ws.write("../escape.txt", b"x")
    with pytest.raises(ValueError):
        ws.read("../secret.txt")


def test_workspace_cross_assistant_isolation(tmp_path: Path) -> None:
    home_a = _make_home(tmp_path, "asst_a")
    home_b = _make_home(tmp_path, "asst_b")
    service = WorkspaceService()

    ws_a = service.open("asst_a", home_a)
    ws_b = service.open("asst_b", home_b)

    ws_a.write_text("private.md", "A secret")
    assert ws_b.list() == []
    assert not (home_b / "workspace" / "private.md").exists()


def test_workspace_does_not_touch_manifest_digest(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    manifest = home / "manifest.json"
    manifest.write_text('{"revision_seq": 1}', encoding="utf-8")
    before = manifest.read_bytes()

    service = WorkspaceService()
    ws = service.open("asst_1", home)
    ws.write_text("outputs/report.md", "report")

    assert manifest.read_bytes() == before
    assert (home / "workspace" / "outputs" / "report.md").is_file()
