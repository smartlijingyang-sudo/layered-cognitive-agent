"""Guard: ``BrainComposer.compose_agent`` does not project brain internals.

PR-A slim-composer refactor: the think-cluster composer is no longer
allowed to copy brain internals (``reasoner`` / ``skill_router`` /
``classifier`` / ``decision_gate`` / ``role_profile`` / ``tools`` /
``adapter``) onto ``phase_capabilities``. Graph nodes read those
collaborators through typed ports or ``runtime.brain.<attr>``; the
composer's only job is to own LLM instrumentation + Brain resolution +
optional lead gate installation.

This test pins the slim ``phase_capabilities={}`` shape: every returned
contribution from ``BrainComposer.compose_agent`` must carry an empty
``phase_capabilities`` mapping. A non-empty map signals a regression —
the slim composer is supposed to leak nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphContribution,
)
from lca.plugins.composer.think.brain_composer import BrainComposer


def _request(*, decision_gate: object | None = None) -> AgentCompositionRequest:
    """Minimal ``AgentCompositionRequest`` — only ``spec`` is read by the composer.

    ``spec.brain`` is set to a Brain instance (not a string factory key),
    which makes ``resolve_brain`` short-circuit and return that brain
    directly. This sidesteps ``BRAINS`` / ``BRAIN_PROMPT_CATALOG_FACTORY``
    / ``PROMPT_TEMPLATE_PROVIDER`` resolution while still exercising
    ``compose_agent``'s slim shape.
    """
    brain = MagicMock(name="brain")
    brain.with_gate.return_value = brain
    spec = SimpleNamespace(
        llm=MagicMock(name="llm"),
        brain=brain,
        profile=SimpleNamespace(),
        tools=(),
    )
    return AgentCompositionRequest(spec=spec, decision_gate=decision_gate)  # type: ignore[arg-type]


def _scope() -> SimpleNamespace:
    """Stand-in cordis ``Context`` — instrument_llm's ctx-soft-get is a no-op here."""
    return SimpleNamespace()


def test_brain_composer_returns_empty_phase_capabilities_without_lead_gate() -> None:
    """``BrainComposer.compose_agent`` returns ``phase_capabilities={}`` for member agents."""
    composer = BrainComposer()
    contribution: AgentGraphContribution = composer.compose_agent(_request(), _scope())
    assert dict(contribution.phase_capabilities) == {}, (
        "BrainComposer must not project brain internals onto phase_capabilities "
        "(PR-A slim-composer); nodes read typed ports / runtime.brain.* instead."
    )


def test_brain_composer_returns_empty_phase_capabilities_with_lead_gate() -> None:
    """Lead-mandate path also returns ``phase_capabilities={}``; only the brain changes."""
    composer = BrainComposer()
    lead_gate = MagicMock(name="lead_gate")
    contribution: AgentGraphContribution = composer.compose_agent(
        _request(decision_gate=lead_gate),
        _scope(),
    )
    assert dict(contribution.phase_capabilities) == {}, (
        "BrainComposer must not project brain internals onto phase_capabilities, "
        "even when a lead decision gate is installed (gate travels via "
        "ModularBrain.with_gate, not as a phase capability)."
    )


def test_brain_composer_invokes_with_gate_when_lead_decision_gate_provided() -> None:
    """The composer hands the lead decision gate to ``brain.with_gate`` (single-step helper)."""
    composer = BrainComposer()
    lead_gate = MagicMock(name="lead_gate")
    request = _request(decision_gate=lead_gate)
    composer.compose_agent(request, _scope())
    assert request.spec.brain.with_gate.call_count == 1, (
        "BrainComposer must invoke brain.with_gate(lead_gate) exactly once when a "
        "lead decision gate is installed (ModularBrain.with_gate replaces the legacy "
        "apply_lead_brain helper)."
    )
    assert request.spec.brain.with_gate.call_args.args == (lead_gate,)


def test_brain_composer_module_has_no_phase_capability_projection_call() -> None:
    """Static check: the module source must not assign to ``phase_capabilities``."""
    from pathlib import Path

    import lca.plugins.composer.think.brain_composer as mod

    src_path = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        'phase_capabilities={"gates"',
        'phase_capabilities={"phase.think',
        'phase_capabilities["reasoner"]',
        'phase_capabilities["skill_router"]',
        'phase_capabilities["classifier"]',
        'phase_capabilities["decision_gate"]',
        'phase_capabilities["adapter"]',
        'phase_capabilities["tools"]',
        "phase_capabilities[REASONER_ROLE_PROFILE.key]",
    )
    leaks = [snippet for snippet in forbidden if snippet in src_path]
    assert leaks == [], (
        "BrainComposer still projects brain internals onto phase_capabilities: "
        f"{leaks}. Move them to typed ports / runtime.brain.* access."
    )
