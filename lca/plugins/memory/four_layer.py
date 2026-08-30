"""Four-layer memory plugin stub (MemGPT/Voyager/standard scenarios).

Tracked by ADR-0107. This module exists only so that bundle YAMLs
referencing ``$module: lca.plugins.memory.four_layer`` can resolve at
profile-load time; the actual implementation of working / episodic /
semantic / procedural memory layers described in v3 认知原语宪法 §13.5
has not been written.

Do NOT use in production: setup() raises NotImplementedError.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import MEMORY_RETRIEVAL_POLICY
from lca.contracts.protocols import RetrievalPolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """Configuration for the four-layer memory backend."""

    model_config = ConfigDict(extra="forbid")

    default_authority: str = Field(default="tool_observation")
    shared_layers: list[str] = Field(default_factory=lambda: ["semantic"])
    max_procedural: int = Field(default=10_000, ge=0)


@plugin(
    id="lca-memory-four-layer",
    Config=Config,
    provides=[MEMORY_RETRIEVAL_POLICY.key, "memory.four_layer"],
    implements=[RetrievalPolicy],
    layer="L0",
    effects="none",
    description=(
        "Four-layer memory backend (working/episodic/semantic/procedural). "
        "STUB ONLY — see ADR-0107; setup() raises NotImplementedError."
    ),
    test_suite="tests/test_memory_policy.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the four-layer memory backend.

    Raises NotImplementedError — implementation tracked by ADR-0107.
    """
    raise NotImplementedError(
        "lca.plugins.memory.four_layer is a stub; the working/episodic/"
        "semantic/procedural memory backend described in v3 认知原语宪法 §13.5 "
        "has not been implemented. See ADR-0107."
    )


__all__ = ["Config", "setup"]
