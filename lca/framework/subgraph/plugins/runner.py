"""SubgraphRunner — think subgraph's single execution entrypoint.

Per plan §13.8: the runner is the framework-side adapter that turns a
:class:`SubgraphReference` into one :class:`InterpretationResult`. It
owns three responsibilities and nothing else:

1. Resolve ``ref.plan_ref`` → ``CompiledRunPlan`` (via the injected
   ``subgraph_resolver``).
2. Lift the plan to a :class:`BundleGraphSpec` via the plan_lift module.
3. Drive the v2 scheduler with the injected ``subgraph_runtime`` and
   ``factory_registry``; publish the resulting :class:`PhaseOutput` to
   the supplied :class:`PhaseOutputChannel`.

The runner is registered as a Cordis ``@plugin(kind=DRIVER)`` so the
container owns its lifecycle and injects its capabilities via
``ctx.inject(...)`` during ``setup``. The interpreter is a pure
consumer of ``subgraph_runner`` — it does not import
:mod:`NodeGraphDriver` or :mod:`plan_lift` directly.
"""

from __future__ import annotations

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (
    FactoryRegistry,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.subgraph.plugins.channel import (
    PhaseOutput,
    PhaseOutputChannel,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.framework.subgraph.plugins.plan_lift import lift_subgraph_reference_to_v2
from lca.framework.subgraph.plugins.runtime import SubgraphRuntime
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class SubgraphRunner:
    """Subgraph execution entrypoint: load → lift → drive → publish.

    Composition is wired in :func:`setup` from the three Cordis
    capabilities (``subgraph_resolver`` / ``factory_registry`` /
    ``subgraph_runtime``) — no ``__init__`` injection (per plan R6).
    """

    def __init__(
        self,
        *,
        resolver: object,
        registry: FactoryRegistry,
        runtime: SubgraphRuntime,
    ) -> None:
        self._resolver = resolver
        self._registry = registry
        self._runtime = runtime

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: PhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        """Execute ``ref``'s subgraph and return ``(state, output)``.

        The driver publishes the terminal ``PhaseOutput`` on ``channel``
        before this method returns; we additionally return it so the
        caller can ``absorb`` or forward without a second channel read.
        """
        sub_plan_obj = self._resolver.resolve(ref.plan_ref)
        spec = lift_subgraph_reference_to_v2(ref, sub_plan_obj)
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=ref.plan_ref,
            scope=self._runtime,
            registry=self._registry,
        )
        sub_result = await driver.run(
            outer_state=outer_state,
            channel=channel,
            artifacts={},
        )
        return sub_result.state, sub_result.output


@plugin(
    id="subgraph.runner",
    Config=None,
    provides=("subgraph_runner",),
    requires=("subgraph_resolver", "factory_registry", "subgraph_runtime"),
    layer="L1",
    kind=PluginKind.DRIVER,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(
            grants=("plugin.serve", "subgraph.run"),
        ),
        observability=EvidenceContract(
            descriptors=("subgraph_runner.served", "subgraph_runner.executed"),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "subgraph_resolver", "factory_registry", "subgraph_runtime"),
        emits=("subgraph.executed",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Wire SubgraphRunner from Cordis-injected capabilities and provide it.

    The three declared ``requires=`` keys are checked at boot by Cordis
    (per ADR-0110); a profile that fails to provide any of them raises
    :class:`cordis.fiber.ValidationError` before this ``setup`` runs.
    """
    resolver = ctx.inject("subgraph_resolver")
    registry = ctx.inject("factory_registry")
    runtime = ctx.inject("subgraph_runtime")
    runner = SubgraphRunner(resolver=resolver, registry=registry, runtime=runtime)
    ctx.provide("subgraph_runner", runner)


__all__ = ["SubgraphRunner", "setup"]
