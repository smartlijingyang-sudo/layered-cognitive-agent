"""Profile-selected semantic compaction policy for the simple memory backend."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import MEMORY_COMPACTION_POLICY
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.cognition.memory.policy import CompactionPolicy
from lca.cognition.memory.semantic_compaction import SemanticCompactionPolicy


class Config(BaseModel):
    """Select auditable shadow or enforce semantic context compaction.

    Shadow mode is the safe default: it computes an evidence-linked summary
    candidate but exposes the legacy exact-record selection to the Reasoner.
    Enforce mode replaces lower-priority records with one untrusted historical
    summary record after checking that the result is smaller.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["shadow", "enforce"] = "shadow"
    max_summary_characters: int = Field(default=1_200, ge=256)


@plugin(
    id="lca-memory-compaction-policy-simple",
    Config=Config,
    provides=[MEMORY_COMPACTION_POLICY.key],
    requires=[],
    implements=[CompactionPolicy],
    layer="L0",
    effects="none",
    description="Provide an auditable semantic compaction policy for memory context views.",
    test_suite="tests/test_memory_policy.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Provide the Profile-selected semantic compactor to memory assemblers."""

    if not isinstance(config, Config):
        raise TypeError("memory compaction policy config must be Config")
    ctx.provide(
        MEMORY_COMPACTION_POLICY.key,
        SemanticCompactionPolicy(
            mode=config.mode,
            max_summary_characters=config.max_summary_characters,
        ),
    )


__all__ = ["Config", "setup"]
