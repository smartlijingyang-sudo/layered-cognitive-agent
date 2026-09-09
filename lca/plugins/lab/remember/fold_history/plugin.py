"""remember.fold_history — Session → messages (history passthrough).

worker: fold_history(*, session) -> messages
kind: TRANSFORMER
out_port: messages
in: session=session
"""
from agent_lab.primitives.artifact import Artifact


def fold_history(
    *,
    session: Artifact | None,
) -> dict[str, Artifact]:
    """Pass session artifact through as messages."""
    return {"messages": session}


__all__ = ["fold_history"]
