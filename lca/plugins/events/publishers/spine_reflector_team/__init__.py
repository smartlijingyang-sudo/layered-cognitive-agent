"""spine_reflector_team — ADR-0181 PR-6。

team 维度 7 EP（PR-6 新加，old manifest 没有）：
- team.casting.started / .completed / .failed
- team.delegation.issued / .completed
- team.delegation.cache_hit
- team.message.published
（team.delegation.cache_hit 与 lca.contracts.event 中已有
Category.TEAM_DELEGATION_CACHE_HIT 对应，本 publisher 提供 spine 侧
typed publisher；业务方在 EventMechanism 路径下走这条线即可。）
"""

from lca.plugins.events.publishers.spine_reflector_team.plugin import (
    ReflectorClass,
    emit_team_casting_completed,
    emit_team_casting_failed,
    emit_team_casting_started,
    emit_team_delegation_cache_hit,
    emit_team_delegation_completed,
    emit_team_delegation_issued,
    emit_team_message_published,
)

__all__ = [
    "ReflectorClass",
    "emit_team_casting_completed",
    "emit_team_casting_failed",
    "emit_team_casting_started",
    "emit_team_delegation_cache_hit",
    "emit_team_delegation_completed",
    "emit_team_delegation_issued",
    "emit_team_message_published",
]
