"""Bundle-relative subgraph resolver provider (L1).

Satisfies ``framework.subgraph.plugins.runner``'s hard
``requires=subgraph_resolver`` declared at the L1 layer. Without
this plugin in the bundle set, the framework runner fails the Cordis
capability check at boot. ADR-0219 §10.11 close-out: the resolver
is the same one ``lca.harness.declarative.compile.subgraph_resolver``
provides, so the v2 BundleGraphSpec path and the legacy fixtures
share a single resolution surface.
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
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@plugin(
    id="lca-subgraph-resolver",
    Config=None,
    requires=(),
    provides=("subgraph_resolver",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Provide the bundle-relative subgraph resolver. Required by the "
        "framework ``subgraph.runner`` plugin (L1) at boot. ADR-0219 "
        "§10.11: keeps the v2 BundleGraphSpec path on the same resolver "
        "as the legacy fixtures."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca_subgraph_resolver.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config) -> None:  # type: ignore[no-untyped-def]
    del config
    from lca.harness.declarative.compile.subgraph_resolver import (
        default_subgraph_resolver,
    )

    ctx.provide("subgraph_resolver", default_subgraph_resolver())


__all__ = ["setup"]
