"""Architecture contracts for the shared component discovery seam."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.contracts.atoms.enums import ComponentKind, DecisionGateName
from lca.contracts.capabilities import COMPONENT_REGISTRY, GATES, LEAD_BUDGET_POLICY_RESOLVER
from lca.contracts.protocols import DecisionGate, LeadBudgetPolicyResolver
from lca.contracts.protocols.spec import (
    MEMORY_CHOICE_SIMPLE,
    MEMORY_CHOICE_TEMPORAL,
    STATE_STORE_CHOICE_MEMORY,
)
from lca.harness.profile.boot import boot_profile
from lca.layer0_infra.component_registry import ComponentRegistry, RegistryKeyError
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.gate_service import GateService
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.memory.temporal_memory import TemporalMemorySystem
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy
from lca.plugins.providers.component_budget_policy import (
    ComponentRegistryLeadBudgetPolicyResolver,
)


def test_component_registry_rejects_duplicate_owner_without_replacing_first() -> None:
    """One category-local name has one provider owner at the discovery seam."""

    registry = ComponentRegistry()
    first = object()
    replacement = object()

    registry.register(ComponentKind.MEMORY, "default", first)

    with pytest.raises(KeyError, match="memory: entry 'default' already registered"):
        registry.register(ComponentKind.MEMORY, "default", replacement)

    assert registry.require(ComponentKind.MEMORY, "default") is first


def test_component_registry_keeps_names_local_to_their_category() -> None:
    """Equivalent names in distinct component categories remain independent."""

    registry = ComponentRegistry()
    memory = object()
    state_store = object()

    registry.register(ComponentKind.MEMORY, "default", memory)
    registry.register(ComponentKind.STATE_STORE, "default", state_store)

    assert registry.require(ComponentKind.MEMORY, "default") is memory
    assert registry.require(ComponentKind.STATE_STORE, "default") is state_store
    assert registry.list_categories() == ["memory", "state_store"]


def test_missing_component_lookup_does_not_create_an_empty_category() -> None:
    """Read paths preserve locality and do not mutate the discovery seam."""

    registry = ComponentRegistry()

    assert registry.get(ComponentKind.MEMORY, "simple") is None
    with pytest.raises(RegistryKeyError, match="未注册memory 'simple'"):
        registry.require(ComponentKind.MEMORY, "simple")

    assert registry.list_categories() == []


def test_component_budget_policy_resolver_owns_discovery_and_validation() -> None:
    """The Lead adapter isolates component lookup from plan-bound assembly."""

    registry = ComponentRegistry()
    registry.register(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy)
    resolver = ComponentRegistryLeadBudgetPolicyResolver(registry)

    assert isinstance(resolver, LeadBudgetPolicyResolver)
    assert isinstance(resolver.resolve_policy(), LeadBudgetPolicy)


def test_component_budget_policy_resolver_rejects_non_policy_factory_output() -> None:
    """A malformed provider fails at the resolver seam rather than in Agent assembly."""

    registry = ComponentRegistry()
    registry.register(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY, object)

    with pytest.raises(TypeError, match="lead budget policy must be BudgetPolicy"):
        ComponentRegistryLeadBudgetPolicyResolver(registry).resolve_policy()


def test_plan_bound_agent_assembly_consumes_only_lead_policy_resolver() -> None:
    """Lead assembly must not leak registry taxonomy or policy naming details."""

    source = (
        Path(__file__).resolve().parents[2] / "lca" / "plugins" / "composer" / "agent_assembly.py"
    ).read_text(encoding="utf-8")

    assert "LEAD_BUDGET_POLICY_RESOLVER.key" in source
    assert "ComponentKind.BUDGET_POLICY" not in source
    assert "COMPONENT_REGISTRY" not in source
    assert '_LEAD_BUDGET_POLICY_KEY = "lead"' not in source


def test_lead_decision_gate_selection_consumes_only_gate_service() -> None:
    """Lead composition keeps DecisionGate discovery local to the gate seam."""

    source = (
        Path(__file__).resolve().parents[2]
        / "lca"
        / "plugins"
        / "composer"
        / "internal"
        / "team.py"
    ).read_text(encoding="utf-8")

    assert "GATES.key" in source
    assert "COMPONENT_REGISTRY" not in source
    assert "ComponentKind" not in source


def test_default_profile_closes_retained_component_contributors_through_one_seam() -> None:
    """Default implementations are independently contributed, then discovered centrally."""

    context = asyncio.run(boot_profile("profiles/web-standard.yaml"))
    registry = context.inject(COMPONENT_REGISTRY.key)

    assert isinstance(registry, ComponentRegistry)
    assert registry.require(ComponentKind.MEMORY, MEMORY_CHOICE_SIMPLE) is SimpleMemorySystem
    assert registry.require(ComponentKind.MEMORY, MEMORY_CHOICE_TEMPORAL) is TemporalMemorySystem
    assert (
        registry.require(ComponentKind.STATE_STORE, STATE_STORE_CHOICE_MEMORY) is InMemoryStateStore
    )
    gates = context.inject(GATES.key)
    assert isinstance(gates, GateService)
    assert isinstance(
        gates.create(DecisionGateName.MUST_CONSULT_ALL.value),
        DecisionGate,
    )
    assert registry.require(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY) is LeadBudgetPolicy
    resolver = context.inject(LEAD_BUDGET_POLICY_RESOLVER.key)
    assert isinstance(resolver, LeadBudgetPolicyResolver)
    assert isinstance(resolver.resolve_policy(), LeadBudgetPolicy)
