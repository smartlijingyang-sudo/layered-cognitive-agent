"""ADR-0184 PR-A 投递回执 + 机制计数器 + I2 零落盘策略测试。

覆盖:
- EventRef 回执字段两态(有 / 无 sink)与必填契约(无默认值)
- 计数器四值 published / persisted / delivered / dropped 正确性,
  含 dropped 两种定义:未落盘;落盘但零派发且注册表声明了订阅者
- 零落盘策略:strict=True 持久 category 抛 EventNoSinkError;
  strict=False 降级为 dropped 计数 + error 日志
- delivery_snapshot() 形状与拷贝语义
- lca-ops events-delivery 命令输出(--json / --category / 人类视图)
"""

from __future__ import annotations

import json

import pytest

from lca.contracts.event import Category, EventPayload, Plane, TeamDelegationCacheHit
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.bus import DeliveryPolicy, EventBus, EventRef
from lca_kernel.events.errors import EventNoSinkError
from lca_kernel.events.payloads_spine import SpineEventPayload
from lca_kernel.events.registry import EventRegistry, EventSpec
from lca_kernel.events.spine_runtime import SpineEventRecord

# ── helpers ──────────────────────────────────────────────────────────────


class _RecordingSink:
    """SinkBackend 测试实现:只收集 record。"""

    def __init__(self) -> None:
        self.records: list[SpineEventRecord] = []

    def append(self, record: SpineEventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None: ...

    def close(self) -> None: ...


@pytest.fixture
def team_producer() -> type:
    """yaml publishers 白名单内的 team.delegation.cache_hit 发送方。"""
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


@pytest.fixture
def team_payload() -> TeamDelegationCacheHit:
    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


@pytest.fixture
def subscriber_plugin() -> type:
    """team. 前缀 consumer_rules 授权的订阅方。"""
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )

    return ConsoleProjectorSubscriber


