"""HTTP RunRequest → RunIntent adapter (ADR-0199 P1-08).

Per ADR-0199 I-HPC-1 this module is the only place where the transport-
layer ``RunRequest`` is converted to the wire-agnostic ``RunIntent``. The
adapter is a pure function: no I/O, no env reads, no starlette/fastapi
imports. Any new wire field belongs here, not at the facade or the
contracts layer.
"""

from __future__ import annotations

from typing import Any

from lca.application.runtime.adapters._mode import coerce_mode
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.runtime.intent import RunIntent
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest


def run_request_to_intent(
    request: RunRequest,
    *,
    surface: str = "http",
    device_id: str = "",
) -> RunIntent:
    """Translate a transport-layer ``RunRequest`` into a wire-agnostic ``RunIntent``.

    Per ADR-0199 I-HPC-1: this adapter is the ONLY place where the wire-
    layer ``RunRequest`` is converted to ``RunIntent``. The ``ctx``,
    ``agent``, ``plane``, ``extra_plane`` and ``question`` fields are
    intentionally dropped — they belong to the L0 carrier / K3 boot
    layers, not to the activation closure (I-HPC-2). The ``device_id``
    parameter overrides the value carried on the request when non-empty,
    so a higher layer (e.g. routes plugin) can supply a transport-
    derived identity the carrier did not embed.

    Imports ``RunRequest`` at module level for type clarity. If a
    circular import emerges, switch to ``TYPE_CHECKING``.
    """
    attachment_ids: tuple[str, ...] = tuple(getattr(request, "attachment_ids", ()) or ())

    prior_turns_raw = getattr(request, "prior_turns", ()) or ()
    prior_turns: tuple[ConversationTurn, ...] = tuple(
        turn if isinstance(turn, ConversationTurn) else ConversationTurn(**turn)
        for turn in prior_turns_raw
    )

    options_raw: Any = getattr(request, "options", {}) or {}
    options = options_raw if isinstance(options_raw, dict) else dict(options_raw)

    assistant_id_raw = getattr(request, "assistant_id", None)
    assistant_id: str | None = assistant_id_raw if assistant_id_raw else None

    request_device_id = getattr(request, "device_id", "") or ""

    return RunIntent(
        profile_path=request.profile,
        user_text=request.user_text,
        mode=coerce_mode(getattr(request, "mode", "solo")),
        session_id=None,
        assistant_id=assistant_id,
        attachment_ids=attachment_ids,
        prior_turns=prior_turns,
        execution_target=str(getattr(request, "execution_target", "") or ""),
        options=options,
        surface=surface,  # type: ignore[arg-type]
        device_id=device_id or request_device_id,
    )


__all__ = ("run_request_to_intent",)
