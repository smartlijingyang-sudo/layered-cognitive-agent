"""Sediment-before-compact (ADR-0283 C1/C2).

Before a semantic compaction strategy (``summarize``/``spill``) discards
the head of the working-context payload, the sediment pass extracts
candidate facts from the doomed region and persists them through the
memory write path with ``metadata["source"] = "compaction"``.

Fail-closed: if the sediment pass raises, persists nothing when it
should have, or no writer is installed, the caller must NOT summarize —
it degrades to ``truncate_oldest`` (byte cut; no semantics lost beyond
what truncation already loses). "0 sedimented + summarize" is the audit
red line (ADR-0283 C2).

Writer injection: :func:`sediment_writer_scope` (ContextVar). Production
bootstrap (installing :class:`AssistantMemorySedimentWriter` at run
entry) is follow-up work (ADR-0283 B1); until then the node degrades,
which is behaviorally identical to today's truncate-only world.

v1 extraction is a deterministic heuristic (marker lines + structured
dicts). An LLM-backed extractor is future work (ADR-0283 B2); the
heuristic's recall ceiling is documented, not hidden.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord

SedimentCategory = Literal["decision", "commitment", "entity_state", "open_question", "fact"]
"""Fine-grained fact class. Persisted as ``MemoryCategory.FACT`` with this
value in ``metadata["sediment_category"]`` (MemoryCategory is a closed
enum; sediment classes are not members)."""

# v1 heuristic: explicit marker lines. Recall ceiling documented in ADR-0283 B2.
_SEDIMENT_MARKER_RE = re.compile(
    r"^\s*(decision|决定|commitment|承诺|todo|待办|fact|事实|state|状态"
    r"|open[ _-]?question|未决事项|未决)"
    r"\s*[:：]\s*(.+?)\s*$",
    re.IGNORECASE,
)

_CATEGORY_BY_MARKER: dict[str, SedimentCategory] = {
    "decision": "decision",
    "决定": "decision",
    "commitment": "commitment",
    "承诺": "commitment",
    "todo": "commitment",
    "待办": "commitment",
    "fact": "fact",
    "事实": "fact",
    "state": "entity_state",
    "状态": "entity_state",
    "open question": "open_question",
    "open_question": "open_question",
    "open-question": "open_question",
    "openquestion": "open_question",
    "未决事项": "open_question",
    "未决": "open_question",
}

# Structured dict payloads: case-insensitive key → category.
_DICT_KEY_CATEGORY: dict[str, SedimentCategory] = {
    "decision": "decision",
    "commitment": "commitment",
    "todo": "commitment",
    "fact": "fact",
    "entity_state": "entity_state",
    "state": "entity_state",
    "open_question": "open_question",
}

_MAX_CANDIDATE_CHARS = 500


@dataclass(frozen=True, slots=True)
class SedimentCandidate:
    """One fact extracted from the compacted-away region, ready to persist."""

    content: str
    category: SedimentCategory
    dedupe_key: str
    source_index: int
    """Index of the payload item this candidate was extracted from."""


def _dedupe_key(category: str, content: str) -> str:
    digest = hashlib.sha256(f"{category}:{content}".encode()).hexdigest()[:16]
    return f"compaction:{digest}"


def _candidate(
    *, raw: str, category: SedimentCategory, source_index: int
) -> SedimentCandidate | None:
    content = raw.strip()
    if not content:
        return None
    content = content[:_MAX_CANDIDATE_CHARS]
    return SedimentCandidate(
        content=content,
        category=category,
        dedupe_key=_dedupe_key(category, content),
        source_index=source_index,
    )


def extract_sediment_candidates(
    payload: tuple[Any, ...],
) -> tuple[SedimentCandidate, ...]:
    """Deterministically extract sediment candidates from a payload region.

    Pure function (no I/O): string items are scanned line-by-line for
    ``<marker>: <content>`` lines; dict items are scanned for known fact
    keys. Anything else is skipped — v1 does not guess semantics from
    opaque objects (documented recall ceiling, ADR-0283 B2).
    """
    found: list[SedimentCandidate] = []
    for index, item in enumerate(payload):
        if isinstance(item, str):
            for line in item.splitlines():
                match = _SEDIMENT_MARKER_RE.match(line)
                if not match:
                    continue
                marker = match.group(1).strip().lower()
                category = _CATEGORY_BY_MARKER.get(marker)
                if category is None:
                    continue
                candidate = _candidate(raw=match.group(2), category=category, source_index=index)
                if candidate is not None:
                    found.append(candidate)
        elif isinstance(item, dict):
            for key, value in item.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue
                category = _DICT_KEY_CATEGORY.get(key.strip().lower())
                if category is None or not value.strip():
                    continue
                candidate = _candidate(raw=value, category=category, source_index=index)
                if candidate is not None:
                    found.append(candidate)
    return tuple(found)


class SedimentWriter(Protocol):
    """Persist sediment candidates; return the number actually persisted."""

    def write(self, candidates: tuple[SedimentCandidate, ...]) -> int: ...


_sediment_writer: ContextVar[SedimentWriter | None] = ContextVar(
    "lca_sediment_writer", default=None
)


def get_sediment_writer() -> SedimentWriter | None:
    """Return the installed writer, or ``None`` when no bootstrap installed one."""
    return _sediment_writer.get()


def set_sediment_writer(writer: SedimentWriter | None) -> Token:
    """Install (or clear) the writer; returns the reset token."""
    return _sediment_writer.set(writer)


@contextmanager
def sediment_writer_scope(writer: SedimentWriter | None) -> Iterator[None]:
    """Install ``writer`` for the enclosed block (tests / run bootstrap)."""
    token = _sediment_writer.set(writer)
    try:
        yield
    finally:
        _sediment_writer.reset(token)


class AssistantMemorySedimentWriter:
    """Adapt an ``upsert``-capable memory to :class:`SedimentWriter`.

    Duck-typed on ``upsert(record)`` so ``nodes/`` does not import
    infrastructure: pass an ``AssistantMemory`` (or a test fake).
    Every candidate lands as ``SEMANTIC`` / ``FACT`` with
    ``metadata["source"] = "compaction"`` (ADR-0283 C1 provenance).
    """

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def write(self, candidates: tuple[SedimentCandidate, ...]) -> int:
        written = 0
        for candidate in candidates:
            record = MemoryRecord(
                record_id=new_id("mem"),
                content=candidate.content,
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.9,
                category=MemoryCategory.FACT,
                dedupe_key=candidate.dedupe_key,
                confidence=1.0,
                metadata={
                    "source": "compaction",
                    "sediment_category": candidate.category,
                },
            )
            self._memory.upsert(record)
            written += 1
        return written


__all__ = [
    "AssistantMemorySedimentWriter",
    "SedimentCandidate",
    "SedimentCategory",
    "SedimentWriter",
    "extract_sediment_candidates",
    "get_sediment_writer",
    "sediment_writer_scope",
    "set_sediment_writer",
]
