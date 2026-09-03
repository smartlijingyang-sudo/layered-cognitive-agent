"""ADR-0180 试点：JournalSink (sink plugin) 测试。"""

from __future__ import annotations

import io

from lca.contracts.event import Category, TeamDelegationCacheHit
from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca.plugins.events.sinks.journal.sink import EventRecord, JournalSink
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca_kernel.events import EventMechanism
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry


def test_journal_sink_records_events() -> None:
    sink = JournalSink()
    from lca_kernel.events.mechanism import EventRef

    payload = TeamDelegationCacheHit(callee_role="x", subtask="y", step=0)
    ref = EventRef(event_id="evt_1", category="team.delegation.cache_hit", trace_id="", ts=0.0)
    sink.on_event(payload, ref)
    assert len(sink.records) == 1
    record = sink.records[0]
    assert isinstance(record, EventRecord)
    assert record.category == Category.TEAM_DELEGATION_CACHE_HIT.value


def test_journal_sink_in_yaml_subscribers_whitelist() -> None:
    """JournalSink 在 yaml subscribers → can_subscribe 通过 → mechanism.subscribe 不抛。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    mechanism = EventMechanism(registry)
    mechanism.subscribe(
        plugin=JournalSink,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        callback=lambda p, r: None,
    )


def test_console_projector_subscriber_renders_to_stdout() -> None:
    """ConsoleProjectorSubscriber 收到 payload 后渲染到 stdout。"""
    stream = io.StringIO()

    subscriber = ConsoleProjectorSubscriber(stream=stream)
    from lca_kernel.events.mechanism import EventRef

    payload = TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3)
    ref = EventRef(event_id="evt_1", category="team.delegation.cache_hit", trace_id="", ts=0.0)
    subscriber.on_event(payload, ref)
    output = stream.getvalue()
    assert "analyst" in output
    assert "幂等短路" in output


def test_end_to_end_publisher_to_subscribers() -> None:
    """端到端：publisher plugin 发 → journal sink + console projector 都收到。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    mechanism = EventMechanism(registry)

    journal = JournalSink()
    console_stream = io.StringIO()

    console = ConsoleProjectorSubscriber(stream=console_stream)

    mechanism.subscribe(
        plugin=JournalSink,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        callback=journal.on_event,
    )
    mechanism.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        callback=console.on_event,
    )

    mechanism.send(
        TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3),
        plugin=DelegationCachePlugin,
    )

    assert len(journal.records) == 1
    assert "analyst" in console_stream.getvalue()
