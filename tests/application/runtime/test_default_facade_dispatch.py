"""Behavioural tests for ``DefaultRuntimeFacade.dispatch_*`` (PR-0199-P1-10).

Companion to ``test_default_facade_resolve.py`` (P1-09). Together they
cover the full Application Service surface per ADR-0199 §2.2.3.

The facade has TWO constructor dependencies after P1-10:

  * :class:`lca.application.runtime.plan_resolution.PlanResolutionService`
    — resolve-side (K1+K2).
  * :class:`~lca.application.runtime.default_facade.RunDispatcher` — the
    application-side port that owns K3 boot and lifecycle delegation.

These tests use a structural ``StubDispatcher`` that implements
:protocol:`RunDispatcher` directly (NOT ``MagicMock``) so the structural
typing is exercised end-to-end. ``asyncio_mode = "auto"`` in
``pyproject.toml`` wraps every ``async def test_*`` automatically.

Behaviour covered:

  * ``dispatch_run`` calls the dispatcher with activation AND intent
    (I-HPC-1 + I-HPC-3).
  * The activation is forwarded read-only (I-HPC-2): object identity
    is preserved, no copy / mutation.
  * The intent is forwarded unchanged.
  * The returned ``RunHandle`` is exactly the dispatcher's return value.
  * ``dispatch_resume`` does not require the intent.
  * ``resolve_activation`` still works after the dispatch surface is
    wired (regression — see P1-09 contract).
  * Concurrent dispatch calls are independent (no shared mutable state).
  * The ``RunDispatcher`` protocol is ``@runtime_checkable``.
  * The facade does NOT import any transport module.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock

from lca.application.runtime.default_facade import (
    DefaultRuntimeFacade,
    RunDispatcher,
)
from lca.application.runtime.plan_resolution import (
    PlanResolutionResult,
    PlanResolutionService,
)
from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.facade import RunHandle
from lca.contracts.runtime.intent import RunIntent

# ── Helpers ───────────────────────────────────────────────────────────


def _intent(
    *,
    profile_path: str = "/abs/profiles/sample.yaml",
    user_text: str = "hello",
    session_id: str | None = "sess-dispatch",
) -> RunIntent:
    """Build a minimal valid ``RunIntent`` for facade dispatch tests."""
    return RunIntent(
        profile_path=profile_path,
        user_text=user_text,
        mode="solo",
        session_id=session_id,
        assistant_id=None,
        attachment_ids=(),
        prior_turns=(),
        execution_target="local",
        options={},
        surface="test",
    )


class StubDispatcher:
    """Structural :class:`RunDispatcher` implementation for tests.

    Records every call so tests can assert the facade forwarded the
    activation / intent verbatim. Returns ``RunHandle("run_test_<n>")``
    with a monotonic counter so each call yields a distinct handle.
    """

    def __init__(self) -> None:
        self.run_calls: list[tuple[SessionActivation, RunIntent]] = []
        self.resume_calls: list[tuple[SessionActivation, str]] = []
        self._counter: int = 0

    async def dispatch_run(
        self,
        activation: SessionActivation,
        intent: RunIntent,
    ) -> RunHandle:
        self._counter += 1
        # Capture the args BEFORE returning so assertions see the call.
        self.run_calls.append((activation, intent))
        return RunHandle(f"run_test_{self._counter}")

    async def dispatch_resume(
        self,
        activation: SessionActivation,
        run_id: str,
    ) -> RunHandle:
        self._counter += 1
        self.resume_calls.append((activation, run_id))
        return RunHandle(f"run_resume_{self._counter}")


class _MissingDispatchRun:
    """Concrete class missing ``dispatch_run`` — must not satisfy the protocol."""

    async def dispatch_resume(
        self,
        activation: SessionActivation,
        run_id: str,
    ) -> RunHandle:
        return RunHandle("noop")


def _plan_service() -> MagicMock:
    """Build a minimal :class:`PlanResolutionService` mock for the facade."""
    service = MagicMock(spec=PlanResolutionService)

    class _StubPlan:
        profile_path = "/abs/profiles/sample.yaml"

    service.resolve_refs.return_value = PlanResolutionResult(
        plan_ref="plan-D",
        graph_ref="graph-D",
        plugin_set_ref="plugin-set-D",
        compiled_plan=_StubPlan(),
    )
    return service


def _activation() -> SessionActivation:
    """Return a frozen ``SessionActivation`` produced by the facade."""
    return DefaultRuntimeFacade(_plan_service(), StubDispatcher()).resolve_activation(
        _intent(session_id="sess-1"),
    )


# ── dispatch_run forwarding ──────────────────────────────────────────


class TestDispatchRunForwarding:
    async def test_dispatch_run_calls_dispatcher(self) -> None:
        """The facade forwards ``dispatch_run`` to the injected dispatcher."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-X"))
        intent = _intent(session_id="sess-X")

        await facade.dispatch_run(activation, intent)

        assert len(dispatcher.run_calls) == 1

    async def test_dispatch_run_forwards_activation_readonly(self) -> None:
        """Activation identity is preserved across dispatch (I-HPC-2)."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-Y"))

        await facade.dispatch_run(activation, _intent(session_id="sess-Y"))

        forwarded_activation, _ = dispatcher.run_calls[0]
        # Same object — the facade MUST NOT copy or rebuild the activation.
        assert forwarded_activation is activation

    async def test_dispatch_run_forwards_intent(self) -> None:
        """The intent is forwarded verbatim (not re-resolved)."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))
        intent = _intent(
            user_text="custom user text",
            session_id="sess-1",
        )

        await facade.dispatch_run(activation, intent)

        _, forwarded_intent = dispatcher.run_calls[0]
        assert forwarded_intent is intent
        assert forwarded_intent.user_text == "custom user text"

    async def test_dispatch_run_returns_run_handle_from_dispatcher(self) -> None:
        """The facade returns exactly the dispatcher's ``RunHandle``."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        handle = await facade.dispatch_run(activation, _intent(session_id="sess-1"))

        assert handle == RunHandle("run_test_1")

    async def test_dispatch_run_handle_is_str(self) -> None:
        """``RunHandle`` is a NewType over ``str`` (erases at runtime)."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        handle = await facade.dispatch_run(activation, _intent(session_id="sess-1"))

        # NewType erases to ``str`` at runtime — see contracts tests.
        assert type(handle) is str


