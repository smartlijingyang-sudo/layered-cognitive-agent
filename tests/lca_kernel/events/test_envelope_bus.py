"""EnvelopeBus 投递契约测试。

覆盖:
- publish 返回 6 字段 :class:`EventRef`,两项投递事实在返回前填齐
- publish 抵达已 subscribe 的 consumer 与已 mount_sink 的落盘后端
- 无装配时 ``default()`` 自建的实例具备完整投递面

计数器四值、零落盘策略与 ``delivery_snapshot`` 拷贝语义见
``tests/lca_kernel/events/test_bus_delivery_receipt.py``。
"""

from __future__ import annotations

from lca.contracts.event import Category, EventPayload
from lca_kernel.events import (
    EnvelopeBus,
    EnvelopeRef,
    EventRef,
    TeamDelegationCacheHit,
)
from lca_kernel.events.spine.runtime import SpineEventRecord
from lca_kernel.events.test.catalog import build_test_bus

# ── 公共 helpers ─────────────────────────────────────────────────────────


def _authorized_payload() -> EventPayload:
    """yaml 试点白名单内的可用 payload。"""
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


def _authorized_producer() -> type:
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


def _authorized_subscriber() -> type:
    from lca.plugins.events.sinks.spine_file_sink.sink import SpineFileSink

    return SpineFileSink


class _RecordingSink:
    """最小 SinkBackend:只收集 record。"""

    def __init__(self) -> None:
        self.records: list[SpineEventRecord] = []

    def append(self, record: SpineEventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None: ...

    def close(self) -> None: ...


# ── 回执 ────────────────────────────────────────────────────────────────


class TestPublishReceipt:
    def test_publish_returns_six_field_event_ref(self) -> None:
        """publish 返回 EventRef;6 字段就位且类型正确。"""
        bus = build_test_bus()
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert isinstance(ref, EventRef)
        assert isinstance(ref, EnvelopeRef)
        assert ref.event_id and isinstance(ref.event_id, str)
        assert ref.category == "team.delegation.cache_hit"
        assert ref.trace_id and isinstance(ref.trace_id, str)
        assert isinstance(ref.ts, float)
        assert isinstance(ref.persisted, bool)
        assert isinstance(ref.subscriber_count, int)

    def test_receipt_reports_zero_delivery_without_sink_or_subscriber(self) -> None:
        """零 sink + 零订阅者:persisted False、subscriber_count 0。"""
        bus = build_test_bus()
        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())
        assert ref.persisted is False
        assert ref.subscriber_count == 0

    def test_receipt_fills_delivery_facts_before_return(self) -> None:
        """投递事实在 publish 返回前同步填齐,生产者读到既成事实。"""
        bus = build_test_bus()
        sink = _RecordingSink()
        bus.mount_sink("receipt-probe", sink)
        seen: list[EventRef] = []
        bus.subscribe(
            plugin=_authorized_subscriber(),
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, r: seen.append(r),
        )

        ref = bus.publish(_authorized_payload(), producer=_authorized_producer())

        assert ref.persisted is True
        assert ref.subscriber_count == 1
        assert len(sink.records) == 1
        assert sink.records[0].to_dict()["event_id"] == ref.event_id
        # consumer 回调收到的回执与返回给生产者的是同一份投递事实
        assert len(seen) == 1
        assert seen[0].event_id == ref.event_id
        assert seen[0].persisted is True


# ── 进程单例 ────────────────────────────────────────────────────────────


class TestProcessSingleton:
    def test_default_without_boot_has_full_delivery_surface(self) -> None:
        """无装配时 ``default()`` 自建的实例具备完整投递面。

        单例槽是进程级共享变量:装配路径(``lca.events.bus`` manifest 的
        ``setup_bus``)经 ``set_default`` 注入,未装配时 ``default()`` 按
        config 目录自建。自建实例必须与装配实例同形 —— 缺 ``subscribe``
        或 ``mount_sink`` 的实例会接受 publish、返回回执,却零落盘零派发。
        """
        EnvelopeBus.reset_singleton()
        try:
            bus = EnvelopeBus.default()
            assert isinstance(bus, EnvelopeBus)
            for name in (
                "publish",
                "subscribe",
                "subscribe_self_observation",
                "mount_sink",
                "register_pipeline",
                "delivery_snapshot",
                "configure_delivery_policy",
            ):
                assert callable(getattr(bus, name, None)), f"default() 实例缺 {name}"
            # 投递面可用:mount_sink 接受装载(无鉴权门,直接落 _sinks)
            bus.mount_sink("singleton-probe", _RecordingSink())
            assert EnvelopeBus.default() is bus, "单例槽必须返回同一实例"
        finally:
            EnvelopeBus.reset_singleton()
