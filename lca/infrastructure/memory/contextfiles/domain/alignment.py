"""Nightly alignment synthesis as a deterministic Markdown document.

The synthesis is a curated set of assertions about how the user wants the
assistant to behave. Every assertion carries a ``message:xxx`` reference
back to the trail or episode evidence that produced it, so a later reader
can audit the provenance without an LLM. The document is injected into
context assembly so it acts as a soft alignment signal, never a hard
instruction.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_MESSAGE = re.compile(r"message:([A-Za-z0-9_-]+)")
_ASSERTION = re.compile(r"^\s*-\s+(.+)$")


@dataclass(frozen=True, slots=True)
class SynthesisAssertion:
    """One alignment assertion with its evidence reference."""

    message_id: str
    content: str


def render_alignment_synthesis(
    assertions: Sequence[SynthesisAssertion],
    *,
    date: str,
    note: str = "",
) -> str:
    """Render the alignment synthesis document.

    Every assertion line embeds ``message:<id>`` so the document's
    references are always present. ``note`` explains that the synthesis is
    a soft alignment signal derived from evidence.
    """

    lines = [
        "# Alignment Synthesis",
        "",
        f"生成日期: {date}",
        "",
    ]
    if note:
        lines.append(note)
        lines.append("")
    lines.append("## 行为调参断言")
    lines.append("")
    for assertion in assertions:
        content = assertion.content.strip()
        if not content:
            continue
        lines.append(f"- {content} (message:{assertion.message_id})")
    lines.append("")
    return "\n".join(lines)


def parse_alignment_synthesis(text: str) -> tuple[SynthesisAssertion, ...]:
    """Read assertions and their message references from a synthesis file."""

    assertions: list[SynthesisAssertion] = []
    for line in text.splitlines():
        bullet = _ASSERTION.match(line)
        if bullet is None:
            continue
        body = bullet.group(1)
        match = _MESSAGE.search(body)
        if match is None:
            continue
        content = _MESSAGE.sub("", body).strip()
        content = re.sub(r"\s+\(\s*\)$", "", content).strip()
        assertions.append(SynthesisAssertion(message_id=match.group(1), content=content))
    return tuple(assertions)


def assertions_from_evidence(
    evidence: Sequence[tuple[str, str]],
) -> tuple[SynthesisAssertion, ...]:
    """Map ``(message_id, content)`` evidence into synthesis assertions.

    Duplicate contents keep their first id and later ids are dropped so the
    document stays concise. The remaining id still appears in the document.
    """

    seen: set[str] = set()
    assertions: list[SynthesisAssertion] = []
    for message_id, content in evidence:
        key = content.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        assertions.append(SynthesisAssertion(message_id=message_id, content=content))
    return tuple(assertions)


__all__ = [
    "SynthesisAssertion",
    "assertions_from_evidence",
    "parse_alignment_synthesis",
    "render_alignment_synthesis",
]
