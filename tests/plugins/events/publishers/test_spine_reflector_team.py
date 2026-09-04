"""spine_reflector_team publisher 端到端测试（ADR-0181 PR-6）。"""

from __future__ import annotations

from typing import Any


def test_emit_team_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_team import (
        plugin,
    )

    ref = plugin.emit_team_casting_started(team_id="t1", requested_roles=["r1"], run_id="r1")
    assert ref.category == "spine.team.casting.started"
    ref = plugin.emit_team_casting_completed(team_id="t1", selected_roles=["r1"], run_id="r1")
    assert ref.category == "spine.team.casting.completed"
    ref = plugin.emit_team_casting_failed(team_id="t1", reason="x", run_id="r1")
    assert ref.category == "spine.team.casting.failed"
    ref = plugin.emit_team_delegation_issued(
        team_id="t1", callee_role="r1", subtask="s1", run_id="r1"
    )
    assert ref.category == "spine.team.delegation.issued"
    ref = plugin.emit_team_delegation_completed(
        team_id="t1", callee_role="r1", subtask="s1", outcome="success", run_id="r1"
    )
    assert ref.category == "spine.team.delegation.completed"
    ref = plugin.emit_team_delegation_cache_hit(
        team_id="t1", callee_role="r1", subtask="s1", step=1, run_id="r1"
    )
    assert ref.category == "spine.team.delegation.cache_hit"
    ref = plugin.emit_team_message_published(team_id="t1", sender="s", recipient="r", run_id="r1")
    assert ref.category == "spine.team.message.published"
