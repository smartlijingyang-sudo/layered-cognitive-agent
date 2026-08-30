"""LayeredRetrievalPolicy plugin — named factory ``retrieval.layered`` (ADR-0068)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import MEMORY_RETRIEVAL_POLICY
from lca.contracts.protocols import RetrievalPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-retrieval-layered",
    provides=["retrieval.layered", MEMORY_RETRIEVAL_POLICY.key],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "Provide LayeredRetrievalPolicy as ``retrieval.layered``. "
        "Standard bundle upgrades default null retrieval to per-layer weighted."
    ),
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide LayeredRetrievalPolicy as ``retrieval.layered``."""
    from lca.layer1_cognitive.memory.layered_retrieval_policy import (
        LayeredRetrievalPolicy,
    )

    ctx.provide("retrieval.layered", LayeredRetrievalPolicy)
    ctx.provide(MEMORY_RETRIEVAL_POLICY.key, LayeredRetrievalPolicy)
