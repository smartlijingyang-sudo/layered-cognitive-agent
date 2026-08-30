"""GateChainComposer Provider plugin — Tier-2 (ADR-0074).

Migrates the hard-coded ``build_workspace_agent_gate()`` logic from
``lca/layer1_cognitive/brain/decision_gates/__init__.py`` into a pluggable
default provider. Profile can replace via ``ctx.provide("gate_chain_composer", ...)``
to customize gate ordering/composition.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.cognition import DecisionGate
from lca.contracts.protocols.gate_chain_composer import GateChainComposer
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configuration for the default GateChainComposer provider."""

    model_config = {"extra": "forbid"}


class DefaultGateChainComposer(GateChainComposer):
    """Default GateChainComposer implementation (ADR-0074).

    Migrated from ``lca/layer1_cognitive/brain/decision_gates/__init__.py:build_workspace_agent_gate()``.
    Composes the standard 5-gate decision chain:

    1. ``RepeatToolCallGate``: warns on consecutive identical tool calls
    2. ``ToolLoopBreakerGate``: blocks after consecutive failures of the same pattern
    3. ``ProgressLoopDetector``: detects cross-tool loops with zero progress
    4. ``TerminalRespondGate``: forces respond on last step for non-producing actions
    5. ``ArtifactRespondInjector``: appends authoritative file list to respond text

    Profile can replace via ``ctx.provide("gate_chain_composer", ...)`` to customize
    gate ordering/composition.
    """

    def compose(self) -> DecisionGate:
        """Compose the standard 5-gate decision chain.

        Returns:
            Composed DecisionGate chain via ChainedDecisionGate.
        """
        from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
            ArtifactRespondInjector,
        )
        from lca.layer1_cognitive.brain.decision_gates.chained import ChainedDecisionGate
        from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import (
            ProgressLoopDetector,
        )
        from lca.layer1_cognitive.brain.decision_gates.repeat_tool_call import RepeatToolCallGate
        from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate
        from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate

        return ChainedDecisionGate(
            RepeatToolCallGate(),
            ToolLoopBreakerGate(),
            ProgressLoopDetector(),
            TerminalRespondGate(),
            ArtifactRespondInjector(),
        )


@plugin(
    id="lca-gate-chain-composer-provider",
    provides=["gate_chain_composer"],
    implements=[GateChainComposer],
    layer="L1",
    effects="none",
    description="Provide the default GateChainComposer implementation (ADR-0074).",
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default GateChainComposer provider."""
    ctx.provide("gate_chain_composer", DefaultGateChainComposer())


__all__ = ["Config", "DefaultGateChainComposer", "setup"]
