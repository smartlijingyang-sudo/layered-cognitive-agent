# COMPAT(delete-when: ADR-0186 PR-3g Session-observer 收口 narrative 投影,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# narrative 是 document-driven：on_event 仅 debug-log；写盘由
# _StepTreeBundle.flush → NarrativeWriter.write(document) 触发。
# StepTreeFoldDeriver → journal.json 已产出 JournalDocument；收口时
# narrative 改读 fold snapshot，无需独立 fold 函数，再删本桥接。

"""NarrativeDeriver — wraps ``StepNarrativeWriter`` as a spine deriver.

``on_event`` is a no-op log. Narrative is built from a complete
``JournalDocument`` via ``write_document`` (terminalizer /
``_StepTreeBundle.flush``). Capability-only today; not the I-SESSION-5
fold derivation path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


class NarrativeDeriver(Deriver):
    """Deriver that delegates to a wrapped ``StepNarrativeWriter``.

    Narrative generation is document-driven, not event-driven: the legacy
    writer takes a complete ``JournalDocument`` and renders
    ``journal.narrative.md`` in one pass.  ``on_event`` therefore only
    records that events arrived (for parity with the legacy code path
    during parallel-write) without producing any partial narrative; the
    actual write happens via ``write_document`` from terminalizer.
    """

    def __init__(self, writer: StepNarrativeWriter) -> None:
        self._writer = writer

    @property
    def writer(self) -> StepNarrativeWriter:
        """Wrapped writer (test seam + boot wiring convenience)."""
        return self._writer

    @property
    def output_path(self) -> Path:
        """Convenience pass-through for boot wiring."""
        return self._writer.output_path

    def on_event(self, event: EventRecord) -> None:
        """Record arrival of a spine event.

        The narrative writer is document-driven, so individual events
        do not contribute to the rendered ``narrative.md``.  This method
        exists to satisfy the ``Deriver`` Protocol and keep the
        parallel-write wiring honest: each spine event is observable to
        the deriver, but does not change disk state.
        """
        log.debug(
            "narrative_deriver saw event execution_point=%s sequence=%s",
            event.execution_point,
            event.sequence,
        )

    def write_document(self, document: JournalDocument) -> Path:
        """Render ``journal.narrative.md`` via the wrapped writer.

        Idempotent re-renders overwrite the previous file with the
        current document (matches legacy semantics).  Returns the path
        the wrapped writer produced.
        """
        try:
            return self._writer.write(document)
        except Exception as exc:
            log.warning(
                "narrative_deriver.write_document failed err=%s",
                exc,
                exc_info=True,
            )
            raise

    def render(self, document: JournalDocument) -> Any:
        """Convenience pass-through to ``StepNarrativeWriter.render``."""
        return self._writer.render(document)


__all__ = ["NarrativeDeriver"]
