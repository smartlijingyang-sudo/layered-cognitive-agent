"""Profile provider for the durable candidate-only learning-review ticket store."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import LEARNING_REVIEW_TICKET_STORE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.learning import LearningReviewTicketStore
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.learning.review_ticket_sqlite import SqliteLearningReviewTicketStore


class Config(BaseModel):
    """Storage location selected by a self-improving Profile."""

    model_config = ConfigDict(extra="forbid")

    database_path: str = ".lca/learning-review.db"


@plugin(
    id="lca-learning-review-ticket-store",
    Config=Config,
    provides=[LEARNING_REVIEW_TICKET_STORE.key],
    requires=[],
    implements=[LearningReviewTicketStore],
    layer="L0",
    effects=EffectClass.NONE,
    description="Provide durable SQLite storage and leasing for learning-review tickets.",
    test_suite="tests/architecture/test_learning_review_ticket_store.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-learning-review-ticket-store.checked",
                "lca-learning-review-ticket-store.served",
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
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Mount the profile-selected review-ticket storage adapter."""

    if not isinstance(config, Config):
        raise TypeError("learning review ticket store config must be Config")
    ctx.provide(
        LEARNING_REVIEW_TICKET_STORE.key,
        SqliteLearningReviewTicketStore(Path(config.database_path)),
    )


__all__ = ["Config", "setup"]
