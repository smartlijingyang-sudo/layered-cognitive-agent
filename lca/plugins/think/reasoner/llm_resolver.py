"""LlmResolver provider — boot-time ``llm_resolver`` capability owner.

Wraps the bound :class:`LLMAdapter` already published by
``phase.think.reasoner.credentials`` as a duck-typed
:class:`LlmResolver`. The runnable-assembly seam
(``RunnableBuildRequest.llm = request.llm_resolver.resolve()``) needs a
``resolve() -> LLMAdapter`` object, not the adapter; this plugin keeps
the adapter binding on a single owner and exposes the resolver shape to
the carrier.

Re-requires ``llm_adapter`` rather than re-reading ``LLM_*`` env vars, so
boot credentials are loaded exactly once (the typed-port LLM-aware
nodes read from the same source).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _BoundAdapterResolver:
    """Adapter from a bound :class:`LLMAdapter` to :class:`LlmResolver`.

    Kept as a tiny private wrapper rather than reaching for
    :class:`ProductionLLMResolver` so this plugin owns zero
    boot-time knowledge of credentials: the adapter arrives already
    bound by ``phase.think.reasoner.credentials``.
    """

    __slots__ = ("_adapter",)

    def __init__(self, adapter: object) -> None:
        self._adapter = adapter

    def resolve(self) -> object:
        return self._adapter


@plugin(
    id="lca-llm-resolver",
    provides=("llm_resolver",),
    requires=("llm_adapter",),
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Expose the LlmResolver view of the boot-bound LLMAdapter; "
        "consumers are the runnable-assembly seam."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca_llm_resolver.checked", "lca_llm_resolver.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("llm_adapter",),
        emits=("llm_resolver.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Resolve ``llm_adapter`` and provide it as a LlmResolver.

    Boot-order note: ``phase.think.reasoner.credentials`` (the only
    credential-reading plugin) must run before this one. The bundle
    composition root guarantees that ordering via the ``llm_adapter``
    requires edge.
    """
    del config
    adapter = ctx.require("llm_adapter")
    ctx.provide("llm_resolver", _BoundAdapterResolver(adapter))


__all__ = ["Config", "setup"]
