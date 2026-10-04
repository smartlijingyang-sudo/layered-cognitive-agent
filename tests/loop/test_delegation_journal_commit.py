"""DelegationJournal commit tests (ADR-0194 P1-16)."""

from __future__ import annotations

from lca.loop.commit.delegation_journal import commit_delegation_cache_hit
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def test_commit_delegation_cache_hit_publishes_fact() -> None:
    session = Session("t-delegation-hit-1")
    token = set_publish_session(session)
    try:
        receipt = commit_delegation_cache_hit(callee_role="coder", subtask="fix login", step=3)
        assert receipt is not None
        assert receipt.event_type == "spine.team.delegation.cache_hit"
        assert receipt.session_id == "t-delegation-hit-1"
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "spine.team.delegation.cache_hit"
        assert event.data["execution_point"] == "team.delegation.cache_hit"
        payload = event.data["payload"]
        assert payload["callee_role"] == "coder"
        assert payload["subtask"] == "fix login"
        assert payload["step"] == 3
    finally:
        reset_publish_session(token)


def test_commit_delegation_cache_hit_default_actor_on_explicit_session() -> None:
    session = Session("t-delegation-hit-2")
    receipt = commit_delegation_cache_hit(
        callee_role="coder", subtask="fix login", step=0, session=session
    )
    assert receipt is not None
    assert session.event_count == 1
    event = session.event_at(0)
    assert event is not None
    assert event.type == "spine.team.delegation.cache_hit"
    assert event.actor == "delegation"


def test_commit_delegation_cache_hit_honors_actor_override() -> None:
    session = Session("t-delegation-hit-3")
    receipt = commit_delegation_cache_hit(
        callee_role="reviewer", subtask="audit", step=1, session=session, actor="team"
    )
    assert receipt is not None
    event = session.event_at(0)
    assert event is not None
    assert event.actor == "team"


def test_commit_delegation_cache_hit_noop_when_unbound() -> None:
    assert commit_delegation_cache_hit(callee_role="coder", subtask="x", step=0) is None
