"""Acceptance tests for the candidate-only self-improving plugin bundle.

The learning scenario must resolve as a real plugin graph, but no component in
this first vertical slice may install a skill or apply a production Profile.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.think.eval_comparison import EvalComparison
from lca.contracts.protocols.think.learning import SkillAcquirer
from lca.contracts.protocols.composition.logic_address import score_logic_address
from lca.harness.plugin_declaration import definition_from_plugin
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.insight.failure_analyzer import FailureAnalyzerService
from lca.plugins.profile.evolver import ProfileEvolverService
from lca.plugins.skill.auto_acquire import AutoAcquireSkillService
from lca.plugins.skill.auto_acquire import setup as auto_acquire_setup
from lca.plugins.tools.profile_apply import ProfileApplyTool
from lca.plugins.tools.profile_diff import ProfileDiffTool

REPO = Path(__file__).resolve().parents[2]


def _comparison(*, passed: bool) -> EvalComparison:
    return EvalComparison(
        expected_status="completed",
        actual_status="completed" if passed else "failed",
    )


def test_self_improving_minimal_profile_resolves_and_compiles() -> None:
    """The non-default learning profile is a real, deterministic plugin graph."""

    resolved = resolve_profile("profiles/self-improving-minimal.yaml")
    plan = compile_plan(resolved)
    provided = {
        capability
        for plugin in resolved.plugins
        for capability in plugin.definition.provided_capability_keys
    }

    assert {
        "learning.skill_acquirer",
        "learning.failure_analyzer",
        "learning.profile_evolver",
        "tools.profile_diff",
        "tools.profile_apply",
    }.issubset(provided)
    assert plan.capability.provider_bindings


def test_auto_acquire_is_a_typed_g11_checkpoint_primitive() -> None:
    """Skill acquisition is a run-scoped, evidence-observing G11 primitive."""

    service = AutoAcquireSkillService(enabled=True, min_confidence=0.7, min_evidence=3)
    definition = definition_from_plugin(auto_acquire_setup)
    address = definition.logic_address

    assert isinstance(service, SkillAcquirer)
    assert definition.functional_group is FunctionalGroup.G11_CREATION
    assert address is not None
    assert address.functional_group is FunctionalGroup.G11_CREATION
    assert address.control_slot is ControlSlot.OBSERVE_CHECKPOINT
    assert address.scope is Scope.RUN
    assert score_logic_address(address).total == 100


def test_auto_acquire_requires_success_confidence_and_evidence() -> None:
    """Skill acquisition only drafts candidates; weak episodes remain absent."""

    service = AutoAcquireSkillService(enabled=True, min_confidence=0.7, min_evidence=3)
    assert (
        service.propose(
            task_ref="run-1",
            procedure="Validate input before retrying.",
            success=True,
            confidence=0.7,
            evidence_refs=("event-1", "event-2"),
        )
        is None
    )

    candidate = service.propose(
        task_ref="run-1",
        procedure="Validate input before retrying.",
        success=True,
        confidence=0.8,
        evidence_refs=("event-1", "event-2", "event-3"),
    )
    assert candidate is not None
    assert candidate.status == "draft"
    assert candidate.candidate_id.startswith("skill-candidate-")


def test_failure_analyzer_only_accepts_declared_triggers() -> None:
    """Unconfigured failures cannot create an ungoverned learning signal."""

    service = FailureAnalyzerService(enabled=True, triggers=frozenset({"budget_exceeded"}))
    assert (
        service.analyze(run_ref="run-1", trigger="tool_error", evidence_refs=("event-1",)) is None
    )

    analysis = service.analyze(
        run_ref="run-1",
        trigger="budget_exceeded",
        evidence_refs=("event-1",),
    )
    assert analysis is not None
    assert analysis.trigger == "budget_exceeded"
    assert "Do not modify grants" in analysis.suggestions[1]


def test_profile_evolver_requires_held_out_sample_and_never_publishes() -> None:
    """A positive comparison can only be approved for external review."""

    service = ProfileEvolverService(
        enabled=True,
        min_sample_size=2,
        commit_threshold=0.05,
        rollback_on_regression=True,
    )
    draft = service.evaluate(
        candidate_ref="candidate-1",
        baseline=(_comparison(passed=False),),
        candidate=(_comparison(passed=True),),
    )
    assert draft.status == "draft"

    decision = service.evaluate(
        candidate_ref="candidate-1",
        baseline=(_comparison(passed=False), _comparison(passed=False)),
        candidate=(_comparison(passed=True), _comparison(passed=True)),
    )
    assert decision.status == "approved_for_review"
    assert "manual promotion" in decision.reason


def test_profile_tools_are_read_only_or_dry_run_only() -> None:
    """The scenario can inspect candidates but cannot mutate a production profile."""

    diff = asyncio.run(
        ProfileDiffTool().execute({"baseline": {"a": 1}, "candidate": {"a": 2, "b": 3}})
    )
    assert diff.success is True
    assert diff.payload == {
        "added": ["b"],
        "removed": [],
        "changed": ["a"],
        "apply_status": "not_applied",
    }

    apply = ProfileApplyTool()
    rejected = asyncio.run(
        apply.execute({"candidate": {"candidate_id": "candidate-1"}, "dry_run": False})
    )
    assert rejected.success is False
    preview = asyncio.run(apply.execute({"candidate": {"candidate_id": "candidate-1"}}))
    assert preview.success is True
    assert preview.payload["applied"] is False
    assert preview.payload["promotion_status"] == "requires_external_approval"


def test_learning_plugins_have_no_direct_promotion_or_skill_installation() -> None:
    """Static gate: learning plugins cannot bypass an external promotion workflow."""

    sources = "\n".join(
        (REPO / path).read_text(encoding="utf-8")
        for path in (
            "lca/plugins/skill/auto_acquire.py",
            "lca/plugins/insight/failure_analyzer.py",
            "lca/plugins/profile/evolver.py",
        )
    )
    assert "install_package(" not in sources
    assert "write_text(" not in sources
    assert "publish_profile(" not in sources
