"""perceive.resolve — Resolve Sensor list + MemorySystem from provider_config.

worker: resolve(*, state_artifact, provider_config) -> sensors + memory_ref
kind: TRANSFORMER
out_port: sensors
in: state=state_artifact
config: provider_config
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import LcaPerceiveResolveProvider


def resolve(
    *,
    state_artifact: Artifact | None,
    provider_config: dict[str, Any],
) -> dict[str, Artifact]:
    """由 provider_config 构造 LcaPerceiveResolveProvider 并 resolve。"""
    return LcaPerceiveResolveProvider.from_node_config(provider_config).resolve()


__all__ = ["resolve"]
