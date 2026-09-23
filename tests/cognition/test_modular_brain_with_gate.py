"""Regression: ``ModularBrain.with_gate`` must preserve ``role_profile``.

The lead-agent composition path calls ``brain.with_gate(decision_gate)`` after
``resolve_brain``. If the copy drops ``role_profile``, ``think.reason.render``
fails every lead-governed team run with "missing brain.role_profile".
"""

from __future__ import annotations

from lca.cognition.brain.pipeline.modular_brain import ModularBrain
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest


def test_with_gate_preserves_role_profile() -> None:
    rp = RoleProfile(
        role="测试角色",
        goal="目标",
        backstory="背景",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
    )
    brain = ModularBrain(reasoner=object(), classifier=object(), role_profile=rp)

    gated = brain.with_gate(decision_gate=object())

    assert gated.role_profile is rp
