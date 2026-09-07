"""CLI args → RunIntent adapter (ADR-0199 P1-08 / P1-13).

Per ADR-0199 I-HPC-1 the CLI parser (argparse / click / typer — P1-13)
is L0 and only produces a ``CliRunArgs`` carrier. This adapter is the
only place that converts ``CliRunArgs`` → ``RunIntent``. The facade in
``lca.application.runtime`` then consumes the intent identically to
the HTTP path.

No argparse / click / typer imports: the adapter stays wire-agnostic
so the same contract applies to a future REST gateway or batch runner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.application.runtime.adapters._mode import coerce_mode
from lca.contracts.runtime.intent import RunIntent


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


__all__ = ("CliRunArgs", "cli_args_to_intent")
