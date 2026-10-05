"""Tests verifying the flattened architecture of cognition decision gates (INV-ARCH-08, INV-ARCH-09)."""

from __future__ import annotations

from pathlib import Path


def test_inv_arch_08_default_workspace_gate_chain_order_and_types() -> None:
    """INV-ARCH-08: Default workspace gate chain retains identical 6-gate sequence and types."""
    from lca.cognition.brain.decision_gates import (
        ArtifactRespondInjector,
        ChainedDecisionGate,
        DeliverySatisfiedGate,
        ProgressLoopDetector,
        RepeatToolCallGate,
        TerminalRespondGate,
        ToolLoopBreakerGate,
        build_default_workspace_gate_chain,
    )

    chain = build_default_workspace_gate_chain()
    assert isinstance(chain, ChainedDecisionGate)
    gates = chain._gates
    assert len(gates) == 6

    expected_types = [
        RepeatToolCallGate,
        ToolLoopBreakerGate,
        ProgressLoopDetector,
        DeliverySatisfiedGate,
        TerminalRespondGate,
        ArtifactRespondInjector,
    ]
    for gate, expected_cls in zip(gates, expected_types, strict=True):
        assert type(gate) is expected_cls


def test_inv_arch_08_flat_module_imports() -> None:
    """INV-ARCH-08: All gates and utilities are importable from flat modules directly under decision_gates."""
    from lca.cognition.brain.decision_gates.artifact import ArtifactRespondInjector
    from lca.cognition.brain.decision_gates.auth import AuthUrlProvenanceGate, is_auth_intent_url
    from lca.cognition.brain.decision_gates.chained import ChainedDecisionGate, record_gate_decided
    from lca.cognition.brain.decision_gates.consult import MustConsultAllMembers
    from lca.cognition.brain.decision_gates.delivery import DeliverySatisfiedGate
    from lca.cognition.brain.decision_gates.loop_guards import (
        ProgressLoopDetector,
        ToolLoopBreakerGate,
    )
    from lca.cognition.brain.decision_gates.multi_tool_loop import (
        MultiToolLoopBreakerGate,
        tool_call_fingerprint,
    )
    from lca.cognition.brain.decision_gates.office import OfficeWorksSealer
    from lca.cognition.brain.decision_gates.repeat import RepeatToolCallGate
    from lca.cognition.brain.decision_gates.terminal import TerminalRespondGate

    assert callable(record_gate_decided)
    assert callable(tool_call_fingerprint)
    assert callable(is_auth_intent_url)
    assert issubclass(ChainedDecisionGate, object)
    assert issubclass(RepeatToolCallGate, object)
    assert issubclass(ToolLoopBreakerGate, object)
    assert issubclass(ProgressLoopDetector, object)
    assert issubclass(MultiToolLoopBreakerGate, object)
    assert issubclass(DeliverySatisfiedGate, object)
    assert issubclass(TerminalRespondGate, object)
    assert issubclass(ArtifactRespondInjector, object)
    assert issubclass(AuthUrlProvenanceGate, object)
    assert issubclass(MustConsultAllMembers, object)
    assert issubclass(OfficeWorksSealer, object)


def test_inv_arch_09_no_micro_directories_remain() -> None:
    """INV-ARCH-09: lca/cognition/brain/decision_gates/ contains zero subdirectories (except __pycache__)."""
    gates_dir = Path("lca/cognition/brain/decision_gates")
    assert gates_dir.is_dir()

    subdirs = [p.name for p in gates_dir.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert subdirs == [], f"Found residual micro-directories in decision_gates: {subdirs}"
