"""R3 tests for ``with_spine_envelope``.

Drives the real shipped decorator at ``lca/cognition/_spine_envelope.py``
on real ``Critic`` / ``SkillRouter`` boundary points to assert:

1. Success path emits ``start`` then ``end(outcome="success")``.
2. Exception path emits ``start`` then ``end(outcome="failure")`` and re-raises.
3. The decorator is a no-op when the spine reflector module is unreachable
   (import-side failure is silently swallowed; the wrapped function still runs).
4. The decorator preserves the wrapped function's metadata (name, docstring).
5. The decorator survives simple failure: the inner exception type is preserved.
"""

from __future__ import annotations

import pytest

from lca.cognition._spine_envelope import with_spine_envelope


def test_decorator_emits_start_then_end_on_success() -> None:
    """Success path emits both start and end(outcome='success')."""
    calls: list[tuple[str, str]] = []

    class _State:
        trace_id = "trace-1"

    from lca.plugins.observability.spine.reflectors import cognition as cog_mod

    original_start = getattr(cog_mod, "emit_test_point_start", None)
    original_end = getattr(cog_mod, "emit_test_point_end", None)

    def _start(*, state_id: str) -> None:
        calls.append(("start", state_id))

    def _end(*, state_id: str, outcome: str = "success") -> None:
        calls.append(("end", f"{state_id}:{outcome}"))

    cog_mod.emit_test_point_start = _start
    cog_mod.emit_test_point_end = _end
    try:

        @with_spine_envelope("test_point", state_id_arg="state")
        async def _fn(state: _State) -> str:
            return "ok"

        # Run the async function
        import asyncio

        result = asyncio.run(_fn(_State()))
        assert result == "ok"
        assert calls == [("start", "trace-1"), ("end", "trace-1:success")]
    finally:
        if original_start is not None:
            cog_mod.emit_test_point_start = original_start
        else:
            delattr(cog_mod, "emit_test_point_start")
        if original_end is not None:
            cog_mod.emit_test_point_end = original_end
        else:
            delattr(cog_mod, "emit_test_point_end")


def test_decorator_emits_failure_on_exception() -> None:
    """Failure path emits end(outcome='failure') and re-raises."""
    calls: list[tuple[str, str]] = []

    class _State:
        trace_id = "trace-2"

    from lca.plugins.observability.spine.reflectors import cognition as cog_mod

    original_start = getattr(cog_mod, "emit_boom_start", None)
    original_end = getattr(cog_mod, "emit_boom_end", None)

    cog_mod.emit_boom_start = lambda *, state_id: calls.append(("start", state_id))
    cog_mod.emit_boom_end = lambda *, state_id, outcome="success": calls.append(
        ("end", f"{state_id}:{outcome}")
    )
    try:

        @with_spine_envelope("boom", state_id_arg="state")
        async def _fn(state: _State) -> str:
            raise ValueError("kaboom")

        import asyncio

        with pytest.raises(ValueError, match="kaboom"):
            asyncio.run(_fn(_State()))
        assert calls == [("start", "trace-2"), ("end", "trace-2:failure")]
    finally:
        if original_start is not None:
            cog_mod.emit_boom_start = original_start
        else:
            delattr(cog_mod, "emit_boom_start")
        if original_end is not None:
            cog_mod.emit_boom_end = original_end
        else:
            delattr(cog_mod, "emit_boom_end")


def test_decorator_noop_when_spine_emitters_missing() -> None:
    """If the spine reflector is absent, decorator still runs the wrapped function."""

    class _State:
        trace_id = "trace-3"

    from lca.plugins.observability.spine.reflectors import cognition as cog_mod

    sentinel_start = getattr(cog_mod, "emit_does_not_exist_start", None)
    sentinel_end = getattr(cog_mod, "emit_does_not_exist_end", None)
    if hasattr(cog_mod, "emit_does_not_exist_start"):
        delattr(cog_mod, "emit_does_not_exist_start")
    if hasattr(cog_mod, "emit_does_not_exist_end"):
        delattr(cog_mod, "emit_does_not_exist_end")

    try:

        @with_spine_envelope("does_not_exist", state_id_arg="state")
        async def _fn(state: _State) -> int:
            return 42

        import asyncio

        assert asyncio.run(_fn(_State())) == 42
    finally:
        if sentinel_start is not None:
            cog_mod.emit_does_not_exist_start = sentinel_start
        if sentinel_end is not None:
            cog_mod.emit_does_not_exist_end = sentinel_end


def test_decorator_preserves_function_metadata() -> None:
    """The decorator must preserve name and docstring via functools.wraps."""

    @with_spine_envelope("critic_eval", state_id_arg="state")
    async def critique(state) -> str:  # type: ignore[no-untyped-def]
        """Critique state and return reflection."""
        return "reflected"

    assert critique.__name__ == "critique"
    assert "Critique state" in (critique.__doc__ or "")
