"""DSH user prompt — LCA ingress only; no plane system role or skill preamble."""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.models.core.conversation import ConversationTurn


def compose_dsh_prompt(
    question: str,
    prior_turns: Sequence[ConversationTurn],
) -> str:
    """User-visible task for ``session/prompt``.

    Workspace roots, skills, and tool policy come from the DSH SDK
    (``cwd``, ``cordis``, ``DSH_CWD``) — not from LCA ``plane_system_role``.
    """
    blocks: list[str] = []
    if prior_turns:
        lines = [f"{turn.role}: {turn.content}" for turn in prior_turns if turn.content.strip()]
        if lines:
            blocks.append("Prior conversation:\n" + "\n\n".join(lines))
    base = question.strip()
    if base:
        blocks.append(base)
    return "\n\n".join(block for block in blocks if block.strip())
