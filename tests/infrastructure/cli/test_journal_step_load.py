"""`_load_journal` distinguishes a damaged journal from a bug in the command.

The journal step command turns a `None` return from `_load_journal` into
"journal.json 不存在或损坏" plus a non-zero exit. That answer is only trustworthy
if `None` is returned for exactly the two real conditions — the file cannot be
read, or it is not valid JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.cli.commands.journal.step import _load_journal


def test_valid_journal_is_returned_as_a_dict(tmp_path: Path) -> None:
    (tmp_path / "journal.json").write_text(
        json.dumps({"steps": [{"step_index": 0}]}), encoding="utf-8"
    )

    doc = _load_journal(tmp_path)

    assert doc is not None
    assert doc["steps"][0]["step_index"] == 0


def test_malformed_json_is_reported_as_no_journal(tmp_path: Path) -> None:
    (tmp_path / "journal.json").write_text("{ this is not json", encoding="utf-8")

    assert _load_journal(tmp_path) is None


def test_missing_journal_is_reported_as_no_journal(tmp_path: Path) -> None:
    assert _load_journal(tmp_path / "absent") is None


def test_unreadable_file_is_reported_as_no_journal(tmp_path: Path) -> None:
    """A directory where journal.json should be is an OSError, not a bug."""
    (tmp_path / "journal.json").mkdir()

    assert _load_journal(tmp_path) is None


def test_programming_error_is_not_labelled_a_corrupt_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anything that is not "cannot read" / "not JSON" must reach the user."""
    (tmp_path / "journal.json").write_text("{}", encoding="utf-8")

    def _boom(text: object, *args: object, **kwargs: object) -> object:
        raise TypeError("decoder called with the wrong argument type")

    monkeypatch.setattr(json, "loads", _boom)

    with pytest.raises(TypeError, match="decoder called with the wrong argument type"):
        _load_journal(tmp_path)
