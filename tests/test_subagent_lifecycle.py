from __future__ import annotations

from lca.contracts.harness.subagent_lifecycle import SubagentLifecycle


def test_only_active_subagents_accept_work() -> None:
    assert SubagentLifecycle.ACTIVE.can_accept_work() is True
    assert SubagentLifecycle.DRAINING.can_accept_work() is False
    assert SubagentLifecycle.DISPOSED.can_accept_work() is False
    assert SubagentLifecycle.DISPOSE_FAILED.can_accept_work() is False
