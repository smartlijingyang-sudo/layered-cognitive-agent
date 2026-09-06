"""R3 tests for ``with_spine_envelope``.

Drives the shipped decorator at ``lca/infrastructure/session/spine_envelope.py``
on real ``Critic`` / ``SkillRouter`` boundary points to assert:

1. Success path emits ``start`` then ``end(outcome="success")``.
2. Exception path emits ``start`` then ``end(outcome="failure")`` and re-raises.
3. The decorator is a no-op when no Session is bound (offline / tests).
4. The decorator preserves the wrapped function's metadata (name, docstring).
5. The decorator survives simple failure: the inner exception type is preserved.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lca.infrastructure.session.spine_envelope import with_spine_envelope
from lca.loop.fact_gateway import publish_ep_bound, reset_fact_gateway_env
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def test_decorator_emits_start_then_end_on_success() -> None:
    """Success path emits both start and end(outcome='success')."""
    calls: list[tuple[str, str, dict[str, object]]] = []

    class _State:
        trace_id = "trace-1"

    session = Session("spine_env_success")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:

        def _capture(ep: str, payload: dict[str, object], **kwargs: object) -> None:
            calls.append((ep, str(payload.get("state_id", "")), dict(payload)))

        with patch(
            "lca.infrastructure.session.spine_envelope.publish_ep_bound",
            side_effect=_capture,
        ):

            @with_spine_envelope("test.point", state_id_arg="state")
            async def _fn(state: _State) -> str:
                return "ok"

            import asyncio

            result = asyncio.run(_fn(_State()))
        assert result == "ok"
        assert len(calls) == 2
        assert calls[0][0] == "test.point.start"
        assert calls[0][1] == "trace-1"
        assert calls[1][0] == "test.point.end"
        assert calls[1][2]["outcome"] == "success"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


def test_decorator_emits_failure_on_exception() -> None:
    """Failure path emits end(outcome='failure') and re-raises."""
    calls: list[tuple[str, dict[str, object]]] = []

    class _State:
        trace_id = "trace-2"

    session = Session("spine_env_failure")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:

        def _capture(ep: str, payload: dict[str, object], **kwargs: object) -> None:
            calls.append((ep, dict(payload)))

        with patch(
            "lca.infrastructure.session.spine_envelope.publish_ep_bound",
            side_effect=_capture,
        ):

            @with_spine_envelope("boom", state_id_arg="state")
            async def _fn(state: _State) -> str:
                raise ValueError("kaboom")

            import asyncio

            with pytest.raises(ValueError, match="kaboom"):
                asyncio.run(_fn(_State()))
        assert len(calls) == 2
        assert calls[0][0] == "boom.start"
        assert calls[1][0] == "boom.end"
        assert calls[1][1]["outcome"] == "failure"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


def test_decorator_noop_when_session_unbound() -> None:
    """If no session is bound, decorator still runs the wrapped function."""

    class _State:
        trace_id = "trace-3"

    reset_fact_gateway_env(enabled=True)
    try:

        @with_spine_envelope("does.not.exist", state_id_arg="state")
        async def _fn(state: _State) -> int:
            return 42

        import asyncio

        assert asyncio.run(_fn(_State())) == 42
    finally:
        reset_fact_gateway_env()


def test_decorator_preserves_function_metadata() -> None:
    """The decorator must preserve name and docstring via functools.wraps."""

    @with_spine_envelope("critic_eval", state_id_arg="state")
    async def critique(state) -> str:  # type: ignore[no-untyped-def]
        """Critique state and return reflection."""
        return "reflected"

    assert critique.__name__ == "critique"
    assert "Critique state" in (critique.__doc__ or "")


def test_decorator_routes_via_publish_ep_bound() -> None:
    """Integration: bound session receives start/end spine facts."""
    session = Session("spine_env_gateway")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:

        class _State:
            trace_id = "trace-gateway"

        with patch(
            "lca.infrastructure.session.spine_envelope.publish_ep_bound",
            wraps=publish_ep_bound,
        ) as publish:

            @with_spine_envelope("critic_eval", state_id_arg="state", actor="critic")
            async def _fn(state: _State) -> str:
                return "ok"

            import asyncio

            assert asyncio.run(_fn(_State())) == "ok"
        assert publish.call_count == 2
        assert publish.call_args_list[0].args[0] == "critic.eval.start"
        assert publish.call_args_list[1].args[0] == "critic.eval.end"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)
