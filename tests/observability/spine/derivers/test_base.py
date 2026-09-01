"""Tests for the Deriver Protocol (Task 2.1).

A deriver is a subscriber to EventSpine that consumes each
``EventRecord`` to derive secondary artefacts (step-tree, narrative,
live tail, ...). Per FD-2, a deriver that raises must NOT block the
spine: the failing call is logged on ``spine.deriver_failed`` and
business continues. The sink still receives the event.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

if TYPE_CHECKING:
    import pytest


def test_deriver_failing_one_does_not_block_business(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """FD-2 containment: a bad deriver does not stop the spine."""

    class BadDeriver:
        def on_event(self, event) -> None:
            raise RuntimeError("deriver boom")

    fs = FileSink(tmp_path, run_id="r1")
    spine = EventSpine(sinks=[fs], subscribers=[BadDeriver().on_event])
    span = SpineContext.push_span("brain.think.start")
    try:
        with caplog.at_level(
            logging.WARNING,
            logger="lca.infrastructure.observability.spine.event_spine",
        ):
            rec = spine.append(
                execution_point="brain.think.start",
                channel="fact",
                caller_payload={},
                span_ctx=span,
            )
    finally:
        spine.close()
        SpineContext.pop_span("brain.think.start")

    # business continues — append returned a record
    assert rec is not None
    assert rec.execution_point == "brain.think.start"
    # FD-2 channel emitted the failure
    assert any("spine.deriver_failed" in record.getMessage() for record in caplog.records), (
        caplog.text
    )
    # event still landed on the sink
    assert (tmp_path / "events.jsonl").exists()


def test_deriver_protocol_satisfied_by_structural_class() -> None:
    """A class with the right attribute is recognized as a Deriver."""

    class GoodDeriver:
        def on_event(self, event) -> None:
            return None

    from lca.infrastructure.observability.spine.derivers.base import Deriver

    assert isinstance(GoodDeriver(), Deriver)