# ── dispatch_resume forwarding ──────────────────────────────────────


class TestDispatchResumeForwarding:
    async def test_dispatch_resume_calls_dispatcher(self) -> None:
        """``dispatch_resume`` forwards to the dispatcher with ``run_id``."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        await facade.dispatch_resume(activation, "run_123")

        assert dispatcher.resume_calls == [(activation, "run_123")]

    async def test_dispatch_resume_returns_run_handle(self) -> None:
        """``dispatch_resume`` returns the dispatcher's ``RunHandle``."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        handle = await facade.dispatch_resume(activation, "run_zzz")

        assert handle == RunHandle("run_resume_1")

    async def test_dispatch_resume_does_not_need_intent(self) -> None:
        """``dispatch_resume`` does not take an intent (only activation + run_id)."""
        sig = inspect.signature(DefaultRuntimeFacade.dispatch_resume)
        assert list(sig.parameters) == ["self", "activation", "run_id"]


# ── Regression: resolve_activation still works ──────────────────────


class TestResolveStillWorksAfterDispatchOverwrite:
    async def test_resolve_activation_still_works_after_dispatch_overwrite(self) -> None:
        """The facade created with a dispatcher still resolves correctly."""
        dispatcher = StubDispatcher()
        service = _plan_service()
        facade = DefaultRuntimeFacade(service, dispatcher)
        intent = _intent(session_id="sess-regression")

        activation = facade.resolve_activation(intent)

        # The facade produced an activation AND the plan service was called.
        assert isinstance(activation, SessionActivation)
        service.resolve_refs.assert_called_once_with(
            "/abs/profiles/sample.yaml",
            session_id="sess-regression",
        )
        # The dispatcher was NOT consulted during resolve.
        assert dispatcher.run_calls == []
        assert dispatcher.resume_calls == []


# ── Activation forwarding integrity ─────────────────────────────────


