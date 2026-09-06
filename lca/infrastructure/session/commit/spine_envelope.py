"""@with_spine_envelope — spine start/end envelope via FactGateway (ADR-0194 P1-14).

Wraps cognition boundary callables in ``publish_ep_bound`` start/end pairs.
Spine mirror failures must not block cognition (same contract as inline envelopes).
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from lca.contracts.models.core.state.state import AgentState
from lca.loop.fact_gateway import publish_ep_bound

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _execution_points(point: str) -> tuple[str, str]:
    base = point.replace("_", ".")
    return f"{base}.start", f"{base}.end"


def with_spine_envelope(
    point: str,
    *,
    state_id_arg: str = "state",
    actor: str = "cognition",
) -> Callable[[Callable[_P, Coroutine[Any, Any, _R]]], Callable[_P, Coroutine[Any, Any, _R]]]:
    """Wrap ``point``'s execution in a start/end spine envelope via ``publish_ep_bound``."""

    start_ep, end_ep = _execution_points(point)

    def decorator(
        fn: Callable[_P, Coroutine[Any, Any, _R]],
    ) -> Callable[_P, Coroutine[Any, Any, _R]]:
        @functools.wraps(fn)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            state_obj = kwargs.get(state_id_arg) or (args[0] if args else None)
            state_id = getattr(state_obj, "trace_id", "") or ""
            state = state_obj if isinstance(state_obj, AgentState) else None
            with contextlib.suppress(Exception):
                publish_ep_bound(
                    start_ep,
                    {"state_id": state_id},
                    state=state,
                    actor=actor,
                )
            try:
                result = await fn(*args, **kwargs)
            except BaseException:
                with contextlib.suppress(Exception):
                    publish_ep_bound(
                        end_ep,
                        {"state_id": state_id, "outcome": "failure"},
                        state=state,
                        actor=actor,
                    )
                raise
            with contextlib.suppress(Exception):
                publish_ep_bound(
                    end_ep,
                    {"state_id": state_id, "outcome": "success"},
                    state=state,
                    actor=actor,
                )
            return result

        return wrapped

    return decorator


__all__ = ["with_spine_envelope"]
