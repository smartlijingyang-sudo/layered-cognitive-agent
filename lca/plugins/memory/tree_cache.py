"""Tree cache memory plugin stub (LATS scenario).

Tracked by ADR-0107. This module exists only so that bundle YAMLs
referencing ``$module: lca.plugins.memory.tree_cache`` can resolve at
profile-load time; the MCTS tree evaluation cache described in v3
认知原语宪法 §13.5.4 has not been written.

Do NOT use in production: setup() raises NotImplementedError.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import MEMORY_RETRIEVAL_POLICY
from lca.contracts.protocols import RetrievalPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configuration for the LATS tree evaluation cache."""

    model_config = ConfigDict(extra="forbid")

    tree_evaluation_cache: bool = Field(default=True)
    max_cache_entries: int = Field(default=1_000, ge=0)


@plugin(
    id="lca-memory-tree-cache",
    Config=Config,
    provides=[MEMORY_RETRIEVAL_POLICY.key, "memory.tree_cache"],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "MCTS tree evaluation cache for LATS Brain. "
        "STUB ONLY — see ADR-0107; setup() raises NotImplementedError."
    ),
    test_suite="tests/test_memory_policy.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the tree evaluation cache.

    Raises NotImplementedError — implementation tracked by ADR-0107.
    """
    raise NotImplementedError(
        "lca.plugins.memory.tree_cache is a stub; the MCTS tree evaluation "
        "cache described in v3 认知原语宪法 §13.5.4 has not been implemented. "
        "See ADR-0107."
    )


__all__ = ["Config", "setup"]
