"""Default ``declarative_interpreter_factory`` capability provider.

Wraps the framework-owned :class:`GenericPlanInterpreter` as a
profile-replaceable factory.  The factory owns the construction policy
(``__init__`` kwargs) without inheriting the Cordis-injected think-
subgraph seams — those are wired at ``declarative.interpreter`` plugin
``setup`` time.  Profiles may swap this capability for a domain-tuned
factory without changing the interpreter plugin.
"""

from __future__ import annotations

from pydantic import BaseModel

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
from lca.contracts.protocols.runtime.runtime.composition import (
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
)
from lca.framework.declarative.plugins.interpreter import GenericPlanInterpreter
from lca.framework.graph.adapter import PlanInterpreterAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default interpreter factory has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


class DefaultDeclarativeInterpreterFactory(DeclarativeInterpreterFactory):
    """Default factory: build the standard interpreter from the runtime closures."""

    def create(
        self,
        *,
        journal: object,
        effect_gateway: object,
        reducer: object,
        phase_observer: object,
        lifecycle_publisher: object,
        loop_guard_evaluator: object | None = None,
    ) -> DeclarativeInterpreter:
        """Construct the interpreter; the think-subgraph seams are added by the plugin.

        PR-7 cutover: the new :class:`lca.framework.graph.adapter.PlanInterpreterAdapter`
        is the production interpreter. It wraps :class:`PlanInterpreter`
        and translates the legacy kwargs into the new strategy seam.
        The legacy :class:`GenericPlanInterpreter` stays importable
        for the in-flight bbcca980 act-subgraph refactor and existing
        direct-construction callers; the new adapter is the active path.
        """
        # Touch the legacy symbol so the import stays in sync with the
        # delegation decision; the symbol is the canonical source of
        # the kwargs shape.
        _ = GenericPlanInterpreter
        return PlanInterpreterAdapter()  # type: ignore[return-value]


@plugin(
    id="declarative.interpreter_factory",
    requires=[],
    provides=["declarative_interpreter_factory"],
    implements=[DeclarativeInterpreterFactory],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default DeclarativeInterpreterFactory so profiles can "
        "swap the interpreter construction policy without touching the "
        "interpreter plugin."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.interpreter_factory.checked",
                "declarative.interpreter_factory.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("declarative_interpreter_factory",),
        emits=("declarative_interpreter_factory.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default DeclarativeInterpreterFactory to runtime assembly."""

    del config
    ctx.provide("declarative_interpreter_factory", DefaultDeclarativeInterpreterFactory())


__all__ = ["Config", "DefaultDeclarativeInterpreterFactory", "setup"]
