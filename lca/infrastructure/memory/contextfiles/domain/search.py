"""Pure full-text search terms and scoring for the memory index.

The index backend lives behind a port. This module only turns text into
terms, a query into a MATCH expression, and scores hits so every backend
ranks the same way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

_ALNUM = re.compile(r"[A-Za-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_SPACE = re.compile(r"\s+")


def tokenize(text: str) -> tuple[str, ...]:
    """Split ``text`` into lowercase terms.

    Latin words and underscore identifiers are kept whole. CJK text has no
    word boundaries, so every CJK character becomes one term. This matches
    the substring behaviour a model expects from ``memory_search``.
    """

    lowered = text.lower()
    terms: list[str] = []
    for match in _ALNUM.finditer(lowered):
        terms.append(match.group(0))
    terms.extend(_CJK.findall(lowered))
    return tuple(terms)


def index_terms(text: str) -> frozenset[str]:
    """Return the distinct terms of ``text`` for building an index."""

    return frozenset(tokenize(text))


def fts_query(terms: Sequence[str]) -> str:
    """Build a safe FTS5 MATCH expression from user query terms.

    Empty input produces an expression that matches nothing. Each term is
    quoted so punctuation cannot inject a query.
    """

    cleaned = [term for term in terms if term]
    if not cleaned:
        return '"__no_match__"'
    return " OR ".join(f'"{term}"' for term in cleaned)


def rank_document(query_terms: Sequence[str], content: str) -> int:
    """Score ``content`` against ``query_terms`` for deterministic ordering.

    A whole-term occurrence counts ten, a term occurrence counts two, and
    a full-content substring match counts ten more.
    """

    lowered = content.lower()
    score = 0
    for term in query_terms:
        if term in lowered:
            score += 2
            if lowered == term:
                score += 10
    if query_terms and "".join(query_terms) in lowered:
        score += 10
    return score


def best_documents(
    documents: Iterable[tuple[str, str, str]],
    query: str,
    *,
    limit: int,
) -> list[tuple[str, str, str]]:
    """Rank ``(doc_id, content, path)`` triples and return the best ``limit``.

    This is the shared ranking used when an index backend is unavailable.
    """

    terms = tokenize(query)
    scored = [
        (rank_document(terms, content), doc_id, content, path)
        for doc_id, content, path in documents
        if any(term in content.lower() for term in terms)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [(doc_id, content, path) for _score, doc_id, content, path in scored[:limit]]


__all__ = ["best_documents", "fts_query", "index_terms", "rank_document", "tokenize"]
