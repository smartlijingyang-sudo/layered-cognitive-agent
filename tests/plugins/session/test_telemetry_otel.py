"""OtelTelemetryBackend plugin 测试(DSH session-telemetry-otel)。

覆盖契约:

- mode 大小写不敏感归一 + 闭集校验;非法值 fail-loud
- mode → sharing 映射;DISABLED 丢弃一切 + warning 一次
- emit 非阻塞入队(自有有界队列;队满丢最旧 + 计数)
- shutdown 有界排空(记录经 OTel provider 到达 exporter)
- FULL 模式记录到达 OTel logger(InMemoryLogRecordExporter,无网络)
- plugin 装配:requires session.telemetry、provides session.telemetry.backend.otel
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

from lca.contracts.protocols.session.telemetry import SharingPolicy, TelemetryRecord
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.telemetry_capture.telemetry_capture import (
    Config as CaptureConfig,
)
from lca.plugins.session.telemetry_capture.telemetry_capture import (
    setup as capture_setup,
)
from lca.plugins.session.telemetry_otel.telemetry_otel import (
    Config,
    OtelTelemetryBackend,
    setup,
)

# ── helpers ─────────────────────────────────────────────────────────


def _record(
    body: str = "spine.turn.started", severity: str = "info", seq: int = 0
) -> TelemetryRecord:
    return TelemetryRecord(
        channel="ledger",
        time=1_700_000_000_000,
        severity=severity,
        attributes={"session.id": "s1", "event.type": body, "event.seq": seq},
        body=body,
    )


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


# ── mode 归一与校验 ─────────────────────────────────────────────────


def test_mode_normalization_case_insensitive() -> None:
    assert Config(mode="full").mode == "FULL"
    assert Config(mode="Feedback_Only").mode == "FEEDBACK_ONLY"
    assert Config(mode="disabled").mode == "DISABLED"
    assert Config().mode == "DISABLED"  # 缺省


def test_mode_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="mode"):
        Config(mode="bogus")
    with pytest.raises(ValueError, match="mode"):
        OtelTelemetryBackend(mode="bogus")


def test_mode_maps_to_sharing() -> None:
    assert OtelTelemetryBackend(mode="FULL").sharing == SharingPolicy.FULL
    assert OtelTelemetryBackend(mode="FEEDBACK_ONLY").sharing == SharingPolicy.FEEDBACK_ONLY
    assert OtelTelemetryBackend(mode="DISABLED").sharing == SharingPolicy.DISABLED


# ── DISABLED 丢弃 ──────────────────────────────────────────────────


def test_disabled_drops_everything_and_warns_once() -> None:
    exporter = InMemoryLogRecordExporter()
    backend = OtelTelemetryBackend(mode="DISABLED", exporter=exporter)

    backend.emit(_record("a"))
    backend.emit(_record("b"))

    assert backend.dropped_count == 0  # 未入队,直接丢弃
    assert backend.pending_count == 0
    assert backend.disabled_warned is True
    backend.flush()
    backend.shutdown()
    assert len(exporter.get_finished_logs()) == 0


# ── emit 非阻塞入队(自有有界队列)──────────────────────────────────


def test_emit_enqueues_and_drop_oldest_on_full() -> None:
    """队满丢最旧 + ``dropped_count``;用 ``_enqueue`` 隔离,不与线程竞态。"""
    backend = OtelTelemetryBackend(mode="FULL", queue_size=2)
    for index in range(5):
        backend._enqueue(_record(f"e{index}"))

    assert backend.dropped_count == 3
    assert backend.pending_count == 2
    # 保留的是最新的两条(丢最旧)
    queued = [backend._queue.get_nowait() for _ in range(2)]
    assert [record.body for record in queued] == ["e3", "e4"]


def test_emit_returns_without_blocking() -> None:
    """emit 只入队即返回(非阻塞);记录经 flush 到达 exporter。"""
    exporter = InMemoryLogRecordExporter()
    backend = OtelTelemetryBackend(mode="FULL", exporter=exporter)

    backend.emit(_record("e0"))
    assert backend.pending_count <= 1  # 入队后由线程消费,不阻塞调用方

    backend.flush()
    assert len(exporter.get_finished_logs()) == 1
    backend.shutdown()


# ── FULL 记录到达 OTel logger ──────────────────────────────────────


def test_full_mode_records_reach_otel_logger() -> None:
    """FULL:记录经 LoggerProvider 到达 InMemory exporter,body/attributes/severity 保真。"""
    exporter = InMemoryLogRecordExporter()
    backend = OtelTelemetryBackend(mode="FULL", exporter=exporter, service_name="svc-test")

    backend.emit(_record("spine.turn.started", severity="info", seq=0))
    backend.emit(_record("spine.turn.ended", severity="error", seq=1))
    backend.flush()

    logs = exporter.get_finished_logs()
    assert len(logs) == 2

    first = logs[0].log_record
    assert first.body == "spine.turn.started"
    assert first.severity_text == "INFO"
    assert first.attributes["session.id"] == "s1"
    assert first.attributes["event.seq"] == 0
    assert first.attributes["telemetry.channel"] == "ledger"
    assert first.timestamp == 1_700_000_000_000 * 1_000_000  # ms → ns

    second = logs[1].log_record
    assert second.body == "spine.turn.ended"
    assert second.severity_text == "ERROR"

    backend.shutdown()


# ── shutdown 有界排空 ──────────────────────────────────────────────


def test_shutdown_drains_queue_to_exporter() -> None:
    exporter = InMemoryLogRecordExporter()
    backend = OtelTelemetryBackend(mode="FULL", exporter=exporter)

    for index in range(10):
        backend.emit(_record(f"e{index}", seq=index))
    backend.shutdown()

    assert len(exporter.get_finished_logs()) == 10
    assert backend.pending_count == 0


def test_shutdown_is_idempotent() -> None:
    exporter = InMemoryLogRecordExporter()
    backend = OtelTelemetryBackend(mode="FULL", exporter=exporter)
    backend.emit(_record())
    backend.shutdown()
    backend.shutdown()  # 重复调用幂等,不抛
    assert len(exporter.get_finished_logs()) == 1

    # shutdown 后的 emit 被丢弃(不重启线程),不抛错
    backend.emit(_record("late"))
    assert backend.pending_count == 0


def test_shutdown_disabled_is_noop() -> None:
    backend = OtelTelemetryBackend(mode="DISABLED")
    backend.shutdown()  # 未启动,no-op,不抛


# ── plugin 装配 ────────────────────────────────────────────────────


async def test_setup_attaches_backend_to_capture_and_provides() -> None:
    """setup:经 session.telemetry 拿捕获并 attach_backend,provide otel capability。"""
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await capture_setup.setup(ctx, CaptureConfig(capture_mode="live"))
    await setup.setup(ctx, Config(mode="FULL"))

    assert "session.telemetry.backend.otel" in ctx.provided
    backend = ctx.provided["session.telemetry.backend.otel"]
    assert isinstance(backend, OtelTelemetryBackend)

    capture = ctx.soft_get("session.telemetry")
    assert capture.backend is backend  # attach_backend 已绑定
    assert capture.sharing == SharingPolicy.FULL


async def test_setup_without_capture_warns_but_still_provides() -> None:
    ctx = _fake_ctx(caps={})  # 无 session.telemetry
    await setup.setup(ctx, Config(mode="DISABLED"))
    assert "session.telemetry.backend.otel" in ctx.provided


async def test_end_to_end_capture_to_exporter() -> None:
    """live capture + otel backend:Session 事件到达 InMemory exporter(无网络)。"""
    exporter = InMemoryLogRecordExporter()
    store = SessionStore()
    ctx = _fake_ctx({"session.store": store})
    await capture_setup.setup(ctx, CaptureConfig(capture_mode="live"))
    await setup.setup(ctx, Config(mode="FULL"))

    backend = ctx.provided["session.telemetry.backend.otel"]
    backend._exporter_override = exporter  # 注入测试 exporter(生产走 no-op/OTLP)

    session = store.create("s-e2e")
    session.append("spine.turn.started", {"turn": 1})
    backend.flush()

    logs = exporter.get_finished_logs()
    assert len(logs) == 1
    assert logs[0].log_record.body == "spine.turn.started"
    assert logs[0].log_record.attributes["session.id"] == "s-e2e"
    backend.shutdown()


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError):
        Config(unknown_key="x")


def test_plugin_manifest_metadata() -> None:
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.session.telemetry_otel import telemetry_otel as plugin_module

    definition = definition_from_plugin(plugin_module.setup, module=__name__)
    assert definition.id == "lca.plugins.session.telemetry_otel"
    assert definition.spec.layer == "L2"
    assert "session.telemetry.backend.otel" in definition.provided_capability_keys
    assert "session.telemetry" in definition.required_capability_keys
    effects = definition.spec.effects
    effects_value = (
        tuple(e.value if hasattr(e, "value") else str(e) for e in effects)
        if isinstance(effects, (list, tuple))
        else (effects.value if hasattr(effects, "value") else str(effects),)
    )
    assert "network" in effects_value
