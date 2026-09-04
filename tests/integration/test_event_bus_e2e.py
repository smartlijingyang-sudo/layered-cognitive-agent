"""EventBus 端到端集成测试 —— ADR-0183 验证链。

覆盖链路(纯 EventBus 公开 API):
publish → pre_dispatch hook → schema 校验 → sink 派发(FD-1)→ SpineSink 落盘
``<run_id>.spine.jsonl`` → SpineReader 还原(10 键字节布局,含 ``trace_id``)。

落盘隔离:全部走 ``tmp_path``;SpineSink 用显式 ``path_template`` 绑定
临时目录,不污染 cwd。

sink 装配:
- ``apply_pipeline(bus, pipeline)``:声明式装 hooks,并把 sinks 实例化进
  ``AppliedPipeline.sinks``(不自动 ``mount_sink`` / ``bus.subscribe``)。
- ``bus.mount_sink(id, backend)``:命令式挂落盘后端;publish→disk 场景须在
  ``apply_pipeline`` 之后显式 mount 回执里的 sink。
- ``bus.subscribe(...)``:consumer_rules 不再由 ``apply_pipeline`` 自动接线;
  需要 fan-out 时由测试 / 调用方显式订阅。
- 生产 boot 仅走 ``register_pipeline_once`` 装 hook(迁移期不启用 sink 派发)。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import ClassVar

import pytest

from lca.contracts.event import Category, EventPayload, Plane
from lca.harness.profile.pipeline_loader import apply_pipeline
from lca_kernel.events import EventRef
from lca_kernel.events.bus import EventBus, FailureSemantics, PayloadSchemaError
from lca_kernel.events.errors import (
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
from lca_kernel.events.hooks import PublishContext, SkipDispatch
from lca_kernel.events.payloads_spine import SpineEventPayload
from lca_kernel.events.pipeline import (
    ConsumerRule,
    HookSpec,
    Pipeline,
    SinkSpec,
    Stage,
    matches_rule,
)
from lca_kernel.events.reader import SpineReader
from lca_kernel.events.registry import EventRegistry, EventSpec
from lca_kernel.events.sinks.spine_sink import SpineSink

CAT = Category.SPINE_COGNITION_BRAIN_PERCEIVE_START
RUN_ID = "run-e2e-eventbus"

# SpineEventRecord.to_dict() 的 10 键字节布局(下游消费者契约;含 ADR-0183 §3.9 trace_id)。
RECORD_KEYS = frozenset(
    {
        "event_id",
        "category",
        "execution_point",
        "channel",
        "payload",
        "ts",
        "causation_id",
        "prev_event_hash",
        "event_hash",
        "trace_id",
    }
)


# ── 测试替身 ─────────────────────────────────────────────────────────────


class TestProducer:
    """registry 授权的 producer。"""


class TestSinkPlugin:
    """registry 授权的 sink 消费方(FAIL_FAST 路径)。

    提供 (payload, ref) ``__call__`` 形态,供测试显式 ``bus.subscribe``。
    """

    seen: ClassVar[list[str]] = []

    def __call__(self, payload: EventPayload, ref: EventRef) -> None:
        TestSinkPlugin.seen.append(ref.event_id)


class TestSubscriberPlugin:
    """registry 授权的派生消费方(CONTAINED 路径)。"""

    seen: ClassVar[list[str]] = []

    def __call__(self, payload: EventPayload, ref: EventRef) -> None:
        TestSubscriberPlugin.seen.append(ref.event_id)


class UnauthorizedPlugin:
    """不在 registry 白名单的类。"""


class RecordingPreDispatchHook:
    """PreDispatchHook:记录调用后原样放行 payload。

    register_pipeline 以无参 ``spec.hook()`` 实例化,调用记录只能挂类属性。
    """

    calls: ClassVar[list[tuple[type, type]]] = []

    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch:
        RecordingPreDispatchHook.calls.append((type(payload), producer))
        return payload


class SkipAllHook:
    """PreDispatchHook:对一切事件返回 SkipDispatch。"""

    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch:
        return SkipDispatch()


class WrongPayload(EventPayload):
    """与 spec payload_class 不符的类型 → 触发 schema 校验拒绝。"""

    category: Category = CAT


# ── 构造 helpers ─────────────────────────────────────────────────────────


def _make_registry() -> EventRegistry:
    """测试专属鉴权矩阵:不读生产 yaml,白名单全部是本文件的测试替身。

    直接构造 ``EventRegistry``:``from_specs`` 只吃 ``*_tokens`` / catalog,
    不把 ``EventSpec.publishers`` / ``subscribers`` frozenset 抄进矩阵。
    """
    pubs = frozenset({TestProducer})
    subs = frozenset({TestSinkPlugin, TestSubscriberPlugin})
    spec = EventSpec(
        category=CAT,
        plane=Plane.OBSERVABILITY,
        payload_class=SpineEventPayload,
        fields={"state_id": "str"},
        publishers=pubs,
        subscribers=subs,
    )
    return EventRegistry(
        specs=(spec,),
        publishers={CAT: pubs},
        subscribers={CAT: subs},
        consumer_rules=(),
        payload_by_category={CAT: SpineEventPayload},
    )


def _spine_payload(seq: int) -> SpineEventPayload:
    return SpineEventPayload(
        category=CAT,
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": f"state-{seq}", "seq": seq},
    )


def _make_pipeline(hook_cls: type = RecordingPreDispatchHook) -> Pipeline:
    """声明式 Pipeline:hooks + sinks + consumer_rules 三段齐备。"""
    return Pipeline(
        name="e2e-spine",
        hooks=(HookSpec(id="pre-dispatch", hook=hook_cls, stage=Stage.PRE_DISPATCH),),
        sinks=(
            SinkSpec(
                id="spine",
                backend=SpineSink,
                failure=FailureSemantics.FAIL_FAST,
                config={"path_template": "{run_id}.spine.jsonl"},
            ),
        ),
        consumer_rules=(
            ConsumerRule(
                prefix="spine.cognition.",
                plugins=(TestSinkPlugin,),
                failure=FailureSemantics.FAIL_FAST,
            ),
        ),
    )


@pytest.fixture
def bus(event_singletons_reset: None) -> EventBus[EventPayload]:
    """reset_singleton 后经 default() 取出的进程级单例。"""
    EventBus.set_default(EventBus(_make_registry()))
    return EventBus.default()


@pytest.fixture
def spine_sink(tmp_path) -> Iterator[SpineSink]:
    """绑定 tmp_path 的 SpineSink;路径模板显式含临时目录。"""
    sink = SpineSink(path_template=str(tmp_path / "{run_id}.spine.jsonl"))
    sink.set_run_id(RUN_ID)
    yield sink
    sink.close()


def _wire_sink(bus: EventBus[EventPayload], sink: SpineSink) -> None:
    # 命令式装载:publish 期经 _dispatch_sinks 把 build_record 结果派发到后端。
    bus.mount_sink("spine", sink, failure=FailureSemantics.FAIL_FAST)


# ── 主链路:publish → hook → 校验 → sink 派发 → 落盘 → 还原 ───────────────


def test_publish_hook_schema_fanout_spine_roundtrip(
    bus: EventBus[EventPayload],
    spine_sink: SpineSink,
    tmp_path,
) -> None:
    RecordingPreDispatchHook.calls.clear()
    TestSinkPlugin.seen.clear()
    bus.register_pipeline(_make_pipeline())
    _wire_sink(bus, spine_sink)

    refs = [bus.publish(_spine_payload(i), producer=TestProducer) for i in range(3)]
    spine_sink.close()

    spine_path = tmp_path / f"{RUN_ID}.spine.jsonl"
    assert spine_path.exists()

    # 字节布局:每行 10 键完整。
    raw_lines = [json.loads(line) for line in spine_path.read_text(encoding="utf-8").splitlines()]
    assert len(raw_lines) == 3
    for line in raw_lines:
        assert set(line) == RECORD_KEYS

    # SpineReader 还原全部事件,顺序与 publish 一致。
    records = list(SpineReader(RUN_ID, path=spine_path).events())
    assert [r.event_id for r in records] == [ref.event_id for ref in refs]
    for seq, record in enumerate(records):
        assert record.category == CAT.value
        assert record.execution_point == "brain.perceive.start"
        assert record.channel == "fact"
        assert record.payload == {"state_id": f"state-{seq}", "seq": seq}
        assert set(record.to_dict()) == RECORD_KEYS

    # reader.filter 前缀过滤。
    assert (
        len(list(SpineReader(RUN_ID, path=spine_path).filter(category_prefix="spine.cognition.")))
        == 3
    )
    assert (
        len(list(SpineReader(RUN_ID, path=spine_path).filter(category_prefix="spine.body."))) == 0
    )

    # pre_dispatch hook 每事件调一次,producer 身份透传。
    assert RecordingPreDispatchHook.calls == [(SpineEventPayload, TestProducer)] * 3


def test_default_singleton_is_process_level(bus: EventBus[EventPayload]) -> None:
    assert EventBus.default() is bus


def test_publish_trace_id_explicit_and_generated(bus: EventBus[EventPayload]) -> None:
    explicit = bus.publish(_spine_payload(0), producer=TestProducer, trace_id="trc_e2e_fixed")
    assert explicit.trace_id == "trc_e2e_fixed"
    generated = bus.publish(_spine_payload(1), producer=TestProducer)
    assert generated.trace_id.startswith("trc_")


# ── 鉴权 ────────────────────────────────────────────────────────────────


def test_unauthorized_producer_rejected(
    bus: EventBus[EventPayload],
    tmp_path,
) -> None:
    RecordingPreDispatchHook.calls.clear()
    bus.register_pipeline(_make_pipeline())
    with pytest.raises(UnauthorizedPublishError):
        bus.publish(_spine_payload(0), producer=UnauthorizedPlugin)
    # 鉴权先于 hook:hook 未执行,也未产生任何落盘。
    assert RecordingPreDispatchHook.calls == []
    assert list(tmp_path.glob("*.spine.jsonl")) == []


def test_unauthorized_subscribe_rejected(bus: EventBus[EventPayload]) -> None:
    with pytest.raises(UnauthorizedSubscribeError):
        bus.subscribe(
            plugin=UnauthorizedPlugin,
            category=CAT,
            on_event=lambda payload, ref: None,
        )


# ── schema 校验与 hook 哨兵 ──────────────────────────────────────────────


def test_schema_validation_rejects_wrong_payload_type(bus: EventBus[EventPayload]) -> None:
    with pytest.raises(PayloadSchemaError):
        bus.publish(WrongPayload(), producer=TestProducer)


def test_pre_dispatch_skip_dispatch_blocks_publish(
    bus: EventBus[EventPayload],
    spine_sink: SpineSink,
    tmp_path,
) -> None:
    bus.register_pipeline(_make_pipeline(hook_cls=SkipAllHook))
    _wire_sink(bus, spine_sink)
    with pytest.raises(PayloadSchemaError):
        bus.publish(_spine_payload(0), producer=TestProducer)
    spine_sink.close()
    assert (tmp_path / f"{RUN_ID}.spine.jsonl").read_text(encoding="utf-8") == ""


# ── 失败语义(I-FW-BUS-2)────────────────────────────────────────────────


def test_fail_fast_sink_failure_propagates(bus: EventBus[EventPayload]) -> None:
    def _boom(payload: EventPayload, ref: EventRef) -> None:
        raise RuntimeError("sink down")

    bus.subscribe(
        plugin=TestSinkPlugin,
        category=CAT,
        on_event=_boom,
        failure=FailureSemantics.FAIL_FAST,
    )
    with pytest.raises(RuntimeError, match="sink down"):
        bus.publish(_spine_payload(0), producer=TestProducer)


def test_contained_subscriber_failure_is_swallowed(bus: EventBus[EventPayload]) -> None:
    seen: list[str] = []

    def _boom(payload: EventPayload, ref: EventRef) -> None:
        raise RuntimeError("subscriber down")

    def _ok(payload: EventPayload, ref: EventRef) -> None:
        seen.append(ref.event_id)

    bus.subscribe(
        plugin=TestSubscriberPlugin,
        category=CAT,
        on_event=_boom,
        failure=FailureSemantics.CONTAINED,
    )
    bus.subscribe(
        plugin=TestSubscriberPlugin, category=CAT, on_event=_ok, failure=FailureSemantics.CONTAINED
    )
    ref = bus.publish(_spine_payload(0), producer=TestProducer)
    assert seen == [ref.event_id]


# ── consumer_rules 前缀语义 + register_pipeline 缺口 tripwire ────────────


def test_consumer_rule_prefix_match() -> None:
    rule = ConsumerRule(prefix="spine.cognition.", plugins=(TestSinkPlugin,))
    assert matches_rule(CAT, rule)
    assert not matches_rule(Category.SPINE_BODY_TOOL_EXECUTE_START, rule)


def test_register_pipeline_does_not_mount_sinks(
    bus: EventBus[EventPayload],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """register_pipeline 仅装 hook(生产 boot 安全形态);sink 装载走
    ``mount_sink``(``apply_pipeline`` 只把 sinks 放进回执,由调用方显式 mount)。

    COMPAT(delete-when: 21 个 publisher 全部迁移到 bus.publish 后,生产 boot
    改为 apply_pipeline,sink 派发在迁移完成时一并启用,tracking: ADR-0183)
    """
    monkeypatch.chdir(tmp_path)
    bus.register_pipeline(_make_pipeline())
    ref = bus.publish(_spine_payload(0), producer=TestProducer)
    assert ref.event_id
    assert list(tmp_path.glob("*.spine.jsonl")) == []


def test_apply_pipeline_mounts_sinks_declaratively(
    bus: EventBus[EventPayload],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply_pipeline 装 hooks 并返回 sinks;测试显式 ``mount_sink`` +
    ``bus.subscribe`` 后 publish 经 _dispatch_sinks 落盘 <run_id>.spine.jsonl。
    """
    RecordingPreDispatchHook.calls.clear()
    TestSinkPlugin.seen.clear()
    monkeypatch.chdir(tmp_path)

    pipeline = _make_pipeline()
    applied = apply_pipeline(bus, pipeline)
    spine = applied.sinks["spine"]
    assert isinstance(spine, SpineSink)
    assert applied.consumer_handles == ()
    sink_failure = next(spec.failure for spec in pipeline.sinks if spec.id == "spine")
    bus.mount_sink("spine", spine, failure=sink_failure)
    # apply_pipeline 不再按 consumer_rules 自动 subscribe;测试显式接线。
    rule = next(r for r in pipeline.consumer_rules if r.prefix == "spine.cognition.")
    bus.subscribe(
        plugin=TestSinkPlugin,
        category=CAT,
        on_event=TestSinkPlugin(),
        failure=rule.failure,
    )
    spine.set_run_id(RUN_ID)

    refs = [bus.publish(_spine_payload(i), producer=TestProducer) for i in range(2)]
    spine.close()

    spine_path = tmp_path / f"{RUN_ID}.spine.jsonl"
    assert spine_path.exists()
    raw_lines = [json.loads(line) for line in spine_path.read_text(encoding="utf-8").splitlines()]
    assert len(raw_lines) == 2
    assert [line["event_id"] for line in raw_lines] == [ref.event_id for ref in refs]
    # pre_dispatch hook 已跑(声明式装载生效)。
    assert RecordingPreDispatchHook.calls == [(SpineEventPayload, TestProducer)] * 2
    # 显式 subscribe 的 TestSinkPlugin.__call__ 记录了 ref.event_id。
    assert TestSinkPlugin.seen == [ref.event_id for ref in refs]
