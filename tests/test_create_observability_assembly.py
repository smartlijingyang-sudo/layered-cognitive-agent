"""create_observability 装配：run 级投影器 + 可选 Langfuse 不阻断。"""

from __future__ import annotations

from lca.contracts.models.observability.journal import AgentRunStarted, StampedEvent
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability import bind, create_observability, record
from lca.layer0_infra.observability.settings import ObservabilitySettings


class _Probe(JournalProjector):
    def __init__(self) -> None:
        self.types: list[str] = []

    def on_event(self, stamped: StampedEvent) -> None:
        self.types.append(type(stamped.event).__name__)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_extra_projectors_see_journal_events() -> None:
    probe = _Probe()
    hub = create_observability(
        "console",
        settings=ObservabilitySettings(backends="console"),
        extra_projectors=(probe,),
    )
    try:
        with bind(hub):
            record(AgentRunStarted(agent_role="助手", objective="hi"))
        assert "AgentRunStarted" in probe.types
    finally:
        hub.close()


def test_unavailable_langfuse_is_skipped_not_fatal(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LCA_OBS_LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LCA_OBS_LANGFUSE_SECRET_KEY", "")
    cfg = ObservabilitySettings(
        backends="console+langfuse",
        langfuse_public_key="",
        langfuse_secret_key="",
    )
    probe = _Probe()
    hub = create_observability(
        "console+langfuse",
        settings=cfg,
        extra_projectors=(probe,),
    )
    try:
        assert hub.bridges == ()
        with bind(hub):
            record(AgentRunStarted(agent_role="助手", objective="still-recorded"))
        assert "AgentRunStarted" in probe.types
    finally:
        hub.close()
