"""Default ``journal_committer`` capability provider.

Registers the in-memory journal committer used by every Cordis-bootstrapped
declarative interpreter instance.  Production deployments are expected to
register a durable replacement under the same capability key; this module
exists so the interpreter plugin always has something to inject at setup.
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
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    JournalCommitter,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.declarative.plugins.interpreter import InMemoryJournalCommitter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Default in-memory journal has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="declarative.journal_committer",
    requires=[],
    provides=["journal_committer"],
    implements=[JournalCommitter],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default in-memory JournalCommitter so declarative profiles "
        "have a working durable-fact seam without bespoke plugin setup."
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
                "declarative.journal_committer.checked",
                "declarative.journal_committer.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("journal_committer",),
        emits=("journal_committer.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default in-memory JournalCommitter to runtime assembly."""

    del config
    ctx.provide("journal_committer", InMemoryJournalCommitter())


__all__ = ["Config", "setup"]
