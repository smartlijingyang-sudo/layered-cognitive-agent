"""InboxFollowupCreated journal emission on /runs entry (PR8.E.1).

Per v3 §6 / PR8, every user message that flows into a Run is a followup
on the Inbox — not a direct LLM call.  The driver MUST publish an
``InboxFollowupCreated`` event before the loop starts, carrying the
question as ``payload_preview`` so the inbox-facts sensor (PR8) can
fold it into the next perceive cycle.

This test pins down the contract on the CognitiveRunDriver side.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_driver(driver, session, hub, *, question, mode):
    """Invoke the driver in a fresh asyncio.run loop so ContextVars propagate."""

    import contextlib

    from lca.contracts.models.team.run_context import RunContext

    async def _go() -> None:
        # Driver may fail later (no real sandbox / bindings); we only
        # care that InboxFollowupCreated is recorded at entry.
        with contextlib.suppress(Exception):
            await driver.execute(
                session,
                question=question,
                mode=mode,
                hub=hub,
                bindings=None,
                run_context=RunContext(session_id="sess"),
                llm_resolver=_StubLLMResolver(),
            )

    asyncio.run(_go())


class TestInboxFollowupCreation:
    def test_run_creation_emits_inbox_followup(self, tmp_path: Path) -> None:
        """``CognitiveRunDriver.execute`` MUST emit InboxFollowupCreated."""
        from gateway.runs.loop_drivers import CognitiveRunDriver
        from gateway.runs.runnable_assembly import CognitiveRunnableAssembler
        from gateway.runs.session import RunSession
        from lca.contracts.models.observability.journal import InboxFollowupCreated, RunScope
        from lca.layer0_infra.observability import bind_backends, run_scope
        from tests.support.observability_helpers import make_test_bound

        hub = make_test_bound()
        session = RunSession(
            run_id="run-test",
            trace_id="trace-test",
            jsonl_path=tmp_path / "inbox.jsonl",
            tail=None,  # type: ignore[arg-type]
            hub=hub,
            question="hello world",
            user_text="hello world",
            mode="solo",
        )
        # LLM 解析会先失败；装配器仅用于保持依赖显式。
        driver = CognitiveRunDriver(cast("CognitiveRunnableAssembler", object()))
        with (
            bind_backends(hub),
            run_scope(RunScope(trace_id=session.trace_id, run_id=session.run_id)),
        ):
            _run_driver(
                driver,
                session,
                hub,
                question=session.question,
                mode=session.mode,
            )

        inbox_events = [
            stamped.event
            for stamped in hub.journal.store.events
            if isinstance(stamped.event, InboxFollowupCreated)
        ]
        assert inbox_events, "CognitiveRunDriver must record InboxFollowupCreated on entry"
        assert len(inbox_events) >= 1

    def test_inbox_followup_carries_question(self, tmp_path: Path) -> None:
        """The first ``InboxFollowupCreated`` MUST carry the question."""
        from gateway.runs.loop_drivers import CognitiveRunDriver
        from gateway.runs.runnable_assembly import CognitiveRunnableAssembler
        from gateway.runs.session import RunSession
        from lca.contracts.models.observability.journal import InboxFollowupCreated, RunScope
        from lca.layer0_infra.observability import bind_backends, run_scope
        from tests.support.observability_helpers import make_test_bound

        question = "帮我总结这份文档的关键点"
        hub = make_test_bound()
        session = RunSession(
            run_id="run-test2",
            trace_id="trace-test2",
            jsonl_path=tmp_path / "inbox2.jsonl",
            tail=None,  # type: ignore[arg-type]
            hub=hub,
            question=question,
            user_text=question,
            mode="solo",
        )
        # LLM 解析会先失败；装配器仅用于保持依赖显式。
        driver = CognitiveRunDriver(cast("CognitiveRunnableAssembler", object()))
        with (
            bind_backends(hub),
            run_scope(RunScope(trace_id=session.trace_id, run_id=session.run_id)),
        ):
            _run_driver(
                driver,
                session,
                hub,
                question=session.question,
                mode=session.mode,
            )

        inbox_events = [
            stamped.event
            for stamped in hub.journal.store.events
            if isinstance(stamped.event, InboxFollowupCreated)
        ]
        assert inbox_events
        first = inbox_events[0]
        # Question MUST show up as payload_preview.
        assert first.payload_preview == question
        # Actor / target / priority must be set (non-empty defaults).
        assert first.actor
        assert first.target
        assert first.priority


class _StubLLMResolver:
    """Stub resolver: returns a fake LLM that immediately fails fast.

    The real driver path may continue / fail; we only care that the
    InboxFollowupCreated event is recorded BEFORE the LLM is invoked.
    """

    def resolve(self, *, mode: str | None = None):
        raise RuntimeError("stub: no LLM")
