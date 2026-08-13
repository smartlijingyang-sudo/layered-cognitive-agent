"""Gateway Run Hub 走 create_observability：Langfuse 是读者，不是平行总线。"""

from __future__ import annotations

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
