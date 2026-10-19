"""RA-168: developer rows converge across the three derive paths.

One ``surface/developer_message`` journal row (ADR-0268 §6 cron handoff) must
be interpreted identically by:

(a) ``RunSessionWriter.derive_messages`` — the LLM wire
    (``think.history.assemble``);
(b) the shared SSOT ``derive_event_message`` (+ ``derive_messages`` /
    ``export_transcript`` in ``lca/plugins/session/runtime/messages`` —
    the ``model_visible`` projection and ``token_usage``);
(c) the kernel ``foldSurface`` (transcript/history reads).

Pre-RA-168 these were passthrough / silent-drop / fail-loud ValueError.
"""

from __future__ import annotations

from lca.plugins.session.runtime.messages.messages import (
    derive_event_message,
    derive_messages,
    export_transcript,
)
from lca.runtime.session.run_session_writer import RunSessionWriter
from lca.session.append import Session
from lca_kernel.events.fold.fold import (
    foldSurface,
    isAppendSurfaceEvent,
    isSurfaceEligibleType,
)

EXPECTED = [{"role": "developer", "content": "cron worker report"}]


def _dev_session() -> tuple[Session, RunSessionWriter]:
    session = Session("test-dev-converge")
    writer = RunSessionWriter(session=session)
    writer.append_developer_message(
        message_id="h1",
        content="cron worker report",
        job_id="job-1",
        run_id="run-1",
    )
    return session, writer


def test_developer_row_is_kernel_surface_eligible() -> None:
    """Kernel fold admits the DSH extension type; fold no longer raises."""
    session, _ = _dev_session()
    (event,) = session.snapshot_events()
    assert event.type == "surface/developer_message"
    assert isSurfaceEligibleType(event.type)
    surface = foldSurface(list(session.snapshot_events()))
    assert list(surface.nodes) == [0]


def test_developer_marker_converged_to_append_contract() -> None:
    """The type-suffixed ``surface_op='developer_message'`` marker is gone."""
    session, _ = _dev_session()
    (event,) = session.snapshot_events()
    assert isAppendSurfaceEvent(event)


def test_wire_ssot_transcript_agree_on_developer_row() -> None:
    """All three derive paths include the row with the same shape."""
    session, writer = _dev_session()
    events = list(session.snapshot_events())
    assert writer.derive_messages() == EXPECTED
    assert derive_messages(events) == EXPECTED
    assert export_transcript(events) == EXPECTED
    assert derive_event_message(events[0]) == EXPECTED[0]


def test_handoff_provenance_survives_in_journal() -> None:
    """job_id / run_id stay in the journal for replay provenance."""
    session, _ = _dev_session()
    (event,) = session.snapshot_events()
    assert event.data["job_id"] == "job-1"
    assert event.data["run_id"] == "run-1"
