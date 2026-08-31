"""ComponentRegistry contributor: LeadBudgetPolicy (ADR-0074).

Injects the shared ComponentRegistry and registers the lead budget policy
under ComponentKind.BUDGET_POLICY.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.application.policies import LEAD_BUDGET_POLICY_KEY
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ComponentKind
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import COMPONENT_REGISTRY, LEAD_BUDGET_POLICY_RESOLVER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.protocols import BudgetPolicy, LeadBudgetPolicyResolver
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class ComponentRegistryLeadBudgetPolicyResolver(LeadBudgetPolicyResolver):
    """Resolve the profile-selected Lead policy through the component discovery seam.

    The adapter owns the ComponentRegistry category/name lookup, factory call,
    and protocol validation. Plan-bound Agent assembly therefore consumes one
    narrow policy-resolution interface rather than this discovery detail.
    """

    def __init__(self, registry: ComponentRegistryProtocol) -> None:
        self._registry = registry

    def resolve_policy(self) -> BudgetPolicy:
        policy_factory = self._registry.require(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY)
        policy = policy_factory()
        if not isinstance(policy, BudgetPolicy):
            raise TypeError(f"lead budget policy must be BudgetPolicy, got {type(policy).__name__}")
        return policy


@plugin(
    id="lca-component-budget-policy-contributor",
    provides=[LEAD_BUDGET_POLICY_RESOLVER.key],
    requires=[COMPONENT_REGISTRY.key],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register and expose the profile-selected LeadBudgetPolicy resolver.",
    test_suite="tests/architecture/test_component_registry_seam.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-component-budget-policy-contributor.checked",
                "lca-component-budget-policy-contributor.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    from lca.application.policies import LeadBudgetPolicy

    registry: ComponentRegistryProtocol = ctx.require(COMPONENT_REGISTRY.key)
    registry.register(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy)
    ctx.provide(
        LEAD_BUDGET_POLICY_RESOLVER.key,
        ComponentRegistryLeadBudgetPolicyResolver(registry),
    )


__all__ = ["ComponentRegistryLeadBudgetPolicyResolver", "Config", "setup"]
