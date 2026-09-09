"""think.guard — DecisionGate.enforce → enforced_decision + think_signal.

worker: guard(*, decision, in_state, provider_config, null_gate, gate_factory,
              fixture_gate_name, allow_empty_chain, gate, out_port) -> enforced_decision + think_signal
kind: TRANSFORMER
out_port: enforced_decision
in: decision=decision in_state=in_state
config: provider_config null_gate gate_factory fixture_gate_name allow_empty_chain gate out_port
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

from lca.plugins.lab.think.guard.ops import enforce_decision


def guard(
    *,
    decision: Artifact | None,
    in_state: Artifact | None,
    provider_config: dict[str, Any] | None = None,
    null_gate: bool = False,
    gate_factory: str | None = None,
    fixture_gate_name: str | None = None,
    allow_empty_chain: bool = False,
    gate: str | None = None,
    out_port: str = "enforced_decision",
) -> dict[str, Artifact]:
    """DecisionGate.enforce → enforced_decision + think_signal。"""
    merged: dict[str, Any] = dict(provider_config or {})
    for k in ("null_gate", "gate_factory", "fixture_gate_name", "allow_empty_chain", "gate"):
        v = locals()[k]
        if v is not None and v is not False:
            merged[k] = v
    result = enforce_decision(
        decision,
        in_state,
        config=merged,
        out_port=out_port,
    )
    # 兜底:result 可能少端口,补 None Artifact(让 framework wiring 不缺)
    for port in (out_port, "think_signal"):
        if port not in result:
            result[port] = Artifact(kind=ArtifactKind.FACT, content=None)
    return result


__all__ = ["guard"]
