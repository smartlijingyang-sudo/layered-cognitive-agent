"""reflect.critique — Critic.critique(combined) → Reflection.

worker: critique(*, combined, provider_config) -> reflection
kind: TRANSFORMER
out_port: reflection
config: provider_config
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.reflect.ops import LcaReflectCriticProvider


def critique(
    *,
    combined: Artifact | None,
    provider_config: dict[str, Any] | None = None,
) -> dict[str, Artifact]:
    """Run configured critic provider on combined artifact."""
    provider = LcaReflectCriticProvider.from_node_config(provider_config or {})
    return provider.critique(combined_artifact=combined)


__all__ = ["critique"]
