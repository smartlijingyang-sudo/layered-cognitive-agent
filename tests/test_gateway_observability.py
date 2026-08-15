"""Gateway Run Hub 走 create_observability：Langfuse 是读者，不是平行总线。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

import pytest

from gateway.runs.execute import create_hub_for_session
from gateway.runs.live import LiveTail
from gateway.runs.session import RunSession
from lca.layer0_infra.observability.settings import ObservabilitySettings, resolve_backend_names


def test_resolve_backend_names_auto_includes_langfuse() -> None:
    assert resolve_backend_names(
        "console",
        include_langfuse=None,
        public_key="pk-test",
        secret_key="sk-test",  # noqa: S106
    ) == ["console", "langfuse"]


def test_resolve_backend_names_false_strips() -> None:
    assert "langfuse" not in resolve_backend_names(
        "console+langfuse",
        include_langfuse=False,
        public_key="pk-test",
        secret_key="sk-test",  # noqa: S106
    )


class _FakeLangfuse:
    last_kwargs: ClassVar[dict] = {}

    def __init__(self, **kwargs: object) -> None:
        _FakeLangfuse.last_kwargs = dict(kwargs)

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def test_create_hub_for_session_attaches_langfuse_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    langfuse_mod = pytest.importorskip("langfuse")
    monkeypatch.setattr(langfuse_mod, "Langfuse", _FakeLangfuse)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LCA_OBS_BACKENDS", "console")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:9")
    session = RunSession(
        run_id="run_test",
        trace_id="trace_test",
        jsonl_path=tmp_path / "run.jsonl",
        tail=LiveTail(),
        question="q",
        user_text="q",
        mode="solo",
    )
    hub = create_hub_for_session(session, settings=ObservabilitySettings())
    try:
        assert len(hub.bridges) == 1
        assert "tracer_provider" in _FakeLangfuse.last_kwargs
        from lca.contracts.models.observability.journal import AgentRunStarted
        from lca.layer0_infra.observability import bind, record

        with bind(hub):
            record(AgentRunStarted(agent_role="助手", objective="probe"))
        assert session.tail.buffer_size >= 1
    finally:
        hub.close()


def test_release_closes_journal_before_export_dispose() -> None:
    closed: list[str] = []

    class _Bridge:
        def attach(self, hub: object) -> None:
            del hub

        def flush(self) -> None:
            return None

        def close(self) -> None:
            closed.append("bridge")

    class _Probe:
        def on_event(self, stamped: object) -> None:
            del stamped

        def flush(self) -> None:
            return None

        def close(self) -> None:
            closed.append("journal")

    from lca.layer0_infra.observability.hub import ObservabilityHub

    hub = ObservabilityHub([], journal_projectors=(_Probe(),))
    hub.attach_bridge(_Bridge())
    hub.release()
    assert closed == ["journal"]
    hub.dispose()
    assert closed == ["journal", "bridge"]


class _HangExportHub:
    released = False

    class _MockStore:
        events: tuple = ()

    store = _MockStore()

    def release(self) -> None:
        self.released = True

    def dispose(self) -> None:
        time.sleep(5)


@pytest.mark.asyncio
async def test_finalize_releases_live_when_export_hangs(tmp_path: Path) -> None:
    import time as time_mod

    from gateway.runs.execute import finalize
    from gateway.runs.live import LiveTail
    from gateway.runs.session import RunRegistry, RunSession

    registry = RunRegistry()
    hub = _HangExportHub()
    session = RunSession(
        run_id="run_hang",
        trace_id="trace_hang",
        jsonl_path=tmp_path / "run_hang.jsonl",
        tail=LiveTail(),
        question="q",
        user_text="q",
        mode="solo",
        hub=hub,  # type: ignore[arg-type]
    )
    registry.put(session)
    started = time_mod.monotonic()
    await finalize(session, registry, None, True)
    elapsed = time_mod.monotonic() - started
    assert hub.released
    assert elapsed < 8
