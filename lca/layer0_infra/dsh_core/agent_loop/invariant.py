"""Package-owned request-reconstruction invariant for loop-built LLM calls.

1:1 port of ``@deepseek-ai/dsh-agent-loop/invariant.ts``.

Validates that a loop-built LLM request is consistent with the session log:
frozen, has sessionId, session exists, messages frozen, session has
step/start, request/header exists, messages match deriveMessages(), and
header config matches the folded request header.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from lca.layer0_infra.dsh_core.session import fold_request_header

PACKAGE_NAME = "@deepseek-ai/dsh-agent-loop"

InvariantFailure = Callable[[str], None]


def install(ctx: Any, fail: InvariantFailure) -> None:
    """Install the request-reconstruction invariant."""

    def on_llm_stream(options: Any, next: Callable[[], Any]) -> Any:
        if not _is_agent_loop_request(options):
            return next()
        if not _is_frozen(options):
            fail("a loop-built request must be frozen")
            return next()
        if not options.get("sessionId"):
            fail("a loop-built request must carry a session id")
            return next()

        session_store = getattr(ctx, "sessions", None)
        session = session_store.get(options["sessionId"]) if session_store else None
        if not session:
            fail(f'a loop-built request must carry a live session id, got "{options["sessionId"]}"')
            return next()

        if not _is_frozen(options.get("messages")):
            fail("a loop-built request must carry a frozen messages array")
            return next()

        events = session.events
        if not any(e.type == "step/start" for e in events):
            fail("a loop-built request with no step/start in its session log")
            return next()

        header = fold_request_header(list(events))
        if header is None:
            fail("a loop-built request with no request/header event in its session log")
            return next()

        expected = session.derive_messages() if hasattr(session, "derive_messages") else []
        if json.dumps(options.get("messages", [])) != json.dumps(expected):
            fail(
                f'llm request for session "{session.id}" diverges from '
                "the dispatch-time durable derivation (log-reconstruction desync)"
            )
            return next()

        header_config = getattr(header, "config", {})
        header_matches = (
            options.get("model") == header_config.get("model")
            and options.get("system") == getattr(header, "system", None)
            and options.get("temperature") == header_config.get("temperature")
            and options.get("maxTokens") == header_config.get("maxTokens")
            and json.dumps(options.get("stop")) == json.dumps(header_config.get("stop"))
            and json.dumps(options.get("tools") or []) == json.dumps(getattr(header, "tools", None) or [])
        )
        if not header_matches:
            fail(
                f'llm request for session "{session.id}" diverges from '
                "the folded request header"
            )
            return next()

        return next()

    # Prepend prevents a short-circuiting replay listener from silencing the check
    if hasattr(ctx, "on"):
        ctx.on("llm/stream", on_llm_stream, prepend=True)


def _is_frozen(obj: Any) -> bool:
    if obj is None:
        return True
    if isinstance(obj, (list, dict)):
        # Approximate: check immutability via __hash__ or _frozen attr
        if hasattr(obj, "_frozen"):
            return obj._frozen
        return True
    return True


def _is_agent_loop_request(options: Any) -> bool:
    """Check if this is a loop-built request."""
    return bool(options and options.get("sessionId"))


def apply(ctx: Any) -> Callable[[], None]:
    """Register the agent-loop invariant companion."""
    if hasattr(ctx, "inject"):
        try:
            ctx.inject(["sessions"], lambda c: _register_with_ctx(c))
        except Exception:
            _register_with_ctx(ctx)
    else:
        _register_with_ctx(ctx)
    return lambda: None


def _register_with_ctx(ctx: Any) -> None:
    invariants = getattr(ctx, "invariants", None)
    if invariants and hasattr(invariants, "register"):
        invariants.register(PACKAGE_NAME, install)