class TestActivationForwarding:
    async def test_dispatch_run_preserves_plan_ref(self) -> None:
        """``activation.plan_ref`` is exactly what the dispatcher sees."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        await facade.dispatch_run(activation, _intent(session_id="sess-1"))

        forwarded_activation, _ = dispatcher.run_calls[0]
        assert forwarded_activation.plan_ref == activation.plan_ref
        assert forwarded_activation.plan_ref == "plan-D"

    async def test_dispatch_run_preserves_activation_ref(self) -> None:
        """``activation.activation_ref`` is exactly what the dispatcher sees."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        await facade.dispatch_run(activation, _intent(session_id="sess-1"))

        forwarded_activation, _ = dispatcher.run_calls[0]
        assert forwarded_activation.activation_ref == activation.activation_ref


# ── No re-resolution during dispatch ────────────────────────────────


class TestNoReresolutionDuringDispatch:
    async def test_dispatch_run_does_not_call_resolve_again(self) -> None:
        """The facade MUST NOT re-resolve the intent during dispatch.

        Per ADR-0199 I-HPC-2 the activation is bound once; the dispatcher
        receives a frozen activation. The facade must not call
        ``PlanResolutionService.resolve_refs`` again as part of dispatch.
        """
        service = _plan_service()
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(service, dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))
        service.resolve_refs.reset_mock()

        await facade.dispatch_run(activation, _intent(session_id="sess-1"))

        service.resolve_refs.assert_not_called()


# ── Concurrency ──────────────────────────────────────────────────────


class TestConcurrency:
    async def test_concurrent_dispatches_are_independent(self) -> None:
        """Two concurrent ``dispatch_run`` calls produce two independent calls."""
        dispatcher = StubDispatcher()
        facade = DefaultRuntimeFacade(_plan_service(), dispatcher)
        activation = facade.resolve_activation(_intent(session_id="sess-1"))

        handle_a, handle_b = await asyncio.gather(
            facade.dispatch_run(activation, _intent(session_id="sess-1")),
            facade.dispatch_run(activation, _intent(session_id="sess-1")),
        )

        # Each call produced an independent dispatcher invocation.
        assert len(dispatcher.run_calls) == 2
        # The two handles are distinct (monotonic counter).
        assert handle_a != handle_b


# ── Protocol structural typing ──────────────────────────────────────


class TestRunDispatcherProtocol:
    def test_run_dispatcher_protocol_is_runtime_checkable(self) -> None:
        """``isinstance(StubDispatcher(), RunDispatcher)`` is True."""
        assert isinstance(StubDispatcher(), RunDispatcher)

    def test_concrete_dispatcher_must_implement_dispatch_run(self) -> None:
        """A class missing ``dispatch_run`` is NOT a ``RunDispatcher``."""
        assert not isinstance(_MissingDispatchRun(), RunDispatcher)

    def test_facade_satisfies_runtime_facade_protocol(self) -> None:
        """The facade is a ``RuntimeFacade`` (sanity)."""
        from lca.contracts.runtime.facade import RuntimeFacade

        assert isinstance(
            DefaultRuntimeFacade(_plan_service(), StubDispatcher()),
            RuntimeFacade,
        )


# ── Transport-isolation architectural rule ──────────────────────────


def test_facade_does_not_import_transport() -> None:
    """The facade module must not import any transport module.

    Per ADR-0199 §2.2.3 and P1-10: ``application/runtime/default_facade.py``
    is a pure Application Service — it must NOT depend on
    ``lca.plugins.transport`` (any submodule). The boundary is enforced
    by reading the module source and inspecting every import.
    """
    facade_path = (
        Path(__file__).resolve().parents[3]
        / "lca"
        / "application"
        / "runtime"
        / "default_facade.py"
    )
    assert facade_path.is_file(), facade_path

    tree = ast.parse(facade_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "lca.plugins.transport",
        "starlette",
        "fastapi",
    )
    offenders: list[tuple[str, str | None]] = []

    def _walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    for prefix in forbidden_prefixes:
                        if alias.name == prefix or alias.name.startswith(prefix + "."):
                            offenders.append((alias.name, None))
            elif isinstance(child, ast.ImportFrom):
                module = child.module or ""
                for prefix in forbidden_prefixes:
                    if module == prefix or module.startswith(prefix + "."):
                        offenders.append((module, None))
            _walk(child)

    _walk(tree)

    assert offenders == [], f"{facade_path} imports forbidden transport modules: {offenders!r}"
