"""`_load_journal_document` distinguishes a damaged journal from a bug in the command.

The journal step command turns a `None` return from `_load_journal_document` into
"journal.json 不存在或损坏" plus a non-zero exit. That answer is only trustworthy
if `None` is returned for exactly the two real conditions — the file cannot be
read, or it is not a valid step-tree document.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.cli.commands.journal.step import _load_journal_document


def _minimal_doc_json() -> str:
    """A minimal valid ``lca.journal/3`` document for the typed reader."""
    return json.dumps(
        {
            "schema": "lca.journal/3",
            "run_id": "r1",
            "trace_id": "t1",
            "started_at": 0.0,
            "steps": [
                {
                    "step_id": "step_0",
                    "step_index": 0,
                    "phase": "perceive",
                    "entered_at": 0.0,
                    "context_before": {
                        "objective": "o",
                        "attachments": [],
                        "prior_summary_chain": [],
                        "cumulative_files": [],
                    },
                    "outcome": "ok",
                }
            ],
            "metadata": {
                "agent_role": "agt",
                "strategy_key": "solo",
                "plan_ref": "p",
                "objective": "o",
            },
            "totals": {"steps": 1, "segments": 0, "phases": 0},
            "phases": [],
        },
        ensure_ascii=False,
    )


def test_valid_journal_is_returned_as_a_document(tmp_path: Path) -> None:
    (tmp_path / "journal.json").write_text(_minimal_doc_json(), encoding="utf-8")

    doc = _load_journal_document(tmp_path)

    assert doc is not None
    assert doc.steps[0].step_index == 0


def test_malformed_json_is_reported_as_no_journal(tmp_path: Path) -> None:
    (tmp_path / "journal.json").write_text("{ this is not json", encoding="utf-8")

    assert _load_journal_document(tmp_path) is None


def test_missing_journal_is_reported_as_no_journal(tmp_path: Path) -> None:
    assert _load_journal_document(tmp_path / "absent") is None


def test_unreadable_file_is_reported_as_no_journal(tmp_path: Path) -> None:
    """A directory where journal.json should be is an OSError, not a bug."""
    (tmp_path / "journal.json").mkdir()

    assert _load_journal_document(tmp_path) is None


def test_non_step_tree_schema_is_reported_as_no_journal(tmp_path: Path) -> None:
    """A legacy/non-step-tree schema is not a valid journal for this command."""
    (tmp_path / "journal.json").write_text(
        json.dumps({"schema": "lca.journal/2", "run_id": "r1"}), encoding="utf-8"
    )

    assert _load_journal_document(tmp_path) is None


def test_programming_error_is_not_labelled_a_corrupt_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anything that is not "cannot read" / "not a step-tree doc" must reach the user."""
    (tmp_path / "journal.json").write_text("{}", encoding="utf-8")

    def _boom(text: object, *args: object, **kwargs: object) -> object:
        raise TypeError("decoder called with the wrong argument type")

    monkeypatch.setattr(json, "loads", _boom)

    with pytest.raises(TypeError, match="decoder called with the wrong argument type"):
        _load_journal_document(tmp_path)
