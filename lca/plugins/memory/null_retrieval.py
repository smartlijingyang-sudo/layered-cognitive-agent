"""NullRetrievalPolicy plugin — named factory ``retrieval.null`` (ADR-0068 / 宪法 §3.4)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import MEMORY_RETRIEVAL_POLICY
from lca.contracts.protocols import RetrievalPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-retrieval-null",
    provides=["retrieval.null", MEMORY_RETRIEVAL_POLICY.key],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "Provide NullRetrievalPolicy as ``retrieval.null`` (ADR-0068 default). "
        "Profile without standard-memory bundle ships empty retrieved_context."
    ),
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide NullRetrievalPolicy as ``retrieval.null``."""
    from lca.layer1_cognitive.memory.null_retrieval_policy import NullRetrievalPolicy

    ctx.provide("retrieval.null", NullRetrievalPolicy)
    ctx.provide(MEMORY_RETRIEVAL_POLICY.key, NullRetrievalPolicy)
