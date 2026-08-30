"""Profile provider for the durable candidate-only learning-review ticket store."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import LEARNING_REVIEW_TICKET_STORE
from lca.contracts.protocols.learning import LearningReviewTicketStore
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.layer0_infra.learning.review_ticket_sqlite import SqliteLearningReviewTicketStore


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
