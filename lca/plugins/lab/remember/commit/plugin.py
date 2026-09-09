"""remember.commit — Append turn fact to Session via JournalProvider.

worker: commit(*, in_reflection, in_observation, in_decision, admitted, provider_config) -> journal_fact
kind: TRANSFORMER
out_port: journal_fact
config: provider_config
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.memory.ops import LcaRememberJournalProvider


def commit(
    *,
    in_reflection: Artifact | None,
    in_observation: Artifact | None,
    in_decision: Artifact | None,
    admitted: Artifact | None,
    provider_config: dict[str, Any] | None = None,
) -> dict[str, Artifact]:
    """Append turn fact to Session。"""
    provider = LcaRememberJournalProvider.from_node_config(provider_config or {})
    return provider.append_journal(
        reflection_artifact=in_reflection,
        observation_artifact=in_observation,
        decision_artifact=in_decision,
        admitted_artifact=admitted,
        out_port="journal_fact",
    )


__all__ = ["commit"]
