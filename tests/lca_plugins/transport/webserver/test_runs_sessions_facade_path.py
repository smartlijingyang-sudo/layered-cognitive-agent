"""HTTP ``create_run`` dual-path tests — RuntimeFacade vs Legacy RunPort (ADR-0199 P1-11).

Per ADR-0199 §12.2 the carrier exposes an env-gated switch:

- Default (``LCA_RUNTIME_FACADE != "0"``): dispatches via ``RuntimeFacade``.
- Legacy (``LCA_RUNTIME_FACADE == "0"``): keeps the old ``RunPort`` path for COMPAT.

The tests exercise ``create_run`` directly with a hand-rolled Starlette
``Request`` (the same pattern used by
``tests/plugins/assistant/test_run_binding.py::_request_with_catalog``)
and monkeypatch:

- ``command_endpoints.resolve_profile_mode`` so the decode step does not
  probe the live capability registry.
- ``command_endpoints._runtime_facade_of`` so the facade path is
  deterministic without a real ``PlanResolutionService``.
- ``command_endpoints._run_port_of`` so the legacy path returns a stub
  receipt.

Plus a unit test for :class:`LegacyRunDispatcher` exercising the
``RunIntent → RunRequest → RunReceipt → RunHandle` translation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.facade import RunHandle, RuntimeFacade
from lca.contracts.runtime.intent import RunIntent
from lca.contracts.runtime.trust import EMPTY_TRUST_ENVELOPE
from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    create_run,
)
from lca.plugins.transport.webserver.handlers.runs.api.legacy_dispatcher_adapter import (
    LegacyRunDispatcher,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
    RunReceipt,
    RunRequest,
)

# ── Fakes / stubs ───────────────────────────────────────────────────


class _StubRunPort:
    """Stand-in for the production ``RunPort`` (legacy path).

    Records every call so tests can assert the handler routed through
    the legacy code path. ``accepted`` controls whether the returned
    receipt carries a rejection_reason.
    """

    def __init__(self, *, accepted: bool = True, run_id: str = "run_legacy") -> None:
        self.accepted = accepted
        self.run_id = run_id
        self.calls: list[RunRequest] = []

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt:
        self.calls.append(request)
        return RunReceipt(
            run_id=self.run_id,
            trace_id="trace_legacy",
            accepted=self.accepted,
            rejection_reason=None if self.accepted else "stub rejection",
        )


class _StubFacade(RuntimeFacade):
    """Stand-in for the production ``RuntimeFacade`` (facade path).

    Implements the duck-typed dispatch_run signature the handler calls:
    ``dispatch_run(activation, intent)``. Records every call so tests
    can assert the handler routed through the facade.
    """

    def __init__(self, *, run_id: str = "run_facade") -> None:
        self.run_id = run_id
        self.resolve_calls: list[RunIntent] = []
        self.dispatch_calls: list[tuple[SessionActivation, RunIntent]] = []

    def resolve_activation(self, intent: RunIntent) -> SessionActivation:
        self.resolve_calls.append(intent)
        return SessionActivation(
            activation_ref="act_" + self.run_id,
            plan_ref="plan_ref",
            graph_ref="graph_ref",
            plugin_set_ref="plugin_set_ref",
            profile_path=intent.profile_path,
            session_id="sess_stub",
            trust_envelope=EMPTY_TRUST_ENVELOPE,
            compiled_plan=None,
        )

    async def dispatch_run(self, activation: Any, intent: Any) -> RunHandle:
        # The handler passes both activation and intent (legacy dispatcher
        # contract). This stub ignores intent and returns the run_id.
        self.dispatch_calls.append((activation, intent))  # type: ignore[arg-type]
        return RunHandle(self.run_id)

    async def dispatch_resume(self, activation: Any, run_id: str) -> RunHandle:
        raise NotImplementedError("StubFacade does not implement dispatch_resume")


# ── Request factory ────────────────────────────────────────────────


def _request(
    *,
    body: dict[str, Any],
    app_state: Any = None,
) -> Request:
    """Build a Starlette ``Request`` whose ``.json()`` yields ``body``."""

    if app_state is None:
        app_state = type("State", (), {})()

    app = Starlette()
    app.state = app_state  # type: ignore[assignment]
    body_bytes = json.dumps(body).encode("utf-8")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/runs",
        "headers": [(b"content-type", b"application/json")],
        "app": app,
    }
    return Request(scope, receive=receive)


def _resolve_mode_stub(ctx: Any, mode: str) -> str:
    """Stub for ``resolve_profile_mode`` — bypasses the capability probe."""
    return mode or "solo"


# ── Fixture: register a temp file_store on app.state ────────────────


@pytest.fixture
def file_store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


@pytest.fixture(autouse=True)
def _patch_resolve_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``resolve_profile_mode`` to a no-op stub for the decode step."""
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(command_endpoints, "resolve_profile_mode", _resolve_mode_stub)


