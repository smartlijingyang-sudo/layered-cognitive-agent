"""reflect.join — Merge all inputs into one combined artifact.

worker: join(*, in_observation, in_decision, in_prior_reflection) -> combined
kind: TRANSFORMER
out_port: combined
"""
from agent_lab.primitives.artifact import Artifact, ArtifactKind


def join(
    *,
    in_observation: Artifact,
    in_decision: Artifact,
    in_prior_reflection: Artifact,
) -> dict[str, Artifact]:
    """把所有输入 artifact 的 content 合并成一个 combined。"""
    merged: dict[str, object] = {}
    for port_name, artifact in {
        "in_observation": in_observation,
        "in_decision": in_decision,
        "in_prior_reflection": in_prior_reflection,
    }.items():
        content = artifact.content
        merged[port_name] = content if isinstance(content, dict) else {"_raw": content}
    return {
        "combined": Artifact(
            kind=ArtifactKind.FACT,
            content=merged,
            schema_ref="reflect.combined.v1",
        )
    }


__all__ = ["join"]
