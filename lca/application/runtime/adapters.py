"""L0 wire → RunIntent adapters (ADR-0199 §2.2.1 / P1-08).

These adapters are the only bridge between transport-layer wire objects
(RunRequest, CLI argv) and the wire-agnostic RunIntent contract. They
MUST NOT import starlette / fastapi / argparse — that would leak L0
concerns into the contracts / application boundary.

Per I-HPC-1 the L0 surface's only job is to produce a RunIntent; the
facade in lca.application.runtime is what interprets it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeGuard

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.runtime.intent import RunIntent, RunMode

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest

_ALLOWED_MODES: frozenset[RunMode] = frozenset({"solo", "team"})


def _is_run_mode(value: object) -> TypeGuard[RunMode]:
    return isinstance(value, str) and value in _ALLOWED_MODES


def coerce_mode(raw: object, *, field: str = "mode") -> RunMode:
    """Narrow an arbitrary wire value to ``RunMode``.

    Accepts the literal strings ``"solo"`` / ``"team"`` exactly.
    Rejects ``None``, ``bool``, non-strings, and any other string with
    a :class:`ValueError` that names the field, so the L1 facade never
    sees a value outside the contract's closed set.
    """
    if _is_run_mode(raw):
        return raw
    raise ValueError(f"RunIntent.{field} must be one of {sorted(_ALLOWED_MODES)}, got {raw!r}")


@dataclass(frozen=True, slots=True)
class CliRunArgs:
    """Carrier of CLI-parsed run arguments.

    Defined here so the CLI parser (P1-13 / lca-ops runs create) does
    not need to know about ``RunIntent``'s full field set. The parser
    only fills what the user passed; defaults fill the rest. All fields
    are plain data so the carrier is hashable and replayable (C8).
    """

    profile: str
    user_text: str
    mode: str = "solo"
    session_id: str | None = None
    assistant_id: str | None = None
    attachment_ids: tuple[str, ...] = ()
    execution_target: str = ""
    options: Mapping[str, Any] | None = None
    device_id: str = ""


def cli_args_to_intent(
    args: CliRunArgs,
    *,
    surface: str = "cli",
) -> RunIntent:
    """Translate parsed CLI args into a wire-agnostic ``RunIntent``.

    Per ADR-0199 I-HPC-1: the CLI parser is L0; it only produces
    ``CliRunArgs``. This adapter is the only place that converts
    ``CliRunArgs`` → ``RunIntent``. CLI runs always start with no
    prior turns — there is no carrier of conversation history at the
    CLI layer.
    """
    options: Mapping[str, Any] = args.options if args.options is not None else {}

    return RunIntent(
        profile_path=args.profile,
        user_text=args.user_text,
        mode=coerce_mode(args.mode),
        session_id=args.session_id,
        assistant_id=args.assistant_id,
        attachment_ids=tuple(args.attachment_ids),
        prior_turns=(),
        execution_target=args.execution_target,
        options=dict(options),
        surface=surface,  # type: ignore[arg-type]
        device_id=args.device_id,
    )


def run_request_to_intent(
    request: RunRequest | Any,
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
    assistant_id: str | None = assistant_id_raw or None

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


__all__ = (
    "CliRunArgs",
    "cli_args_to_intent",
    "coerce_mode",
    "run_request_to_intent",
)
