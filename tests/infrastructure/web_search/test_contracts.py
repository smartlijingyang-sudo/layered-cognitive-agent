"""Tests for lca.contracts.models.cognition.web_search.

Covers: enum values / frozen dataclasses / Citation render format /
SearchRequest defaults.

Note: expected citation strings use \\u escapes (\\u3010 = open bracket,
\\u2020 = dagger, \\u3011 = close bracket) so the source never contains a
literal citation mark.
"""

import dataclasses

import pytest

from lca.contracts.models.cognition.web_search import (
    Citation,
    SearchOutcome,
    SearchRequest,
    SearchResult,
    SearchTier,
    Verdict,
    Vertical,
)

CITE_OPEN = "【"
CITE_SEP = "†"
CITE_CLOSE = "】"


def _cite(url: str, lines: str) -> str:
    # builds the expected render without a literal citation mark in source
    return CITE_OPEN + url + CITE_SEP + lines + CITE_CLOSE


def test_vertical_values() -> None:
    assert {v.value for v in Vertical} == {
        "news",
        "sports",
        "weather",
        "finance",
        "datetime",
    }


def test_tier_order() -> None:
    assert [t.value for t in SearchTier] == ["search", "fetch", "browse"]


def test_verdict_values() -> None:
    assert Verdict.SEARCHED.value == "searched"
    assert Verdict.VERIFIED.value == "verified"


def test_citation_render_single_line() -> None:
    c = Citation(url="https://example.com/a", line=3)
    assert c.render() == _cite("https://example.com/a", "L3")


def test_citation_render_range() -> None:
    c = Citation(url="https://example.com/a", line=3, line_end=5)
    assert c.render() == _cite("https://example.com/a", "L3-L5")


def test_citation_render_same_line_end() -> None:
    c = Citation(url="https://example.com/a", line=3, line_end=3)
    assert c.render() == _cite("https://example.com/a", "L3")


def test_contracts_frozen() -> None:
    r = SearchResult(title="t", url="https://example.com")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.title = "x"  # type: ignore[misc]
    req = SearchRequest(query="q")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.query = "y"  # type: ignore[misc]


def test_search_request_defaults() -> None:
    req = SearchRequest(query="playwright headless detection")
    assert req.vertical is None
    assert req.need_text is False
    assert req.max_results == 10
    assert req.vertical_params == {}


def test_search_outcome_defaults() -> None:
    o = SearchOutcome()
    assert o.results == ()
    assert o.tier_reached is SearchTier.SEARCH
    assert o.verdict is Verdict.SEARCHED
    assert o.page_text == ""
