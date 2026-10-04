"""Tests for phase.think.context.sediment marker extraction (ADR-0283 C1).

Sediment is the deterministic "salvage before compact" pass: before a
semantic compaction discards the head of the working-context payload,
explicit ``<marker>: <content>`` lines are extracted and persisted with
``metadata["source"] = "compaction"``. Node-level fail-closed behavior
(writer raises / missing / partial write) is pinned in
``test_summarize.py``; this file pins the extraction contract itself.

The load-bearing invariant: **a marker the regex accepts must never be
silently dropped by the category map**. Regression evidence: commit
``f04929658`` fixed exactly this — ``open-question:`` matched the regex
but was missing from ``_CATEGORY_BY_MARKER``, so the candidate was
silently discarded (data loss with zero signal). The parametrized
``test_marker_map_regex_consistency`` would have been red the whole time.
"""

from __future__ import annotations

import pytest

from lca.nodes.think.context.sediment import (
    _CATEGORY_BY_MARKER,
    _DICT_KEY_CATEGORY,
    _MAX_CANDIDATE_CHARS,
    extract_sediment_candidates,
)


@pytest.mark.parametrize("marker", sorted(_CATEGORY_BY_MARKER))
def test_marker_map_regex_consistency(marker: str) -> None:
    """Every mapped marker survives extraction with its mapped category.

    Guards the f04929658 bug class: regex accepts the marker but the map
    lacks it, which previously dropped the candidate with no signal.
    """
    expected = _CATEGORY_BY_MARKER[marker]
    (candidate,) = extract_sediment_candidates((f"{marker}: keep this",))
    assert candidate.category == expected
    assert candidate.content == "keep this"


@pytest.mark.parametrize(
    "line",
    [
        "open-question: migrate the database",
        "open question: migrate the database",
        "open_question: migrate the database",
        "openquestion: migrate the database",
        "OPEN-QUESTION: migrate the database",  # IGNORECASE
        "未决：迁移数据库",  # full-width colon
    ],
)
def test_open_question_variants_all_extract(line: str) -> None:
    """The hyphen variant regression nail: must not be silently dropped."""
    (candidate,) = extract_sediment_candidates((line,))
    assert candidate.category == "open_question"
    assert candidate.content


@pytest.mark.parametrize("key", sorted(_DICT_KEY_CATEGORY))
def test_dict_key_map_consistency(key: str) -> None:
    """Every structured-dict key in the map survives extraction too."""
    expected = _DICT_KEY_CATEGORY[key]
    (candidate,) = extract_sediment_candidates(({key: "keep this"},))
    assert candidate.category == expected
    assert candidate.content == "keep this"


@pytest.mark.parametrize(
    "line",
    [
        "banana: split",  # unknown marker: regex never matches
        "no colon here at all",
        "decision:",  # marker without content: no capture group match
        "   ",  # blank line
    ],
)
def test_unrecognized_lines_are_dropped(line: str) -> None:
    """v1 does not guess semantics from opaque lines (ADR-0283 B2)."""
    assert extract_sediment_candidates((line,)) == ()


def test_source_index_tracks_payload_position() -> None:
    """Provenance: the candidate records which payload item it came from."""
    candidates = extract_sediment_candidates(
        ("noise without markers", {"fact": "real"}, "decision: also real")
    )
    assert [c.source_index for c in candidates] == [1, 2]
    assert [c.content for c in candidates] == ["real", "also real"]


def test_content_never_exceeds_cap() -> None:
    """Extracted content is truncated to the documented cap."""
    (candidate,) = extract_sediment_candidates(("decision: " + "x" * (_MAX_CANDIDATE_CHARS * 10),))
    assert len(candidate.content) == _MAX_CANDIDATE_CHARS


def test_dedupe_key_distinguishes_category() -> None:
    """Same text under different markers dedupes independently."""
    candidates = extract_sediment_candidates(("decision: same text", "fact: same text"))
    assert len(candidates) == 2
    assert candidates[0].dedupe_key != candidates[1].dedupe_key


def test_empty_payload_returns_empty() -> None:
    assert extract_sediment_candidates(()) == ()
