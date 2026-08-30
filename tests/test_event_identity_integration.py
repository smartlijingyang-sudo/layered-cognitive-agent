"""RunStore.append/seal 闭环填 event_id —— ADR-0096 MVA-2 Task 4 + ADR-0097.

JournalEvent 本体不带 scope（由 RunStore 盖章）；本文件只断言 engine 在
append / seal 时经 EventIdentityProvider 写入 ULID event_id。
"""

from __future__ import annotations

import re

from lca.contracts.models.observability.journal import AgentRunFinished, AgentRunStarted
from lca.infrastructure.observability.journal.engine import RunStore

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def test_runstore_append_fills_event_id() -> None:
    store = RunStore(run_id="r1")
    stamped = store.append(AgentRunStarted(agent_role="A"))
    assert stamped.event_id != ""
    assert _ULID_RE.match(stamped.event_id), f"not ULID: {stamped.event_id}"


def test_runstore_multiple_appends_have_distinct_event_ids() -> None:
    """ULID monotonic time + random 保证同 run 多次 append 产不同 event_id。"""
    store = RunStore(run_id="r1")
    s1 = store.append(AgentRunStarted(agent_role="A"))
    s2 = store.append(AgentRunStarted(agent_role="A"))
    assert s1.event_id != s2.event_id


def test_runstore_seal_terminal_event_has_event_id() -> None:
    store = RunStore(run_id="r1")
    store.append(AgentRunStarted(agent_role="A"))
    sealed = store.seal(terminal_event=AgentRunFinished(status="completed"))
    assert sealed is not None
    assert sealed.event_id != ""
    assert _ULID_RE.match(sealed.event_id), f"not ULID: {sealed.event_id}"


def test_runstore_custom_identity_provider() -> None:
    """Verify identity_provider injection works (for tests / custom derivations)."""

    class FixedIdentity:
        def derive(self, *, run_id: str, seq: int, event_type: str) -> str:
            return f"FIXED-{run_id}-{seq}-{event_type}"

    store = RunStore(run_id="r1", identity_provider=FixedIdentity())
    stamped = store.append(AgentRunStarted(agent_role="A"))
    assert stamped.event_id == "FIXED-r1-1-AgentRunStarted"
