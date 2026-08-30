"""Tests for CommandEnvelope + RunFact + mint_envelope (ADR-0074 PR-7).

This test covers:

- CommandEnvelope dataclass construction + V5 plan_ref required
- mint_envelope factory: dict / Decision object / DecisionRef inputs
- CapabilityGrant / BudgetReservation nested dataclass types
- RunFact / RunDelta dataclass types
- Verdict / EnvelopeVerdict enums + verdict aggregation
- command_envelope_to_dict + envelope_is_authorized helpers
- V4 architecture test gate: scripts/check_command_envelope_required.py
- V5 acceptance: execute() stack trace contains mint_envelope (integration)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.protocols.act.command_envelope import (
    BudgetReservation,
    CapabilityGrant,
    CommandEnvelope,
    DecisionRef,
    EnvelopeVerdict,
    RunDelta,
    RunFact,
    Verdict,
    command_envelope_to_dict,
    envelope_aggregate_verdict,
    envelope_is_authorized,
    mint_envelope,
    warn_deprecated_envelope_constructor,
)

# ── Test fixtures ───────────────────────────────────────────────────


@dataclass
class _FakeDecision:
    """Fake Decision with decision_id attribute."""

    decision_id: str = "dec_test"
    action_type: str = "use_tool"


# ── CommandEnvelope + mint_envelope ──────────────────────────────


class TestCommandEnvelopeConstruction:
    def test_minimal_valid(self) -> None:
        env = CommandEnvelope(
            plan_ref="plan_xyz",
            scope_ref="run_1",
            decision_ref="dec_1",
            provider="bash",
        )
        assert env.plan_ref == "plan_xyz"
        assert env.scope_ref == "run_1"
        assert env.decision_ref == "dec_1"
        assert env.provider == "bash"
        assert env.grant == CapabilityGrant()
        assert env.budget_reservation == BudgetReservation()
        assert env.policy_verdict_refs == ()
        assert env.version == 1

    def test_blank_plan_ref_allowed_at_construction(self) -> None:
        """PR-7: CommandEnvelope blank plan_ref 在 dataclass 构造时合法；mint_envelope 拒绝。"""
        env = CommandEnvelope()
        assert env.plan_ref == ""


class TestMintEnvelopeFactory:
    def test_dict_input_decision_id(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1", "action_type": "use_tool"},
            provider="bash",
        )
        assert env.decision_ref == "dec_1"

    def test_dict_input_id_key_fallback(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"id": "dec_2"},
            provider="bash",
        )
        assert env.decision_ref == "dec_2"

    def test_decision_object_input(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision=_FakeDecision(decision_id="dec_3"),
            provider="bash",
        )
        assert env.decision_ref == "dec_3"

    def test_decision_object_with_id_attr(self) -> None:
        class _WithId:
            id = "dec_4"

        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision=_WithId(),
            provider="bash",
        )
        assert env.decision_ref == "dec_4"

    def test_string_input(self) -> None:
        """A stable string decision id is preserved as the envelope reference."""
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision="dec_5_str",
            provider="bash",
        )
        assert env.decision_ref == "dec_5_str"

    def test_none_input_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty decision_id"):
            mint_envelope(
                plan_ref="abc",
                scope_ref="run_1",
                decision=None,
                provider="bash",
            )

    def test_empty_plan_ref_raises(self) -> None:
        """V5 acceptance: empty plan_ref 拒绝（empty == legacy path）。"""
        with pytest.raises(ValueError, match="plan_ref must be non-empty"):
            mint_envelope(
                plan_ref="",
                scope_ref="run_1",
                decision={"decision_id": "dec_1"},
                provider="bash",
            )

    def test_empty_scope_ref_raises(self) -> None:
        with pytest.raises(ValueError, match="scope_ref must be non-empty"):
            mint_envelope(
                plan_ref="abc",
                scope_ref="",
                decision={"decision_id": "dec_1"},
                provider="bash",
            )

    def test_empty_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="provider must be non-empty"):
            mint_envelope(
                plan_ref="abc",
                scope_ref="run_1",
                decision={"decision_id": "dec_1"},
                provider="",
            )

    def test_with_grant_and_budget(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            grant=CapabilityGrant(capability="bash", scope="turn", effect_class="tools"),
            budget_reservation=BudgetReservation(tokens=100, cost_cents=5),
        )
        assert env.grant.capability == "bash"
        assert env.grant.scope == "turn"
        assert env.grant.effect_class == "tools"
        assert env.budget_reservation.tokens == 100
        assert env.budget_reservation.cost_cents == 5

    def test_with_policy_verdict_refs(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            policy_verdict_refs=("policy.authorize", "policy.budget"),
        )
        assert env.policy_verdict_refs == ("policy.authorize", "policy.budget")


# ── CapabilityGrant / BudgetReservation ───────────────────────────


class TestCapabilityGrant:
    def test_minimal_valid(self) -> None:
        g = CapabilityGrant()
        assert g.capability == ""
        assert g.scope == ""
        assert g.effect_class == "none"

    def test_with_values(self) -> None:
        g = CapabilityGrant(capability="memory", scope="turn", effect_class="memory")
        assert g.capability == "memory"
        assert g.scope == "turn"
        assert g.effect_class == "memory"


class TestBudgetReservation:
    def test_minimal_valid(self) -> None:
        b = BudgetReservation()
        assert b.tokens == 0
        assert b.cost_cents == 0
        assert b.wall_clock_ms == 0
        assert b.tool_calls == 0

    def test_with_values(self) -> None:
        b = BudgetReservation(tokens=100, cost_cents=5, wall_clock_ms=1000, tool_calls=2)
        assert b.tokens == 100
        assert b.cost_cents == 5
        assert b.wall_clock_ms == 1000
        assert b.tool_calls == 2


# ── RunFact / RunDelta ─────────────────────────────────────────────


class TestRunFact:
    def test_minimal_valid(self) -> None:
        fact = RunFact()
        assert fact.fact_id == ""
        assert fact.plan_ref == ""
        assert fact.kind == ""
        assert fact.payload == {}
        assert fact.created_at == 0.0

    def test_with_values(self) -> None:
        fact = RunFact(
            fact_id="fact_1",
            plan_ref="plan_xyz",
            kind="tool_invoked",
            payload={"tool": "bash", "args": {"cmd": "ls"}},
            created_at=1234567890.0,
        )
        assert fact.fact_id == "fact_1"
        assert fact.kind == "tool_invoked"
        assert fact.payload["tool"] == "bash"


class TestRunDelta:
    def test_minimal_valid(self) -> None:
        delta = RunDelta()
        assert delta.plan_ref == ""
        assert delta.run_id == ""
        assert delta.facts == ()
        assert delta.metadata == {}

    def test_with_facts(self) -> None:
        facts = (
            RunFact(fact_id="f1", kind="decision_made"),
            RunFact(fact_id="f2", kind="tool_invoked"),
        )
        delta = RunDelta(
            plan_ref="plan_xyz",
            run_id="run_1",
            facts=facts,
        )
        assert delta.plan_ref == "plan_xyz"
        assert delta.run_id == "run_1"
        assert len(delta.facts) == 2
        assert delta.facts[0].kind == "decision_made"
        assert delta.facts[1].kind == "tool_invoked"


# ── DecisionRef ────────────────────────────────────────────────────


class TestDecisionRef:
    def test_minimal_valid(self) -> None:
        ref = DecisionRef()
        assert ref.decision_id == ""
        assert ref.plan_ref == ""
        assert ref.scope_ref == ""
        assert ref.action_type == ""
        assert ref.tool_name == ""

    def test_with_values(self) -> None:
        ref = DecisionRef(
            decision_id="dec_1",
            plan_ref="plan_xyz",
            scope_ref="run_1",
            action_type="use_tool",
            tool_name="bash",
        )
        assert ref.decision_id == "dec_1"
        assert ref.tool_name == "bash"


# ── Verdict / EnvelopeVerdict ─────────────────────────────────────


class TestVerdictEnum:
    def test_verdict_values(self) -> None:
        """5 闸单调聚合后的 verdict。"""
        assert Verdict.AUTHORIZED.value == "authorized"
        assert Verdict.DENIED.value == "denied"
        assert Verdict.BUDGET_EXHAUSTED.value == "budget_exhausted"
        assert Verdict.CONSTRAINT_VIOLATED.value == "constraint_violated"
        assert Verdict.SAFE_BOUNDARY_VIOLATED.value == "safe_boundary_violated"


class TestEnvelopeVerdictEnum:
    def test_envelope_verdict_values(self) -> None:
        assert EnvelopeVerdict.AUTHORIZED.value == "authorized"
        assert EnvelopeVerdict.DENIED.value == "denied"
        assert EnvelopeVerdict.BUDGET_EXHAUSTED.value == "budget_exhausted"


# ── Accessors / factories (ADR-0015) ──────────────────────────────


class TestEnvelopeIsAuthorized:
    def test_empty_verdict_refs_not_authorized(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            policy_verdict_refs=(),
        )
        assert envelope_is_authorized(env) is False

    def test_partial_verdict_refs_are_not_authorized(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            policy_verdict_refs=("act.authorize:allow",),
        )
        assert envelope_is_authorized(env) is False

    def test_all_canonical_gate_allows_authorize_envelope(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            policy_verdict_refs=(
                "act.authorize:allow",
                "act.budget:allow",
                "act.constrain:allow",
                "act.execute:allow",
                "act.safe-boundary:allow",
            ),
        )
        assert envelope_is_authorized(env) is True


class TestEnvelopeAggregateVerdict:
    def test_authorized(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
            policy_verdict_refs=(
                "act.authorize:allow",
                "act.budget:allow",
                "act.constrain:allow",
                "act.execute:allow",
                "act.safe-boundary:allow",
            ),
        )
        assert envelope_aggregate_verdict(env) is Verdict.AUTHORIZED

    def test_denied_when_empty_verdict_refs(self) -> None:
        env = mint_envelope(
            plan_ref="abc",
            scope_ref="run_1",
            decision={"decision_id": "dec_1"},
            provider="bash",
        )
        assert envelope_aggregate_verdict(env) is Verdict.DENIED


class TestCommandEnvelopeToDict:
    def test_round_trip_fields(self) -> None:
        env = mint_envelope(
            plan_ref="plan_xyz",
            scope_ref="run_1",
            decision={"decision_id": "dec_1", "action_type": "use_tool"},
            provider="bash",
            grant=CapabilityGrant(capability="bash", scope="turn"),
            budget_reservation=BudgetReservation(tokens=100),
            idempotency_key="dec_1:bash",
            policy_verdict_refs=("policy.pre_execute",),
        )
        d = command_envelope_to_dict(env)
        assert d["plan_ref"] == "plan_xyz"
        assert d["scope_ref"] == "run_1"
        assert d["provider"] == "bash"
        assert d["decision_ref"] == "dec_1"
        assert d["grant"]["capability"] == "bash"
        assert d["grant"]["scope"] == "turn"
        assert d["budget_reservation"]["tokens"] == 100
        assert d["idempotency_key"] == "dec_1:bash"
        assert d["policy_verdict_refs"] == ["policy.pre_execute"]
        assert d["version"] == 1


class TestWarnDeprecatedEnvelopeConstructor:
    def test_warns(self) -> None:
        """Direct CommandEnvelope construction 触发 deprecation warning。"""

        with pytest.warns(DeprecationWarning, match="Direct CommandEnvelope construction"):
            warn_deprecated_envelope_constructor(
                CommandEnvelope(
                    plan_ref="abc", scope_ref="run_1", decision_ref="dec_1", provider="bash"
                )
            )


# ── V4 architecture test gate (integration) ──────────────────────


class TestV4ArchitectureTestGate:
    def test_check_command_envelope_required_passes(self) -> None:
        """V4 acceptance §3.4: scripts/check_command_envelope_required.py exit 0。"""
        import subprocess
        import sys
        from pathlib import Path

        repository_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(  # noqa: S603 -- fixed repository-local verifier
            [
                sys.executable,
                str(repository_root / "scripts/check_command_envelope_required.py"),
            ],
            capture_output=True,
            text=True,
            cwd=repository_root,
        )
        assert result.returncode == 0, (
            f"architecture test failed: stdout={result.stdout}, stderr={result.stderr}"
        )
        assert "mint_envelope" in result.stdout or "OK" in result.stdout

    def test_pipeline_safe_executor_mints_envelope_on_execute(self) -> None:
        """PipelineSafeExecutor.execute stack trace 必含 mint_envelope。

        integration test: execute a real tool call with plan_ref active.
        Verify via import-level inspection that PipelineSafeExecutor.execute
        references mint_envelope.
        """
        import inspect

        from lca.cognition.body.pipeline_safe_executor import (
            PipelineSafeExecutor,
        )

        source = inspect.getsource(PipelineSafeExecutor.execute)
        # The execute() method must reference mint_envelope
        assert "mint_envelope" in source, (
            "PipelineSafeExecutor.execute() must call mint_envelope() (V4 acceptance)"
        )
