"""Memory Provider plugin — Tier-2."""

from __future__ import annotations

from functools import partial

from pydantic import BaseModel, Field

from lca.contracts.capabilities import (
    MEMORY_COMPACTION_POLICY,
    MEMORY_RETRIEVAL_POLICY,
    MEMORY_WRITE_POLICY,
)
from lca.contracts.protocols import MemorySystem
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Select installed memory implementations and temporal-store settings."""

    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["simple"])
    temporal_db_path: str = ".lca/temporal-memory.sqlite3"
    temporal_scope_id: str = "local:default"
    temporal_recall_limit: int = 8


@plugin(
    id="lca-memory-provider",
    requires=[
        "memory",
        MEMORY_WRITE_POLICY.key,
        MEMORY_COMPACTION_POLICY.key,
        MEMORY_RETRIEVAL_POLICY.key,
    ],
    implements=[MemorySystem],
    layer="L0",
    effects="memory",
    description="Register simple and optional temporal MemorySystem providers on the Memory service.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register memory factories through the active profile's governance policies."""
    from lca.cognition.memory.simple_memory import SimpleMemorySystem

    write_policy = ctx.require(MEMORY_WRITE_POLICY.key)
    compaction_policy = ctx.require(MEMORY_COMPACTION_POLICY.key)
    retrieval_policy_factory = ctx.require(MEMORY_RETRIEVAL_POLICY.key)

    def build_simple_memory(**kwargs: object) -> MemorySystem:
        if {"policy", "compaction", "retrieval"} & kwargs.keys():
            raise TypeError(
                "memory policies are selected by the active profile, not create() arguments"
            )
        return SimpleMemorySystem(
            policy=write_policy,
            compaction=compaction_policy,
            retrieval=retrieval_policy_factory(),
            **kwargs,
        )

    service = ctx.require("memory")
    if "simple" in config.providers:
        service.register("simple", build_simple_memory)
    if "temporal" in config.providers:
        from lca.cognition.memory.temporal_memory import TemporalMemorySystem

        service.register(
            "temporal",
            partial(
                TemporalMemorySystem,
                db_path=config.temporal_db_path,
                scope_id=config.temporal_scope_id,
                recall_limit=config.temporal_recall_limit,
                policy=write_policy,
            ),
        )
