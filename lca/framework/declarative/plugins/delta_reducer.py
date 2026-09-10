"""Default ``delta_reducer`` capability provider.

Registers a null delta reducer as a fail-closed seam: any phase that
attempts to apply a RunDelta before a registry-backed provider is
contributed will surface a clear NotImplementedError.  Production
profiles must override this capability with their single-writer reducer.
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
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.act.command.envelope import RunDelta
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    DeltaReducer,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default null delta reducer has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


class NullDeltaReducer(DeltaReducer):
    """Reject every delta; explicit fail-closed null default."""

    def apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState:
        del delta
        raise NotImplementedError(
            "NullDeltaReducer rejected delta; install a registry-backed "
            "DeltaReducer provider before phases may fold declared deltas."
        )
        return state


@plugin(
    id="declarative.delta_reducer",
    requires=[],
    provides=["delta_reducer"],
    implements=[DeltaReducer],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default null DeltaReducer so declarative profiles have a "
        "fail-closed single-writer seam until a registry-backed provider "
        "replaces it."
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
                "declarative.delta_reducer.checked",
                "declarative.delta_reducer.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("delta_reducer",),
        emits=("delta_reducer.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default null DeltaReducer to runtime assembly."""

    del config
    ctx.provide("delta_reducer", NullDeltaReducer())


__all__ = ["Config", "NullDeltaReducer", "setup"]
