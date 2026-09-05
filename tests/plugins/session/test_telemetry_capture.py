"""SessionTelemetryCapture plugin 测试(DSH session-telemetry 捕获缝)。

覆盖契约:

- live 模式事件→record 投影(fake backend 收集)
- on_demand 游标语义(capture_session 释放到指定 seq;幂等;失败重试)
- 脱敏钩子扣下单条不影响其他;钩子抛错 = 扣下(fail-closed)
- backend.emit 抛错 contained + 计数,不反噬 append
- sharing 透传;无后端 = DISABLED 语义(丢弃并计数)
- plugin 装配:requires session.store、provides session.telemetry、layer L2
- canonical 日志只读:捕获不改变 Session 日志
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.protocols.session.telemetry import (
    CHANNEL_LEDGER,
    SharingPolicy,
    TelemetryRecord,
)
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.telemetry_capture.telemetry_capture import (
    Config,
    SessionTelemetryCapture,
    setup,
)

# ── helpers ─────────────────────────────────────────────────────────


class _FakeBackend:
    """最小 :class:`SessionTelemetryBackend` 实现:收集记录,可选注入失败。"""

    def __init__(self, sharing: SharingPolicy = SharingPolicy.FULL, *, fail: bool = False) -> None:
        self.records: list[TelemetryRecord] = []
        self._sharing = sharing
        self.fail = fail
        self.emit_calls = 0
        self.flush_called = False
        self.shutdown_called = False

    @property
    def sharing(self) -> SharingPolicy:
        return self._sharing

    def emit(self, record: TelemetryRecord) -> None:
        self.emit_calls += 1
        if self.fail:
            raise RuntimeError("backend down")
        self.records.append(record)

    def flush(self) -> None:
        self.flush_called = True

    def shutdown(self) -> None:
        self.shutdown_called = True


def _fake_ctx(caps: dict[str, Any] | None = None) -> Any:
    """最小 stub PluginContext:provide + soft_get。"""

    class _Ctx:
        def __init__(self) -> None:
            self.provided: dict[str, Any] = {}
            self._caps: dict[str, Any] = dict(caps or {})

        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            self.provided[str(key)] = value

        def soft_get(self, key: str) -> Any | None:
            # 真实 PluginContext:provide 过的 capability 可被 soft_get 读回。
            return self.provided.get(key, self._caps.get(key))

    return _Ctx()


def _bodies(backend: _FakeBackend) -> list[str]:
    return [record.body for record in backend.records]


# ── live 模式投影 ───────────────────────────────────────────────────


def test_live_mode_projects_committed_events() -> None:
    """live:已提交事件投影为 ledger/info 记录,attributes 带身份三件套。"""
    store = SessionStore()
    session = store.create("s-live")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    capture.observe_session(session)

    event = session.append("spine.turn.started", {"turn": 1})

    assert len(backend.records) == 1
    record = backend.records[0]
    assert record.channel == CHANNEL_LEDGER
    assert record.severity == "info"
    assert record.body == "spine.turn.started"
    assert record.time == event.time
    assert record.attributes["session.id"] == "s-live"
    assert record.attributes["event.type"] == "spine.turn.started"
    assert record.attributes["event.seq"] == event.seq


def test_live_mode_does_not_mutate_canonical_log() -> None:
    """捕获只读:投影/交付不改变 Session 日志(C7 观察面)。"""
    store = SessionStore()
    session = store.create("s-readonly")
    capture = SessionTelemetryCapture(backend=_FakeBackend(), capture_mode="live")
    capture.observe_session(session)

    session.append("e0", {"k": 1})
    session.append("e1", {"k": 2})

    assert session.seq == 2
    assert session.event_at(0) is not None and session.event_at(0).type == "e0"
    assert session.event_at(1) is not None and session.event_at(1).type == "e1"


def test_cancel_observer_stops_capture() -> None:
    store = SessionStore()
    session = store.create("s-cancel")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    cancel = capture.observe_session(session)

    session.append("before", {})
    cancel()
    cancel()  # 幂等
    session.append("after", {})

    assert _bodies(backend) == ["before"]


# ── on_demand 游标语义 ──────────────────────────────────────────────


def test_on_demand_holds_events_until_capture_session() -> None:
    """on_demand:不实时交付;反馈触发时才按游标释放。"""
    store = SessionStore()
    session = store.create("s-od")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="on_demand")
    capture.observe_session(session)  # on_demand 下是 no-op

    session.append("e0", {})
    session.append("e1", {})
    session.append("e2", {})
    assert backend.records == []

    delivered = capture.capture_session(session, up_to_seq=1)
    assert delivered == 2
    assert _bodies(backend) == ["e0", "e1"]

    delivered = capture.capture_session(session)  # 释放到日志尾
    assert delivered == 1
    assert _bodies(backend) == ["e0", "e1", "e2"]

    assert capture.capture_session(session) == 0  # 幂等,无新记录


def test_on_demand_cursor_retries_on_backend_error() -> None:
    """backend.emit 抛错时游标不推进,下次捕获重试该记录。"""
    store = SessionStore()
    session = store.create("s-od-err")
    backend = _FakeBackend(fail=True)
    capture = SessionTelemetryCapture(backend=backend, capture_mode="on_demand")
    session.append("e0", {})

    assert capture.capture_session(session) == 0
    assert capture.backend_error_count == 1
    assert backend.records == []

    backend.fail = False
    assert capture.capture_session(session) == 1
    assert _bodies(backend) == ["e0"]


# ── 脱敏钩子 ────────────────────────────────────────────────────────


def test_redactor_withholds_single_record_not_others() -> None:
    """钩子返回 None 只扣下匹配记录,其余照常交付;计数准确。"""
    store = SessionStore()
    session = store.create("s-red")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    capture.observe_session(session)

    def _drop_secret(record: TelemetryRecord) -> TelemetryRecord | None:
        return None if record.body == "secret" else record

    cancel = capture.register_redactor(_drop_secret)
    session.append("secret", {})
    session.append("public", {})

    assert _bodies(backend) == ["public"]
    assert capture.redacted_count == 1

    cancel()
    session.append("secret", {})  # 取消后不再扣下
    assert _bodies(backend) == ["public", "secret"]
    assert capture.redacted_count == 1


def test_redactor_throwing_withholds_record() -> None:
    """钩子抛错 = fail-closed 扣下该条,不反噬 append。"""
    store = SessionStore()
    session = store.create("s-throw")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    capture.observe_session(session)

    def _boom(_record: TelemetryRecord) -> TelemetryRecord | None:
        raise RuntimeError("redactor crashed")

    capture.register_redactor(_boom)
    event = session.append("e0", {})  # append 不受影响

    assert event.seq == 0
    assert backend.records == []
    assert capture.redacted_count == 1


def test_redactor_transforms_record() -> None:
    """钩子返回新记录 = 出站副本被替换;canonical 日志不变。"""
    store = SessionStore()
    session = store.create("s-transform")
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    capture.observe_session(session)

    def _mask(record: TelemetryRecord) -> TelemetryRecord | None:
        return TelemetryRecord(
            channel=record.channel,
            time=record.time,
            severity=record.severity,
            attributes=dict(record.attributes),
            body="<redacted>",
        )

    capture.register_redactor(_mask)
    session.append("e0", {})

    assert _bodies(backend) == ["<redacted>"]
    assert session.event_at(0).type == "e0"  # canonical 未被改写


# ── 后端错误 contained ──────────────────────────────────────────────


def test_backend_emit_error_contained_in_live() -> None:
    """live:emit 抛错只计数 + warning,不反噬 append,不打断后续事件。"""
    store = SessionStore()
    session = store.create("s-err")
    backend = _FakeBackend(fail=True)
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    capture.observe_session(session)

    event = session.append("e0", {})
    assert event.seq == 0
    assert capture.backend_error_count == 1
    session.append("e1", {})
    assert capture.backend_error_count == 2
    assert backend.records == []  # fail 后端未收集任何记录


# ── sharing 透传 / 无后端语义 ───────────────────────────────────────


def test_sharing_passthrough_and_disabled_default() -> None:
    backend = _FakeBackend(sharing=SharingPolicy.FEEDBACK_ONLY)
    capture = SessionTelemetryCapture(backend=backend)
    assert capture.sharing == SharingPolicy.FEEDBACK_ONLY

    capture_no_backend = SessionTelemetryCapture()
    assert capture_no_backend.sharing == SharingPolicy.DISABLED


def test_no_backend_drops_and_counts() -> None:
    """无后端:记录丢弃并计数,不抛错。"""
    store = SessionStore()
    session = store.create("s-nobackend")
    capture = SessionTelemetryCapture(capture_mode="live")
    capture.observe_session(session)

    session.append("e0", {})
    assert capture.dropped_count == 1

    # 后端补挂后,新事件恢复交付
    backend = _FakeBackend()
    capture.attach_backend(backend)
    session.append("e1", {})
    assert _bodies(backend) == ["e1"]
    assert capture.dropped_count == 1


def test_shutdown_forwards_to_backend() -> None:
    backend = _FakeBackend()
    capture = SessionTelemetryCapture(backend=backend)
    capture.shutdown()
    assert backend.shutdown_called is True
    SessionTelemetryCapture().shutdown()  # 无后端 no-op,不抛


# ── plugin 装配 ────────────────────────────────────────────────────


async def test_setup_provides_capability_and_captures_future_sessions() -> None:
    """setup provide session.telemetry;setup 后创建的 Session 也被接管。"""
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await setup.setup(ctx, Config())

    assert "session.telemetry" in ctx.provided
    capture = ctx.provided["session.telemetry"]
    assert isinstance(capture, SessionTelemetryCapture)
    assert capture.capture_mode == "live"

    session = store.create("s-future")
    session.append("e", {})
    assert capture.dropped_count == 1  # 无后端 → 丢弃并计数


async def test_setup_on_demand_does_not_emit_live() -> None:
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await setup.setup(ctx, Config(capture_mode="on_demand"))
    capture = ctx.provided["session.telemetry"]

    backend = _FakeBackend()
    capture.attach_backend(backend)
    session = store.create("s")
    session.append("e", {})

    assert backend.records == []  # 不实时交付
    assert capture.capture_session(session) == 1
    assert _bodies(backend) == ["e"]


async def test_setup_attach_backend_via_capability() -> None:
    """能力可用性驱动:backend plugin 经 capability 拿 capture 并绑定。"""
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await setup.setup(ctx, Config(capture_mode="live"))

    capture = ctx.soft_get("session.telemetry")
    assert capture is not None
    backend = _FakeBackend()
    capture.attach_backend(backend)

    session = store.create("s")
    session.append("e", {})
    assert _bodies(backend) == ["e"]


async def test_setup_no_store_does_not_raise() -> None:
    ctx = _fake_ctx(caps={})
    await setup.setup(ctx, Config())
    assert "session.telemetry" in ctx.provided


def test_config_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="capture_mode"):
        Config(capture_mode="bogus")
    assert Config(capture_mode="on_demand").capture_mode == "on_demand"


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.session.telemetry_capture import telemetry_capture as plugin_module

    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.telemetry_capture"
    assert definition.spec.layer == "L2"
    assert "session.telemetry" in definition.provided_capability_keys
    assert "session.store" in definition.required_capability_keys
    effects = definition.spec.effects
    effects_value = (
        tuple(e.value if hasattr(e, "value") else str(e) for e in effects)
        if isinstance(effects, (list, tuple))
        else (effects.value if hasattr(effects, "value") else str(effects),)
    )
    assert "network" in effects_value
