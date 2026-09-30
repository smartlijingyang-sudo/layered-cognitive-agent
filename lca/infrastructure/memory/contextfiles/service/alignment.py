"""Load and persist the nightly alignment synthesis document.

The synthesis is a curated Markdown file under the assistant home. It is
written by the dream pipeline and read back during context assembly so the
model sees a soft alignment signal.
"""

from __future__ import annotations

import logging

from lca.infrastructure.memory.contextfiles.domain.alignment import (
    SynthesisAssertion,
    render_alignment_synthesis,
)
from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.events.publisher import SynthesisWritten
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore

logger = logging.getLogger(__name__)


def load_alignment_synthesis(
    store: FileStore,
    *,
    layout: ContextLayout | None = None,
) -> str:
    """Return the synthesis Markdown, or empty when the home has none."""

    chosen = packaged_layout() if layout is None else layout
    try:
        return store.read_text(chosen.alignment_synthesis_path)
    except OSError:
        return ""


def write_alignment_synthesis(
    store: FileStore,
    assertions: list[SynthesisAssertion],
    *,
    date: str,
    note: str,
    layout: ContextLayout | None = None,
    publisher: DomainEventPublisher | None = None,
) -> str:
    """Render and persist the synthesis. Returns the written relative path."""

    chosen = packaged_layout() if layout is None else layout
    text = render_alignment_synthesis(assertions, date=date, note=note)
    store.atomic_replace(chosen.alignment_synthesis_path, text)
    logger.info(
        "alignment synthesis wrote path=%s assertions=%s",
        chosen.alignment_synthesis_path,
        len(assertions),
    )
    if publisher is not None:
        publisher.publish(
            SynthesisWritten(
                path=chosen.alignment_synthesis_path,
                assertion_count=len(assertions),
            )
        )
    return chosen.alignment_synthesis_path


__all__ = ["load_alignment_synthesis", "write_alignment_synthesis"]
