"""HTTP carrier grant binder (ADR-0292 §10 P3).

The HTTP ``POST /runs`` path skips ``DefaultRuntimeFacade.resolve_activation``,
so assistant-bound runs used to execute with no ambient TrustEnvelope. Any
tool declaring a ``required_grant`` (``memory_add`` → ``profile.revise``) was
refused at ``act.authorize`` and the run failed. These tests lock the binder:
``RunLifecycleCoordinator.execute`` binds the assistant's grants ∪
``RULE_DEFAULTS`` when no envelope is already bound.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

# isort: off
# Importing the terminal commands first initialises the execute package in the
# app's order and avoids the lifecycle<->execute circular import.
from lca.infrastructure.assistant.io import assistant_trust_envelope
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession
# isort: on


def _write_grants(home: Path, assistant_id: str, grants: list[str]) -> None:
    assistant_dir = home / "assistants" / assistant_id
    assistant_dir.mkdir(parents=True, exist_ok=True)
    (assistant_dir / "grants.yaml").write_text(
        "grants:\n" + "".join(f"  - {g}\n" for g in grants),
        encoding="utf-8",
    )


def test_assistant_trust_envelope_merges_assistant_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    _write_grants(tmp_path, "asst_test", ["profile.revise", "workspace.write"])

    envelope = assistant_trust_envelope("asst_test")

    assert envelope.grants("profile.revise") is True
    assert envelope.grants("workspace.write") is True
    # RULE_DEFAULTS 保证 envelope 非空且 HITL/平台基础 grant 可用。
    assert envelope.grants("platform.basic") is True
    assert envelope.grants("hitl.interact") is True
    # 未绑定的 assistant_id → 只有 RULE_DEFAULTS（fail-closed）。
    assert assistant_trust_envelope("").grants("profile.revise") is False


class _RegistryStub:
    def __init__(self, session: RunSession) -> None:
        self._session = session

    def get(self, run_id: str) -> RunSession | None:
        return self._session if run_id == self._session.run_id else None

    def mark_paused(self, session: RunSession) -> None:  # pragma: no cover
        return None


def _session(assistant_id: str) -> RunSession:
    return RunSession(
        run_id="run-grant-binder",
        trace_id="trace-grant-binder",
        spine_path=Path("traces/grant-binder.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="记住我的名字",
        user_text="记住我的名字",
        mode="solo",
        assistant_id=assistant_id,
    )


def test_execute_binds_assistant_envelope_when_unbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP run 未绑定 envelope 时，execute 补绑 assistant grants。"""
    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    _write_grants(tmp_path, "asst_test", ["profile.revise"])
    session = _session("asst_test")

    seen: dict[str, object] = {}
    from lca.contracts.runtime.trust import get_current_trust_envelope

    class _FakeDriver:
        async def execute(self, *args: object, **kwargs: object) -> SimpleNamespace:
            seen["envelope"] = get_current_trust_envelope()
            return SimpleNamespace(success=True)

    class _FakePrepared:
        workspace = object()
        bindings = object()
        run_context = object()
        driver = _FakeDriver()

    class _FakeEnvironment:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def prepare(self) -> _AsyncCM:
            return _AsyncCM(_FakePrepared())

    class _AsyncCM:
        def __init__(self, prepared: _FakePrepared) -> None:
            self._prepared = prepared

        async def __aenter__(self) -> _FakePrepared:
            return self._prepared

        async def __aexit__(self, *exc: object) -> None:
            return None

    import lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "ensure_session_hub", lambda *a, **k: object())
    monkeypatch.setattr(lifecycle, "bind_event_bridge", lambda *a, **k: "token")
    monkeypatch.setattr(lifecycle, "unbind_event_bridge", lambda *a, **k: None)
    import lca.loop.transport as loop_transport

    monkeypatch.setattr(loop_transport, "emit_kernel_run_start", lambda **k: None)
    monkeypatch.setattr(loop_transport, "emit_kernel_run_stop", lambda **k: None)
    monkeypatch.setattr(lifecycle, "RunExecutionEnvironment", _FakeEnvironment)

    async def _noop_finish(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        lifecycle.RunLifecycleCoordinator,
        "_finish_or_pause",
        staticmethod(_noop_finish),
    )

    coordinator = lifecycle.RunLifecycleCoordinator(_RegistryStub(session))  # type: ignore[arg-type]
    coordinator._outcomes.apply_driver = lambda *a, **k: None  # type: ignore[method-assign]

    async def _scenario() -> None:
        await coordinator.execute(
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
            ctx=object(),
        )

    asyncio.run(_scenario())

    envelope = seen["envelope"]
    assert envelope is not None
    assert envelope.grants("profile.revise") is True


def test_execute_keeps_existing_envelope_when_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """facade/CLI 已绑定 envelope 时，execute 不覆盖。"""
    from lca.contracts.runtime.trust import (
        PluginOrigin,
        TrustEnvelope,
        get_current_trust_envelope,
        trust_envelope_scope,
    )

    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    _write_grants(tmp_path, "asst_test", ["workspace.write"])
    session = _session("asst_test")

    seen: dict[str, object] = {}

    class _FakeDriver:
        async def execute(self, *args: object, **kwargs: object) -> SimpleNamespace:
            seen["envelope"] = get_current_trust_envelope()
            return SimpleNamespace(success=True)

    class _FakePrepared:
        workspace = object()
        bindings = object()
        run_context = object()
        driver = _FakeDriver()

    class _FakeEnvironment:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def prepare(self) -> _AsyncCM:
            return _AsyncCM(_FakePrepared())

    class _AsyncCM:
        def __init__(self, prepared: _FakePrepared) -> None:
            self._prepared = prepared

        async def __aenter__(self) -> _FakePrepared:
            return self._prepared

        async def __aexit__(self, *exc: object) -> None:
            return None

    import lca.plugins.transport.webserver.carrier.runs.lifecycle.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "ensure_session_hub", lambda *a, **k: object())
    monkeypatch.setattr(lifecycle, "bind_event_bridge", lambda *a, **k: "token")
    monkeypatch.setattr(lifecycle, "unbind_event_bridge", lambda *a, **k: None)
    import lca.loop.transport as loop_transport

    monkeypatch.setattr(loop_transport, "emit_kernel_run_start", lambda **k: None)
    monkeypatch.setattr(loop_transport, "emit_kernel_run_stop", lambda **k: None)
    monkeypatch.setattr(lifecycle, "RunExecutionEnvironment", _FakeEnvironment)

    async def _noop_finish(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        lifecycle.RunLifecycleCoordinator,
        "_finish_or_pause",
        staticmethod(_noop_finish),
    )

    coordinator = lifecycle.RunLifecycleCoordinator(_RegistryStub(session))  # type: ignore[arg-type]
    coordinator._outcomes.apply_driver = lambda *a, **k: None  # type: ignore[method-assign]

    outer_envelope = TrustEnvelope(
        origins=(
            PluginOrigin(
                source="bundled",
                trust="core",
                enabled_by="test",
                discovered_at="test",
            ),
        ),
        granted_privileges=frozenset({"workspace.write", "custom.grant"}),
    )

    async def _scenario() -> None:
        with trust_envelope_scope(outer_envelope):
            await coordinator.execute(
                run_id=session.run_id,
                question=session.question,
                mode=session.mode,
                ctx=object(),
            )

    asyncio.run(_scenario())

    envelope = seen["envelope"]
    assert envelope is outer_envelope
    assert envelope.grants("custom.grant") is True
    # 已绑定时不加载 assistant grants。
    assert envelope.grants("profile.revise") is False
