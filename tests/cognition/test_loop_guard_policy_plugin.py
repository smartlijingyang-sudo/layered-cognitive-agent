"""Loop guard policy plugin tests (ADR-0197)."""

from __future__ import annotations

from lca.cognition.brain.guard.loop_policy import LoopGuardPolicyView, StaticLoopGuardPolicy
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.plugins.cognitive.loop.policy.plugin import Config, setup


def test_plugin_declares_loop_guard_policy_capability() -> None:
    defn = setup._lca_definition
    assert "loop_guard_policy" in defn.provided_capability_keys


def test_static_policy_exposes_thresholds() -> None:
    view = LoopGuardPolicyView(
        thresholds=LoopPolicyThresholds(repeat_warn=5, progress_break=8),
        repeat_thresholds=(3, 5, 8),
    )
    policy = StaticLoopGuardPolicy(view)
    assert policy.thresholds.repeat_warn == 5
    assert policy.thresholds.progress_break == 8


def test_static_policy_exposes_repeat_thresholds() -> None:
    view = LoopGuardPolicyView(
        thresholds=LoopPolicyThresholds(),
        repeat_thresholds=(3, 5, 8),
        arguments_preview_chars=500,
    )
    policy = StaticLoopGuardPolicy(view)
    assert policy.repeat_thresholds == (3, 5, 8)
    assert policy.arguments_preview_chars == 500


def test_config_defaults_match_dsh_repeat_reminder() -> None:
    cfg = Config()
    assert cfg.repeat_warn == 3
    assert cfg.progress_break == 6