# ── Dual-path env-var switch ────────────────────────────────────────


class TestEnvGatedSwitch:
    @pytest.mark.asyncio
    async def test_default_path_uses_facade(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        """Env unset → handler dispatches via the RuntimeFacade."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.delenv("LCA_RUNTIME_FACADE", raising=False)
        facade = _StubFacade()
        port = _StubRunPort()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202
        assert len(facade.dispatch_calls) == 1
        assert port.calls == []

    @pytest.mark.asyncio
    async def test_explicit_off_flag_uses_legacy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        """Env ``LCA_RUNTIME_FACADE=0`` → handler uses the RunPort path."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.setenv("LCA_RUNTIME_FACADE", "0")
        port = _StubRunPort()
        facade = _StubFacade()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202
        assert len(port.calls) == 1
        assert facade.dispatch_calls == []

    @pytest.mark.asyncio
    async def test_explicit_on_flag_uses_facade(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        """Env ``LCA_RUNTIME_FACADE=1`` → facade path is taken."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.setenv("LCA_RUNTIME_FACADE", "1")
        facade = _StubFacade()
        port = _StubRunPort()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202
        assert len(facade.dispatch_calls) == 1
        assert port.calls == []


# ── Response shape ──────────────────────────────────────────────────


class TestResponseShape:
    @pytest.mark.asyncio
    async def test_facade_path_returns_run_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.delenv("LCA_RUNTIME_FACADE", raising=False)
        facade = _StubFacade(run_id="run_xyz")
        port = _StubRunPort()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        body = json.loads(response.body)
        assert body["run_id"] == "run_xyz"

    @pytest.mark.asyncio
    async def test_facade_path_returns_202(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.delenv("LCA_RUNTIME_FACADE", raising=False)
        facade = _StubFacade()
        port = _StubRunPort()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_legacy_path_returns_run_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.setenv("LCA_RUNTIME_FACADE", "0")
        port = _StubRunPort(run_id="run_legacy")
        facade = _StubFacade()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        body = json.loads(response.body)
        assert body["run_id"] == "run_legacy"

    @pytest.mark.asyncio
    async def test_legacy_path_still_returns_202(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.setenv("LCA_RUNTIME_FACADE", "0")
        port = _StubRunPort()
        facade = _StubFacade()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202


# ── 4xx error handling survives both paths ──────────────────────────


class TestErrorPassThrough:
    @pytest.mark.asyncio
    async def test_4xx_errors_still_pass_through_facade_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        """decode error → 400 regardless of the env-var setting."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.delenv("LCA_RUNTIME_FACADE", raising=False)
        facade = _StubFacade()
        port = _StubRunPort()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        # Empty messages → decode_create_run returns a JSONResponse 400.
        request = _request(body={"messages": []}, app_state=state)
        response = await create_run(request)
        assert response.status_code == 400
        assert facade.dispatch_calls == []
        assert port.calls == []

    @pytest.mark.asyncio
    async def test_4xx_errors_still_pass_through_legacy_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        file_store: LocalFileStore,
    ) -> None:
        """decode error → 400 on the legacy path too."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        monkeypatch.setenv("LCA_RUNTIME_FACADE", "0")
        port = _StubRunPort()
        facade = _StubFacade()
        monkeypatch.setattr(command_endpoints, "_runtime_facade_of", lambda req: facade)

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(body={"messages": []}, app_state=state)
        response = await create_run(request)
        assert response.status_code == 400
        assert facade.dispatch_calls == []
        assert port.calls == []


# ── LegacyRunDispatcher adapter unit tests ──────────────────────────


def _intent(**overrides: Any) -> RunIntent:
    """Build a minimal ``RunIntent`` for adapter tests."""
    base: dict[str, Any] = {
        "profile_path": "web-standard",
        "user_text": "hello",
        "mode": "solo",
        "session_id": None,
        "assistant_id": None,
        "attachment_ids": (),
        "prior_turns": (),
        "execution_target": "",
        "options": {},
        "surface": "http",
        "device_id": "",
    }
    base.update(overrides)
    return RunIntent(**base)


def _activation() -> SessionActivation:
    return SessionActivation(
        activation_ref="act_test",
        plan_ref="plan_ref",
        graph_ref="graph_ref",
        plugin_set_ref="plugin_set_ref",
        profile_path="web-standard",
        session_id="sess_test",
        trust_envelope=EMPTY_TRUST_ENVELOPE,
        compiled_plan=None,
    )


class TestLegacyRunDispatcher:
    @pytest.mark.asyncio
    async def test_adapter_module_adapts_intent_to_request(self) -> None:
        """``dispatch_run`` translates the intent into a ``RunRequest`` and
        forwards it to the legacy ``RunPort.create_and_dispatch``."""
        port = _StubRunPort(run_id="run_from_intent")
        dispatcher = LegacyRunDispatcher(port)  # type: ignore[arg-type]

        intent = _intent(user_text="ping", attachment_ids=("att-1",), device_id="dev-x")
        activation = _activation()

        handle = await dispatcher.dispatch_run(activation, intent)

        # ``RunHandle`` is a ``NewType`` over ``str``; isinstance check uses str.
        assert isinstance(handle, str)
        assert str(handle) == "run_from_intent"
        assert len(port.calls) == 1
        forwarded: RunRequest = port.calls[0]
        assert forwarded.user_text == "ping"
        assert forwarded.profile == "web-standard"
        assert forwarded.attachment_ids == ("att-1",)
        assert forwarded.device_id == "dev-x"

    @pytest.mark.asyncio
    async def test_adapter_rejects_failed_receipt(self) -> None:
        """A ``RunReceipt(accepted=False)`` surfaces as ``RuntimeError``."""
        port = _StubRunPort(accepted=False)
        dispatcher = LegacyRunDispatcher(port)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="carrier rejected run"):
            await dispatcher.dispatch_run(_activation(), _intent())

    @pytest.mark.asyncio
    async def test_adapter_resume_raises_not_implemented(self) -> None:
        """``dispatch_resume`` is a COMPAT marker until P1-13 wires it up."""
        port = _StubRunPort()
        dispatcher = LegacyRunDispatcher(port)  # type: ignore[arg-type]

        with pytest.raises(NotImplementedError, match="P1-13"):
            await dispatcher.dispatch_resume(_activation(), "run_xyz")


# ── COMPAT template present in handler source ────────────────────────


class TestCompatTemplate:
    def test_compat_comment_present(self) -> None:
        """The handler source must carry the ADR-0199 COMPAT marker."""
        from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

        source = Path(command_endpoints.__file__).read_text(encoding="utf-8")
        assert "COMPAT(owner: ADR-0199" in source
        assert "delete_when" in source
        assert "forbidden_new_usage" in source
        assert "handler-internal resolve_profile" in source
