"""ADR-0180 试点：JournalSink (sink plugin) 测试 / ADR-0183 PR-7。"""

from __future__ import annotations

import io

from lca.contracts.event import Category, TeamDelegationCacheHit
from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca.plugins.events.sinks.journal.sink import EventRecord, JournalSink
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca_kernel.events.bus import EventBus, EventRef
from lca_kernel.events.hooks import FailureSemantics
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


def test_journal_sink_records_events() -> None:
    sink = JournalSink()
    payload = TeamDelegationCacheHit(callee_role="x", subtask="y", step=0)
    ref = EventRef(event_id="evt_1", category="team.delegation.cache_hit", trace_id="", ts=0.0)
    sink.on_event(payload, ref)
    assert len(sink.records) == 1
    record = sink.records[0]
    assert isinstance(record, EventRecord)
    assert record.category == Category.TEAM_DELEGATION_CACHE_HIT.value


def test_journal_sink_in_yaml_subscribers_whitelist() -> None:
    """JournalSink 在 yaml subscribers → can_subscribe 通过 → bus.subscribe 不抛。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    bus = EventBus(registry)
    bus.subscribe(
        plugin=JournalSink,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=lambda p, r: None,
    )


def test_console_projector_subscriber_renders_to_stdout() -> None:
    """ConsoleProjectorSubscriber 收到 payload 后渲染到 stdout。"""
    stream = io.StringIO()

    subscriber = ConsoleProjectorSubscriber(stream=stream)
    payload = TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3)
    ref = EventRef(event_id="evt_1", category="team.delegation.cache_hit", trace_id="", ts=0.0)
    subscriber.on_event(payload, ref)
    output = stream.getvalue()
    assert "analyst" in output
    assert "幂等短路" in output


def test_end_to_end_publisher_to_subscribers() -> None:
    """端到端：publisher plugin 发 → journal sink + console projector 都收到。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    bus = EventBus(registry)
    EventBus.set_default(bus)

    journal = JournalSink()
    console_stream = io.StringIO()

    console = ConsoleProjectorSubscriber(stream=console_stream)

    bus.subscribe(
        plugin=JournalSink,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=journal.on_event,
        failure=FailureSemantics.FAIL_FAST,
    )
    bus.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=console.on_event,
        failure=FailureSemantics.CONTAINED,
    )

    try:
        bus.publish(
            TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3),
            producer=DelegationCachePlugin,
        )
    finally:
        EventBus.set_default(None)

    assert len(journal.records) == 1
    assert "analyst" in console_stream.getvalue()
