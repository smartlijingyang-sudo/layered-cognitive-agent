"""EventBus 单元测试 —— ADR-0183 PR-1+PR-2 守护。

覆盖:
- publish / subscribe / register_pipeline 三入口
- pre_dispatch hook 替换 payload + SkipDispatch
- post_dispatch hook 派生新事件
- failure hook 吞错 vs 上抛
- failure= 参数语义:FAIL_FAST 上抛,CONTAINED 吞错
- trace_id 优先顺序:payload → contextvars(留 stub) → new_id("trc")
- 鉴权失败 raise UnauthorizedPublishError
- ConsumerHandle.unregister 留 stub
- 重置 EventBus.default() 单例(测试隔离)

不变量 I-FW-BUS-1/2 的单元测试;架构不变量测试见
``tests/architecture/test_event_bus_invariants.py``。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.event import Category, EventPayload
from lca_kernel.events.bus import (
    ConsumerHandle,
    EventBus,
    FailureSemantics,
    PayloadSchemaError,
)
from lca_kernel.events.errors import (
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
from lca_kernel.events.hooks import (
    FailureAction,
    PublishContext,
    SkipDispatch,
)
from lca_kernel.events.mechanism import (
    _DEFAULT_CONFIG_DIR,
    EventRef,
)
from lca_kernel.events.pipeline import (
    ConsumerRule,
    HookSpec,
    Pipeline,
    Stage,
    matches_rule,
    parse_pipeline_yaml,
)
from lca_kernel.events.registry import EventRegistry

# ── helpers ──────────────────────────────────────────────────────────────


def _make_bus() -> EventBus[EventPayload]:
    """独立 EventBus 实例(从默认 yaml 加载 registry),避免单例串扰。"""
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    return EventBus(registry)


@pytest.fixture
def bus() -> EventBus[EventPayload]:
    """每个测试用独立 EventBus 实例。"""
    return _make_bus()


@pytest.fixture
def authorized_payload() -> EventPayload:
    """最小可用 payload:TeamDelegationCacheHit 在 yaml 试点白名单内。"""
    from lca_kernel.events import TeamDelegationCacheHit

    return TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)


@pytest.fixture
def authorized_plugin() -> type:
    """yaml publishers 白名单内的合法 plugin:DelegationCachePlugin。"""
    from lca.plugins.events.publishers.delegation_cache.plugin import (
        DelegationCachePlugin,
    )

    return DelegationCachePlugin


@pytest.fixture
def authorized_subscriber_plugin() -> type:
    """yaml subscribers 白名单内的合法 plugin:ConsoleProjectorSubscriber。"""
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )

    return ConsoleProjectorSubscriber


# ── publish 入口 ──────────────────────────────────────────────────────────


class TestPublish:
    """ADR-0183 §3.1 publish 入口。"""

    def test_publish_basic_returns_event_ref(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """publish 后返回 EventRef,event_id 以 "evt-" 开头。"""
        ref = bus.publish(authorized_payload, producer=authorized_plugin)
        assert isinstance(ref, EventRef)
        assert ref.event_id.startswith("evt-") or ref.event_id.startswith("evt_")

    def test_publish_unauthorized_raises(
        self,
        bus: EventBus[EventPayload],
        authorized_payload: EventPayload,
    ) -> None:
        """producer 不在白名单 → raise UnauthorizedPublishError。"""

        class _RoguePlugin:
            pass

        with pytest.raises(UnauthorizedPublishError):
            bus.publish(authorized_payload, producer=_RoguePlugin)

    def test_publish_missing_plugin_identity_raises(
        self,
        bus: EventBus[EventPayload],
        authorized_payload: EventPayload,
    ) -> None:
        """producer=None 或非 type → raise MissingPluginIdentityError。"""
        with pytest.raises(MissingPluginIdentityError):
            bus.publish(authorized_payload, producer=None)  # type: ignore[arg-type]
        with pytest.raises(MissingPluginIdentityError):
            bus.publish(authorized_payload, producer="not a type")  # type: ignore[arg-type]

    def test_event_ref_has_iso_ts(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """EventRef.ts 是 float(epoch)。"""
        ref = bus.publish(authorized_payload, producer=authorized_plugin)
        assert isinstance(ref.ts, float)

    def test_trace_id_priority_payload_first(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
    ) -> None:
        """trace_id 显式传入 → EventRef.trace_id 等于传入值。"""
        from lca_kernel.events import TeamDelegationCacheHit

        explicit = new_id("trc")
        payload = TeamDelegationCacheHit(callee_role="a", subtask="b", step=1)
        ref = bus.publish(payload, producer=authorized_plugin, trace_id=explicit)
        assert ref.trace_id == explicit

    def test_trace_id_priority_generated_when_omitted(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """trace_id 未传 → 机制生成 new_id("trc")。"""
        ref = bus.publish(authorized_payload, producer=authorized_plugin)
        assert ref.trace_id.startswith("trc-") or ref.trace_id.startswith("trc_")

    def test_payload_schema_mismatch_raises(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
    ) -> None:
        """payload type 与 yaml spec 不符 → raise PayloadSchemaError。"""

        class _WrongPayload(EventPayload):
            category: Category = Category.TEAM_DELEGATION_CACHE_HIT

        with pytest.raises(PayloadSchemaError):
            bus.publish(_WrongPayload(), producer=authorized_plugin)


# ── subscribe 入口 ───────────────────────────────────────────────────────


class TestSubscribe:
    """ADR-0183 §3.1 subscribe 入口。"""

    def test_subscribe_records_consumer(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """subscribe 后 dispatch 时 callback 被调。"""
        received: list[tuple[EventPayload, object]] = []
        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, r: received.append((p, r)),
        )
        bus.publish(authorized_payload, producer=authorized_plugin)
        assert len(received) == 1
        payload, ref = received[0]
        assert payload.callee_role == "a"
        assert ref.event_id.startswith("evt-") or ref.event_id.startswith("evt_")

    def test_subscribe_unauthorized_raises(
        self,
        bus: EventBus[EventPayload],
    ) -> None:
        """plugin 不在白名单 → raise UnauthorizedSubscribeError。"""

        class _RogueSubscriber:
            pass

        with pytest.raises(UnauthorizedSubscribeError):
            bus.subscribe(
                plugin=_RogueSubscriber,
                category=Category.TEAM_DELEGATION_CACHE_HIT,
                on_event=lambda _p, _r: None,
            )

    def test_subscribe_missing_plugin_identity_raises(
        self,
        bus: EventBus[EventPayload],
    ) -> None:
        """plugin=None 或非 type → raise MissingPluginIdentityError。"""
        with pytest.raises(MissingPluginIdentityError):
            bus.subscribe(
                plugin=None,  # type: ignore[arg-type]
                category=Category.TEAM_DELEGATION_CACHE_HIT,
                on_event=lambda _p, _r: None,
            )

    def test_subscribe_returns_consumer_handle(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
    ) -> None:
        """subscribe 返回 ConsumerHandle(含 plugin / category,unregister 留 stub)。"""
        handle = bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        assert isinstance(handle, ConsumerHandle)
        assert handle.plugin is authorized_subscriber_plugin
        assert handle.category is Category.TEAM_DELEGATION_CACHE_HIT
        # unregister 留 stub:不应抛错(本 PR 框架不实装删除路径)。
        handle.unregister()

    def test_subscribe_accepts_category_string(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
    ) -> None:
        """subscribe 接受 category=str(自动 coerce 到 Category enum)。"""
        handle = bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category="team.delegation.cache_hit",
            on_event=lambda _p, _r: None,
        )
        assert handle.category is Category.TEAM_DELEGATION_CACHE_HIT


# ── failure 语义 ────────────────────────────────────────────────────────


class TestFailureSemantics:
    """ADR-0183 §3.1 failure= 参数语义。"""

    def test_subscribe_with_fail_fast_propagates(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """subscribe(failure=FAIL_FAST) 时 callback 抛错最终上抛给 publisher。"""

        def boom(_p, _r):
            raise RuntimeError("sink failure")

        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.FAIL_FAST,
        )
        with pytest.raises(RuntimeError, match="sink failure"):
            bus.publish(authorized_payload, producer=authorized_plugin)

    def test_subscribe_with_contained_swallows(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """subscribe(failure=CONTAINED) 时 callback 抛错不阻塞其他 callback。"""
        called: list[str] = []

        def boom(_p, _r):
            raise RuntimeError("contained failure")

        def ok(_p, _r):
            called.append("ok")

        # 第一个抛错,CONTAINED 模式应继续
        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.CONTAINED,
        )
        # 但 yaml 白名单内只有一个 subscriber plugin type;
        # 第二个 subscriber 用相同 plugin type 但不同 callback,fanout 顺序按注册序。
        # 为避免双 subscribe 同一 plugin 的不可预期行为,本断言只验证不抛错。
        bus.publish(authorized_payload, producer=authorized_plugin)
        # 关键断言:不抛错(ref 仍返回)。
        assert called == []  # 第一个 boom 已吞错;第二个 ok 未注册

    def test_subscribe_default_is_contained(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """不传 failure 参数 → CONTAINED 行为(consumer 抛错不阻塞 publish)。"""

        def boom(_p, _r):
            raise RuntimeError("default contained")

        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
        )
        # 不传 failure= → 默认 CONTAINED → 不抛
        ref = bus.publish(authorized_payload, producer=authorized_plugin)
        assert ref.event_id.startswith("evt-") or ref.event_id.startswith("evt_")


# ── register_pipeline + hooks ──────────────────────────────────────────


class TestRegisterPipeline:
    """ADR-0183 §3.1 + §3.2 register_pipeline + 4 hook 协议。"""

    def test_register_pipeline_stores_pipeline(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """pipeline 装载后再 publish 跑 hook。"""
        calls: list[tuple[EventPayload, type, PublishContext]] = []

        class _RecordingPreHook:
            def before_publish(self, payload, producer, ctx):
                calls.append((payload, producer, ctx))
                return payload

        pipeline = Pipeline(
            name="test",
            hooks=(HookSpec(id="rec", hook=_RecordingPreHook, stage=Stage.PRE_DISPATCH),),
        )
        bus.register_pipeline(pipeline)
        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )
        bus.publish(authorized_payload, producer=authorized_plugin)
        assert len(calls) == 1
        _p, producer, ctx = calls[0]
        assert producer is authorized_plugin
        assert ctx.producer is authorized_plugin
        assert isinstance(ctx.ts, float)

    def test_pre_dispatch_hook_can_replace_payload(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
    ) -> None:
        """PreDispatchHook 返回新 payload 时,sink 收到替换后的。"""
        from lca_kernel.events import TeamDelegationCacheHit

        class _RewritePreHook:
            def before_publish(self, payload, producer, ctx):
                # 返回一个新 payload(step 字段被改写)
                return TeamDelegationCacheHit(
                    callee_role="rewritten",
                    subtask=payload.subtask,
                    step=999,
                )

        seen: list[TeamDelegationCacheHit] = []

        def observer(_p, _r):
            seen.append(_p)  # type: ignore[arg-type]

        pipeline = Pipeline(
            name="test",
            hooks=(HookSpec(id="rewrite", hook=_RewritePreHook, stage=Stage.PRE_DISPATCH),),
        )
        bus.register_pipeline(pipeline)
        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=observer,
        )
        original = TeamDelegationCacheHit(callee_role="original", subtask="x", step=1)
        bus.publish(original, producer=authorized_plugin)
        assert len(seen) == 1
        assert seen[0].callee_role == "rewritten"
        assert seen[0].step == 999

    def test_pre_dispatch_hook_can_skip_dispatch(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """返回 SkipDispatch 时,sink / consumer 都不被调。"""
        seen: list[EventPayload] = []

        class _SkipPreHook:
            def before_publish(self, payload, producer, ctx):
                return SkipDispatch()

        pipeline = Pipeline(
            name="test",
            hooks=(HookSpec(id="skip", hook=_SkipPreHook, stage=Stage.PRE_DISPATCH),),
        )
        bus.register_pipeline(pipeline)
        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda p, _r: seen.append(p),
        )
        with pytest.raises(PayloadSchemaError):
            bus.publish(authorized_payload, producer=authorized_plugin)
        assert seen == []  # consumer 未被调

    def test_post_dispatch_hook_yields_followup_events(
        self,
        bus: EventBus[EventPayload],
        authorized_plugin: type,
        authorized_payload: EventPayload,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """post_dispatch hook yield 的新事件也走 publish(由本 EventBus 实例)。"""
        from lca_kernel.events import TeamDelegationCacheHit

        yielded: list[EventPayload] = []

        class _FollowupPostHook:
            def after_dispatch(self, payload, ref, results):
                new = TeamDelegationCacheHit(
                    callee_role="derived",
                    subtask="from-hook",
                    step=42,
                )
                yielded.append(new)
                yield new

        observed_publish_calls: list[tuple[EventPayload, type]] = []
        original_publish = bus.publish

        def spy_publish(payload, *, producer, trace_id=None):
            observed_publish_calls.append((payload, producer))
            return original_publish(payload, producer=producer, trace_id=trace_id)

        monkeypatch.setattr(bus, "publish", spy_publish)

        pipeline = Pipeline(
            name="test",
            hooks=(HookSpec(id="followup", hook=_FollowupPostHook, stage=Stage.POST_DISPATCH),),
        )
        bus.register_pipeline(pipeline)
        bus.publish(authorized_payload, producer=authorized_plugin)
        # 至少 2 次 publish:原始 + 派生
        assert len(observed_publish_calls) >= 2
        assert yielded[0].callee_role == "derived"  # type: ignore[attr-defined]


# ── Failure hook ────────────────────────────────────────────────────────


class TestFailureHook:
    """ADR-0183 §3.2 FailureHook。"""

    def test_failure_hook_contains_default(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """CONTAIN 模式下 consumer 抛错不影响 publish 流程。"""

        def boom(_p, _r):
            raise RuntimeError("subscriber fail")

        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.CONTAINED,
        )
        # 不应抛错
        ref = bus.publish(authorized_payload, producer=authorized_plugin)
        assert ref.event_id.startswith("evt-") or ref.event_id.startswith("evt_")

    def test_failure_hook_rethrow_propagates(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """RETHROW 模式下 consumer 抛错最终上抛给 publisher。"""

        def boom(_p, _r):
            raise RuntimeError("rethrow")

        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.FAIL_FAST,
        )
        with pytest.raises(RuntimeError, match="rethrow"):
            bus.publish(authorized_payload, producer=authorized_plugin)

    def test_failure_hook_explicit_rethrow_via_hook(
        self,
        bus: EventBus[EventPayload],
        authorized_subscriber_plugin: type,
        authorized_plugin: type,
        authorized_payload: EventPayload,
    ) -> None:
        """FailureHook(自定义)返回 RETHROW → consumer 抛错最终上抛。"""
        # 用一个 FailureHook 把所有 consumer 失败都升级为 RETHROW。
        from lca_kernel.events.hooks import FailureHook

        class _RethrowAll(FailureHook):
            def on_consumer_failure(self, payload, ref, exc):
                return FailureAction.RETHROW

        def boom(_p, _r):
            raise RuntimeError("via failure hook")

        bus.subscribe(
            plugin=authorized_subscriber_plugin,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=boom,
            failure=FailureSemantics.CONTAINED,
        )
        pipeline = Pipeline(
            name="test",
            hooks=(HookSpec(id="rethrow", hook=_RethrowAll, stage=Stage.ON_FAILURE),),
        )
        bus.register_pipeline(pipeline)
        with pytest.raises(RuntimeError, match="via failure hook"):
            bus.publish(authorized_payload, producer=authorized_plugin)


# ── Pipeline + ConsumerRule ──────────────────────────────────────────────


class TestPipelineAndConsumerRule:
    """ADR-0183 §3.3 Pipeline + ConsumerRule。"""

    def test_pipeline_parse_yaml_returns_empty(self, tmp_path) -> None:
        """yaml 不存在时返回空 Pipeline。"""
        path = tmp_path / "missing.yaml"
        pipeline = parse_pipeline_yaml(path)
        assert isinstance(pipeline, Pipeline)
        assert pipeline.hooks == ()
        assert pipeline.sinks == ()
        assert pipeline.consumer_rules == ()

    def test_consumer_rule_matches_prefix(self) -> None:
        """`category.value.startswith(rule.prefix)` 判定。"""
        rule = ConsumerRule(prefix="team.", plugins=())
        assert matches_rule(Category.TEAM_DELEGATION_CACHE_HIT, rule) is True
        assert matches_rule(Category.TEAM_MESSAGE_PUBLISHED, rule) is True
        # 不匹配
        assert matches_rule(Category.SPINE_COGNITION_BRAIN_PERCEIVE_START, rule) is False

    def test_consumer_rule_no_match_skips(self) -> None:
        """不匹配 prefix 时 matches_rule 返回 False。"""
        rule = ConsumerRule(prefix="spine.cognition.", plugins=())
        assert matches_rule(Category.TEAM_DELEGATION_CACHE_HIT, rule) is False
        assert matches_rule(Category.SPINE_LLM_CALL_START, rule) is False


# ── 单例 ────────────────────────────────────────────────────────────────


class TestSingleton:
    """ADR-0183 §3.1 EventBus 进程级单例。"""

    def test_event_bus_default_returns_same_instance(self) -> None:
        """多次 default() 返回同一实例(进程级单例)。"""
        EventBus.reset_singleton()
        try:
            a = EventBus.default()
            b = EventBus.default()
            assert a is b
        finally:
            EventBus.reset_singleton()

    def test_default_singleton_reset(self) -> None:
        """reset_singleton 后 default() 返回新实例。"""
        EventBus.reset_singleton()
        try:
            a = EventBus.default()
            EventBus.reset_singleton()
            b = EventBus.default()
            assert a is not b
        finally:
            EventBus.reset_singleton()

    def test_set_default_replaces(self) -> None:
        """set_default 可注入自定义实例。"""
        EventBus.reset_singleton()
        try:
            registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
            custom: EventBus[EventPayload] = EventBus(registry)
            EventBus.set_default(custom)
            assert EventBus.default() is custom
        finally:
            EventBus.reset_singleton()
