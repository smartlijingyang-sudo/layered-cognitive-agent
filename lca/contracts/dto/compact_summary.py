"""CompactSummary — structured summary produced by ``think.context.summarize``.

ADR-0283 C4: the summary is not free text. It is a frozen DTO with one
list per fact class plus an honest ``dropped`` ledger: every payload item
that was discarded *without* being sedimented must appear here (as a
truncated repr), so "what did we lose" is answerable from the receipt
alone instead of being silent.

``prompt_version`` pins which summarize-prompt version produced this
summary; ``summarize.py::SUMMARIZE_PROMPT_VERSION`` must match the
``summarize_prompt.md`` header marker (drift is a test failure, T4).

ADR-0195 §1.4 / C13: frozen Pydantic model with ``extra="forbid"``,
like its sibling :class:`CompactReceipt`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CompactSummary(BaseModel):
    """Typed evidence of what a summarize pass kept and dropped.

    Fields:
        decisions: decision statements preserved from the compacted region.
        commitments: commitments / TODOs preserved from the compacted region.
        entity_states: entity-state facts preserved from the compacted region.
        open_questions: unresolved items preserved from the compacted region.
        dropped: truncated reprs of discarded items that yielded no
            sediment candidate — the honest "we lost this" ledger.
            Capped by the producer (see ``summarize.MAX_DROPPED_LEDGER``).
        prompt_version: summarize-prompt version that produced this summary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decisions: tuple[str, ...] = ()
    commitments: tuple[str, ...] = ()
    entity_states: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    prompt_version: str = Field(default="v1", min_length=1)


__all__ = ["CompactSummary"]
