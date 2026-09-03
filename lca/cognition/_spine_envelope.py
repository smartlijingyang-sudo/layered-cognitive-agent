"""@with_spine_envelope — single decorator for cognition-layer spine envelopes (R3).

The cognition layer (think/reflect/act/synthesize boundaries) historically
hand-wrote the ``emit_*_start → try → emit_*_end(outcome=success|failure)``
envelope at every Think/Reflect/Synthesize/SkillRouter boundary.  Seven
modules repeated the same shape, each with a fresh inline import of
``lca.plugins.observability.spine.reflectors.cognition``.  R3 consolidates
the simplest envelope (a single start/end pair around a callable body)
into this decorator.

The decorator:
1. Resolves the ``emit_*_start`` / ``emit_*_end`` helpers from the cognition
   reflector module via a small registry (set by the brain module that owns
   the execution-point).
2. Wraps the callable in the envelope; failures log ``outcome="failure"``
   and re-raise.
3. Returns the original value on success.

Limitations: R3 targets the SIMPLE envelope (1 start, 1 end).  Composite
envelopes like ``PromptReasoner.generate_thoughts`` (which emits
``emit_prompt_assembler_start/end`` AND ``emit_reasoner_reason_start/end``
with different signatures and partial-failure handling) are out of scope.

Deletion test: yes, this concentrates the boilerplate in one decorator.
Each of the 7 modules can shrink by ~10 lines.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")


def with_spine_envelope(
    point: str,
    *,
    state_id_arg: str = "state",
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Wrap ``point``'s execution in a start/end spine envelope.

    ``state_id_arg`` names the kwarg on the wrapped callable whose
    ``trace_id`` attribute is used as ``state_id`` for the spine payload.
    Defaults to ``"state"`` which matches ``Critic.critique``, ``SkillRouter.route``,
    and friends.

    The decorator expects the spine reflector module to export
    ``emit_<point>_start`` and ``emit_<point>_end`` functions with the
    canonical signature ``(*, state_id: str, outcome: Outcome = "success")``.
    """

    def decorator(
        fn: Callable[_P, Awaitable[_R]],
    ) -> Callable[_P, Awaitable[_R]]:
        @functools.wraps(fn)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            from lca.plugins.observability.spine.reflectors import cognition as _cog

            start_fn = getattr(_cog, f"emit_{point}_start", None)
            end_fn = getattr(_cog, f"emit_{point}_end", None)
            if start_fn is None or end_fn is None:
                # No spine wired: silently no-op (mirrors the existing pattern).
                return await fn(*args, **kwargs)

            state_obj = kwargs.get(state_id_arg) or (args[0] if args else None)
            state_id = getattr(state_obj, "trace_id", "") or ""
            start_fn(state_id=state_id)
            try:
                result = await fn(*args, **kwargs)
            except BaseException:
                end_fn(state_id=state_id, outcome="failure")
                raise
            end_fn(state_id=state_id, outcome="success")
            return result

        return wrapped

    return decorator


__all__ = ["with_spine_envelope"]
