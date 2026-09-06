"""SessionFactCommitter FactGateway wiring (ADR-0194 P1-08)."""

from __future__ import annotations

from unittest.mock import patch

from lca.contracts.harness.fold.perceive import fold_context_manifest_from_events
from lca.contracts.protocols.act.command.envelope import RunFact
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.infrastructure.session.commit.fact_committer import SessionFactCommitter, emit_diagnostic
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.runtime.loop.runtime_journal import RuntimeJournalCommitter
from lca.session.append import Session


def test_commit_context_injected_returns_receipt_seq() -> None:
    session = Session("fact_committer_injected")
    token = set_publish_session(session)
    try:
        committer = SessionFactCommitter()
        ref = committer.commit_fact(
            RunFact(
                fact_id="inj-1",
                kind="context.injected",
                payload={"source": "perceive", "content_ref": "ctx-1", "model_visible": True},
            ),
            plan_ref="plan",
            node_ref="perceive",
        )
        assert ref == f"{session.id}:0"
        events = [
            event for event in session.snapshot_events() if event.type == "context.injected.v1"
        ]
        assert len(events) == 1
        assert events[0].actor == "perceive"
        assert committer.sequence == 1
    finally:
        reset_publish_session(token)


def test_commit_context_manifested_returns_receipt_seq() -> None:
    session = Session("fact_committer_manifest")
    token = set_publish_session(session)
    try:
        committer = SessionFactCommitter()
        ref = committer.commit_fact(
            RunFact(
                fact_id="man-1",
                kind="context.manifested",
                payload={"step": 3, "digest": "digest-fc"},
            ),
            plan_ref="plan",
            node_ref="perceive",
        )
        assert ref == f"{session.id}:0"
        folded = fold_context_manifest_from_events(session.snapshot_events(), step=3)
        assert folded is not None
        assert folded.digest == "digest-fc"
    finally:
        reset_publish_session(token)


def test_commit_fact_noop_when_session_unbound() -> None:
    committer = SessionFactCommitter()
    ref = committer.commit_fact(
        RunFact(
            fact_id="inj-2",
            kind="context.injected",
            payload={"source": "perceive", "content_ref": "ctx-2"},
        ),
        plan_ref="plan",
        node_ref="perceive",
    )
    assert ref == "noop:context.injected:1"


def test_commit_spine_fact_fallback_when_unbound() -> None:
    committer = SessionFactCommitter()
    evidence_ref = committer.commit_evidence("evidence-1", plan_ref="plan", node_ref="think")
    observation_ref = committer.commit_observation({"ok": True}, plan_ref="plan", node_ref="act")
    assert evidence_ref == "evidence-1"
    assert observation_ref == "act:observation:2"
    assert committer.sequence == 2


def test_runtime_journal_committer_monotonic_sequence() -> None:
    journal = RuntimeJournalCommitter()
    with patch(
        "lca.infrastructure.session.fact_committer.publish_ep_bound",
        return_value=None,
    ):
        first = journal.commit_evidence("evidence-1", plan_ref="plan", node_ref="think")
        second = journal.commit_observation({"ok": True}, plan_ref="plan", node_ref="act")
    assert first == "evidence-1"
    assert second == "act:observation:2"
    assert journal.sequence == 2


def test_commit_spine_fact_uses_receipt_seq_when_bound() -> None:
    session = Session("fact_committer_spine")
    token = set_publish_session(session)
    try:
        committer = SessionFactCommitter()
        receipt = AppendReceipt(
            event_type="spine.phase.evidence",
            seq=7,
            session_id=session.id,
            time=1,
        )
        with patch(
            "lca.infrastructure.session.fact_committer.publish_ep_bound",
            return_value=receipt,
        ) as publish:
            ref = committer.commit_evidence("evidence-2", plan_ref="plan", node_ref="think")
        publish.assert_called_once_with(
            "phase.evidence",
            {"plan_ref": "plan", "evidence_ref": "evidence-2"},
            actor="think",
        )
        assert ref == f"{session.id}:7"
    finally:
        reset_publish_session(token)


def test_emit_diagnostic_noop_when_unbound() -> None:
    emit_diagnostic(
        category="plugin",
        operation="sensor.read",
        plugin="TestSensor",
        output={"error": "boom"},
    )


def test_emit_diagnostic_routes_via_publish_ep_bound() -> None:
    session = Session("fact_committer_diag")
    token = set_publish_session(session)
    try:
        with patch("lca.infrastructure.session.fact_committer.publish_ep_bound") as publish:
            emit_diagnostic(
                category="plugin",
                operation="sensor.read",
                plugin="TestSensor",
                output={"error": "boom"},
            )
        publish.assert_called_once()
        args, kwargs = publish.call_args
        assert args[0] == "runtime.diagnostic"
        assert args[1]["operation"] == "sensor.read"
        assert kwargs["session"] is session
        assert kwargs["actor"] == "TestSensor"
    finally:
        reset_publish_session(token)
