"""remember.snapshot — StateStore.save + emit remember_signal.

worker: snapshot(*, journal_fact, provider_config) -> state_ref + remember_signal
kind: TRANSFORMER
out_port: state_ref
config: provider_config
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.memory.ops import LcaRememberStateStoreProvider


def snapshot(
    *,
    journal_fact: Artifact | None,
    provider_config: dict[str, Any] | None = None,
) -> dict[str, Artifact]:
    """通过 StateStoreProvider 保存 state。"""
    provider = LcaRememberStateStoreProvider.from_node_config(provider_config or {})
    return provider.save(journal_artifact=journal_fact)


__all__ = ["snapshot"]
