"""Tests for the shared assistant-domain IO helpers.

Drive the real functions in ``lca/infrastructure/assistant/io.py`` used by the
assistant catalog plugin, home layout, persona, and self-manage tools.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.assistant.io import (
    load_grants,
    read_json,
    read_json_soft,
    sha256_digest,
    write_json,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_read_json_returns_dict(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    _write(p, '{"a": 1}')
    assert read_json(p) == {"a": 1}


def test_read_json_raises_on_non_dict(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    _write(p, "[1, 2, 3]")
    with pytest.raises(ValueError, match="顶层不是 JSON object"):
        read_json(p)


def test_read_json_raises_on_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, "{not json")
    with pytest.raises(ValueError):
        read_json(p)


def test_read_json_soft_returns_empty_on_missing(tmp_path: Path) -> None:
    assert read_json_soft(tmp_path / "missing.json") == {}


def test_read_json_soft_returns_empty_on_invalid(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, "{nope")
    assert read_json_soft(p) == {}


def test_read_json_soft_returns_empty_on_non_dict(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    _write(p, "[1]")
    assert read_json_soft(p) == {}


def test_read_json_soft_returns_dict(tmp_path: Path) -> None:
    p = tmp_path / "ok.json"
    _write(p, '{"x": 1}')
    assert read_json_soft(p) == {"x": 1}


def test_write_json_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "out.json"
    write_json(p, {"b": 2, "a": [1, 2]})
    assert read_json(p) == {"b": 2, "a": [1, 2]}
    # sort_keys is on: "a" appears before "b" in the raw text.
    text = p.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')


def test_sha256_digest_prefix(tmp_path: Path) -> None:
    p = tmp_path / "file.bin"
    _write(p, "hello world")
    digest = sha256_digest(p)
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_sha256_digest_is_stable(tmp_path: Path) -> None:
    p = tmp_path / "file.bin"
    _write(p, "same content")
    assert sha256_digest(p) == sha256_digest(p)


def test_load_grants_missing_returns_empty(tmp_path: Path) -> None:
    assert load_grants(tmp_path) == frozenset()


def test_load_grants_parses_strings(tmp_path: Path) -> None:
    home = tmp_path
    _write(home / "grants.yaml", "grants:\n  - read.files\n  - write.tools\n")
    assert load_grants(home) == frozenset({"read.files", "write.tools"})


def test_load_grants_filters_non_strings(tmp_path: Path) -> None:
    home = tmp_path
    _write(home / "grants.yaml", "grants:\n  - read.files\n  - 42\n  - \n")
    assert load_grants(home) == frozenset({"read.files"})


def test_load_grants_non_list_returns_empty(tmp_path: Path) -> None:
    home = tmp_path
    _write(home / "grants.yaml", "grants:\n  read.files: true\n")
    assert load_grants(home) == frozenset()


def test_load_grants_invalid_yaml_returns_empty(tmp_path: Path) -> None:
    home = tmp_path
    _write(home / "grants.yaml", "grants: [unclosed\n")
    assert load_grants(home) == frozenset()