@pytest.fixture
def spine_producer() -> type:
    """yaml publishers 白名单内的持久类(observability)发送方。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    return ReflectorClass


@pytest.fixture
def spine_payload() -> SpineEventPayload:
    return SpineEventPayload(
        execution_point="brain.think.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


def _counts(bus: EventBus[EventPayload], category: str) -> dict[str, int]:
    return bus.delivery_snapshot()[category]


# ── 回执字段 ─────────────────────────────────────────────────────────────


class TestDeliveryReceipt:
    def test_receipt_without_sink(self, bus, team_producer, team_payload) -> None:
        """无 sink 无订阅:persisted=False,subscriber_count=0。"""
        ref = bus.publish(team_payload, producer=team_producer)
        assert ref.persisted is False
        assert ref.subscriber_count == 0

    def test_receipt_with_sink_and_subscriber(
        self, bus, team_producer, team_payload, subscriber_plugin
    ) -> None:
        """有 sink + 有订阅:两个回执字段反映 S3 / S4 事实。"""
        sink = _RecordingSink()
        bus.mount_sink("rec", sink)
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        ref = bus.publish(team_payload, producer=team_producer)
        assert ref.persisted is True
        assert ref.subscriber_count == 1
        assert len(sink.records) == 1
        assert sink.records[0].event_id == ref.event_id

    def test_subscriber_sees_settled_persisted_fact(
        self, bus, team_producer, team_payload, subscriber_plugin
    ) -> None:
        """S4 派发时 S3 已落定:订阅者收到的 ref 携带落盘事实。"""
        bus.mount_sink("rec", _RecordingSink())
        seen: list[EventRef] = []
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, r: seen.append(r),
        )
        ref = bus.publish(team_payload, producer=team_producer)
        assert len(seen) == 1
        assert seen[0].persisted is True
        assert seen[0].event_id == ref.event_id

    def test_receipt_fields_are_required(self) -> None:
        """回执字段无默认值:构造方必填(禁止缺字段静默通过)。"""
        with pytest.raises(TypeError):
            EventRef(event_id="e1", category="c", trace_id="t", ts=0.0)  # type: ignore[call-arg]


# ── 计数器四值 ───────────────────────────────────────────────────────────


class TestDeliveryCounters:
    def test_all_green_no_drop(self, bus, team_producer, team_payload, subscriber_plugin) -> None:
        """落盘 + 派发均成功 → dropped=0,其余三值按事件数累计。"""
        bus.mount_sink("rec", _RecordingSink())
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        bus.publish(team_payload, producer=team_producer)
        bus.publish(team_payload, producer=team_producer)
        assert _counts(bus, "team.delegation.cache_hit") == {
            "published": 2,
            "persisted": 2,
            "delivered": 2,
            "dropped": 0,
        }

    def test_dropped_when_not_persisted(self, bus, team_producer, team_payload) -> None:
        """dropped 定义一:未落盘。双条件同时命中也只计一次。"""
        ref = bus.publish(team_payload, producer=team_producer)
        assert ref.persisted is False
        assert _counts(bus, "team.delegation.cache_hit") == {
            "published": 1,
            "persisted": 0,
            "delivered": 0,
            "dropped": 1,
        }

    def test_dropped_when_zero_dispatch_with_declared_subscribers(
        self, bus, team_producer, team_payload
    ) -> None:
        """dropped 定义二:已落盘但零派发,且注册表声明了订阅者。"""
        bus.mount_sink("rec", _RecordingSink())
        ref = bus.publish(team_payload, producer=team_producer)
        assert ref.persisted is True
        assert _counts(bus, "team.delegation.cache_hit") == {
            "published": 1,
            "persisted": 1,
            "delivered": 0,
            "dropped": 1,
        }

    def test_no_drop_without_declared_subscribers(self) -> None:
        """落盘 + 零派发,但注册表未声明订阅者 → 不计 dropped。"""

        class _Producer:
            pass

        spec = EventSpec(
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            plane=Plane.STRUCTURAL,
            payload_class=TeamDelegationCacheHit,
            publishers=frozenset({_Producer}),
        )
        isolated = EventBus(EventRegistry.from_specs([spec]))
        isolated.mount_sink("rec", _RecordingSink())
        payload = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
        isolated.publish(payload, producer=_Producer)
        assert _counts(isolated, "team.delegation.cache_hit") == {
            "published": 1,
            "persisted": 1,
            "delivered": 0,
            "dropped": 0,
        }

    def test_counters_accumulate_across_publishes(
        self, bus, team_producer, team_payload, subscriber_plugin
    ) -> None:
        """计数器跨事件累计:先零落盘一次,再挂 sink + 订阅发一次。"""
        bus.publish(team_payload, producer=team_producer)
        bus.mount_sink("rec", _RecordingSink())
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        bus.publish(team_payload, producer=team_producer)
        assert _counts(bus, "team.delegation.cache_hit") == {
            "published": 2,
            "persisted": 1,
            "delivered": 1,
            "dropped": 1,
        }


# ── I2 零落盘策略 ────────────────────────────────────────────────────────


class TestZeroSinkPolicy:
    def test_default_policy_is_non_strict(self, bus) -> None:
        """迁移窗口默认 strict=False。"""
        assert bus.delivery_policy == DeliveryPolicy(strict=False)

    def test_configure_policy_roundtrip(self, bus) -> None:
        bus.configure_delivery_policy(strict=True)
        assert bus.delivery_policy == DeliveryPolicy(strict=True)
        bus.configure_delivery_policy(strict=False)
        assert bus.delivery_policy == DeliveryPolicy(strict=False)

    def test_strict_raises_event_no_sink_error_for_persistent_category(
        self, bus, spine_producer, spine_payload, subscriber_plugin
    ) -> None:
        """strict=True:持久类(observability)零 sink → fail-loud,不进 _fanout。"""
        bus.configure_delivery_policy(strict=True)
        seen: list[EventPayload] = []
        bus.subscribe(
            plugin=subscriber_plugin,
            category=Category.SPINE_COGNITION_BRAIN_THINK_START,
            on_event=lambda p, _r: seen.append(p),
        )
        with pytest.raises(EventNoSinkError) as excinfo:
            bus.publish(spine_payload, producer=spine_producer)
        assert excinfo.value.category == "spine.cognition.brain.think.start"
        assert seen == []
        assert _counts(bus, "spine.cognition.brain.think.start") == {
            "published": 1,
            "persisted": 0,
            "delivered": 0,
            "dropped": 1,
        }

    def test_non_strict_degrades_to_count_and_error_log(
        self, bus, spine_producer, spine_payload, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """strict=False:持久类零 sink → 不抛错,记 dropped + error 日志,事件继续派发。"""
        assert bus.delivery_policy.strict is False
        ref = bus.publish(spine_payload, producer=spine_producer)
        assert ref.persisted is False
        assert _counts(bus, "spine.cognition.brain.think.start") == {
            "published": 1,
            "persisted": 0,
            "delivered": 0,
            "dropped": 1,
        }
        captured = capsys.readouterr()
        assert "zero sinks" in captured.out
        assert "spine.cognition.brain.think.start" in captured.out

    def test_strict_still_counts_non_persistent_category(
        self, bus, team_producer, team_payload
    ) -> None:
        """strict=True:非持久类零 sink 只计数,不抛错、不打 error 日志。"""
        bus.configure_delivery_policy(strict=True)
        ref = bus.publish(team_payload, producer=team_producer)
        assert ref.persisted is False
        assert _counts(bus, "team.delegation.cache_hit") == {
            "published": 1,
            "persisted": 0,
            "delivered": 0,
            "dropped": 1,
        }


# ── delivery_snapshot 形状 ───────────────────────────────────────────────


class TestDeliverySnapshot:
    def test_empty_before_any_publish(self, bus) -> None:
        assert bus.delivery_snapshot() == {}

    def test_shape_and_four_keys(self, bus, team_producer, team_payload) -> None:
        """快照 = {category: 四值 dict};值均为 int。"""
        bus.publish(team_payload, producer=team_producer)
        snapshot = bus.delivery_snapshot()
        assert set(snapshot) == {"team.delegation.cache_hit"}
        entry = snapshot["team.delegation.cache_hit"]
        assert set(entry) == {"published", "persisted", "delivered", "dropped"}
        assert all(isinstance(v, int) for v in entry.values())

    def test_snapshot_is_a_copy(self, bus, team_producer, team_payload) -> None:
        """快照是拷贝:调用方写回不影响机制计数器。"""
        bus.publish(team_payload, producer=team_producer)
        bus.delivery_snapshot()["team.delegation.cache_hit"]["published"] = 999
        assert bus.delivery_snapshot()["team.delegation.cache_hit"]["published"] == 1

    def test_only_published_categories_appear(self, bus, team_producer, team_payload) -> None:
        """未发生 publish 的 category 不占快照条目。"""
        bus.publish(team_payload, producer=team_producer)
        assert "spine.cognition.brain.think.start" not in bus.delivery_snapshot()


# ── events-delivery CLI ──────────────────────────────────────────────────


class TestEventsDeliveryCommand:
    @pytest.fixture
    def seeded_default_bus(
        self, team_producer: type, team_payload: TeamDelegationCacheHit
    ) -> EventBus[EventPayload]:
        """把带计数的 bus 注入进程单例,供 CLI 命令读取。"""
        registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
        seeded: EventBus[EventPayload] = EventBus(registry)
        seeded.publish(team_payload, producer=team_producer)
        EventBus.set_default(seeded)
        return seeded

    def test_json_output(self, seeded_default_bus) -> None:
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        result = CliRunner().invoke(app, ["events-delivery", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["team.delegation.cache_hit"] == {
            "published": 1,
            "persisted": 0,
            "delivered": 0,
            "dropped": 1,
        }

    def test_category_filter(self, seeded_default_bus) -> None:
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        runner = CliRunner()
        hit = runner.invoke(
            app, ["events-delivery", "--category", "team.delegation.cache_hit", "--json"]
        )
        assert hit.exit_code == 0
        assert set(json.loads(hit.output)) == {"team.delegation.cache_hit"}
        miss = runner.invoke(app, ["events-delivery", "--category", "no.such.cat", "--json"])
        assert miss.exit_code == 0
        assert json.loads(miss.output) == {}

    def test_human_output_renders_table(self, seeded_default_bus) -> None:
        from typer.testing import CliRunner

        from lca.infrastructure.cli.cli import app

        result = CliRunner().invoke(app, ["events-delivery"])
        assert result.exit_code == 0
        for token in ("category", "published", "persisted", "delivered", "dropped"):
            assert token in result.output
        assert "team.delegation.cache_hit" in result.output
