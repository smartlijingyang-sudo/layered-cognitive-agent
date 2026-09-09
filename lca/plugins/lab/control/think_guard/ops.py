from __future__ import annotations

"""Inlined ops (PR-D)."""

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind


def handle_control_decision(
    inbound: Artifact | None,
    *,
    mode: str,
    out_port: str,
    enforce_config: dict[str, Any],
) -> dict[str, Artifact]:
    if mode != "enforce":
        if inbound is None:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.FACT,
                    content=None,
                    schema_ref="decision.v1",
                )
            }
        return {out_port: inbound}

    from agent_lab.nodes.think.guard.ops import enforce_decision

    result = enforce_decision(
        inbound,
        None,
        config=enforce_config,
        out_port=out_port,
    )
    return {out_port: result[out_port]}
