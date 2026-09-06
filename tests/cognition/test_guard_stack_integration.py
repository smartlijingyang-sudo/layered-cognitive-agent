"""Guard stack bundle wiring tests (ADR-0197)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUNDLES = ROOT / "bundles"


def _bundle_text(name: str) -> str:
    return (BUNDLES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bundle",
    ["web-app.yaml", "scenario-standard.yaml"],
)
def test_bundle_declares_loop_policy_before_gates(bundle: str) -> None:
    text = _bundle_text(bundle)
    loop_idx = text.index("loop.policy.default")
    gate_idx = text.index("gate.repeat-tool-call")
    assert loop_idx < gate_idx, f"{bundle}: loop.policy must boot before gate plugins"


def test_web_app_declares_act_guards_before_safe_executor() -> None:
    text = _bundle_text("web-app.yaml")
    for plugin_id in (
        "tool.guards.service",
        "guard.tool-timeout",
        "guard.tool-result-spill",
    ):
        assert plugin_id in text
    guards_idx = text.index("tool.guards.service")
    executor_idx = text.index("safe_executor.simple")
    assert guards_idx < executor_idx


def test_guard_stack_bundle_declares_act_guards() -> None:
    text = _bundle_text("guard-stack.yaml")
    for plugin_id in (
        "loop.policy.default",
        "tool.guards.service",
        "guard.tool-timeout",
        "guard.tool-result-spill",
    ):
        assert plugin_id in text


@pytest.mark.asyncio
async def test_default_profile_boots_guard_stack_capabilities() -> None:
    from lca.application.api.api import ensure_default_ctx

    scope = await ensure_default_ctx()
    loop_policy = scope.inject("loop_guard_policy")
    assert hasattr(loop_policy, "thresholds")
    assert hasattr(loop_policy, "repeat_thresholds")
    tool_guards = scope.inject("tool_guards")
    assert len(tool_guards.ordered()) >= 2
    convergence = scope.inject("convergence_policy")
    assert convergence is not None
