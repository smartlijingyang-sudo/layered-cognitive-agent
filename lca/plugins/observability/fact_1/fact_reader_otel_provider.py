"""OTel fact-reader factory (stub).

The legacy ``OtelProjector`` (which translated :class:`RunStore` events
into OpenTelemetry spans) was removed in the ADR-0192 cleanup. OTel
span emission is now owned by :mod:`lca.infrastructure.observability.spine`
observers — Session.runtime reads the spine event stream and emits
OTel spans directly, no projection needed.

This factory is kept as a bundle entry stub so ``bundles/base.yaml``
can resolve the ``lca-fact-reader-otel-factory`` plugin id without
breaking profile resolution. The plugin registers nothing; the
``assemble_observability`` boot path resolves the registry slot to
``None`` and the rest of the system works as before.
"""

from __future__ import annotations

from typing import Any

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
from lca.contracts.protocols import JournalProjector
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-fact-reader-otel-factory",
    requires=["fact_readers"],
    implements=[JournalProjector],
    layer="L0",
    effects="none",
    description="No-op OTel fact reader (legacy OtelProjector removed; Session observers own OTel).",
    test_suite="tests/test_fact_reader_plugin.py::test_provider_registers_otel_reader",
    kind=PluginKind.PROVIDER,
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
                "lca-fact-reader-otel-factory.checked",
                "lca-fact-reader-otel-factory.served",
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
    """No-op: Session runtime observers own OTel emission post-ADR-0192.

    Kept for bundle compatibility (``bundles/base.yaml`` references this
    plugin id). The :class:`NamedRegistry` slot for ``fact_readers`` is
    registered but its ``otel`` factory is the no-op :func:`_make_otel_reader`.
    """
    del ctx, config, JournalProjector
    return None  # noqa: PLR1711 — explicit no-op for static analysers


def _make_otel_reader(
    settings: Any = None,
    *,
    tracer: Any = None,
    **unused: Any,
) -> JournalProjector | None:
    """Stub reader (returns ``None``); Session observers own OTel."""
    del settings, tracer, unused
    return None
