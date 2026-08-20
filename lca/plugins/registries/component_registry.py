"""Component discovery registry — former defaults.py component table (ADR-0062 §7)."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums import ComponentKind, DecisionGateName
from lca.contracts.capabilities import COMPONENT_REGISTRY
from lca.contracts.protocols.spec import MEMORY_CHOICE_SIMPLE, STATE_STORE_CHOICE_MEMORY
from lca.harness.plugin_api import PluginKind, plugin
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY

EVENT_BUS_SIMPLE = "simple"


@plugin(
    id="lca.registries.component_registry",
    provides=[COMPONENT_REGISTRY.key],
    requires=[],
    layer="L4",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="ComponentRegistry with built-in state_store/memory/event_bus/gates/budget.",
    test_suite="tests/test_refactor_guards.py",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    from lca.layer0_infra.component_registry import ComponentRegistry
    from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
    from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
    from lca.layer1_cognitive.event_bus import SimpleEventBus
    from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
    from lca.layer4_app.policies import LeadBudgetPolicy

    reg = ComponentRegistry()
    reg.register(ComponentKind.STATE_STORE, STATE_STORE_CHOICE_MEMORY, InMemoryStateStore)
    reg.register(ComponentKind.MEMORY, MEMORY_CHOICE_SIMPLE, SimpleMemorySystem)
    reg.register(ComponentKind.EVENT_BUS, EVENT_BUS_SIMPLE, SimpleEventBus)
    reg.register(
        ComponentKind.DECISION_GATE, DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
    )
    reg.register(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy)
    ctx.provide(COMPONENT_REGISTRY.key, reg)
