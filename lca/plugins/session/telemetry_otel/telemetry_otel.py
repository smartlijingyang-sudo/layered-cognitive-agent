"""OtelTelemetryBackend —— DSH ``session-telemetry-otel`` 一比一 LCA 实现。

对齐 deepseek-harness ``packages/session/session-telemetry-otel/src/index.ts``：
把 :class:`TelemetryRecord` 映射到 OTel Logs（``LoggerProvider`` +
``BatchLogRecordProcessor``），按部署 mode 披露共享策略。观察面派生物
（AGENTS.md §2.3 / C7）：只出站，不回灌日志，不写任何事实源。

与 DSH 的显式差异：**自建有界队列 + daemon 线程**——DSH 直接把
``logger.emit`` 当 enqueue，LCA 捕获侧 ``emit`` 处于 ``Session.append``
observer fire 热路径，故先入自有有界 :class:`queue.Queue`（满则丢最旧 +
``dropped_count``），daemon 线程批量转发 OTel logger 再经 SDK 批处理导出；
**无独立协调器**——DSH otel 后端自带 coordinator，LCA 捕获缝是独立 plugin，
本后端经 ``ctx.soft_get("session.telemetry")`` 拿捕获并 ``attach_backend``
绑定；**惰性 OTel 初始化**——provider 首次 emit 才建（无 import 副作用），
OTLP exporter 缺包回退 no-op + warning。

失败语义（有界排空，非阻塞入队）：``emit`` 永不阻塞（队满丢最旧）；
``flush`` / ``shutdown`` 以 ``shutdown_timeout_ms`` 为上界轮询排空 + force_flush。
"""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.session.telemetry import (
    SharingPolicy,
    TelemetryRecord,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_log = structlog.get_logger(__name__)

__all__ = ["Config", "OtelTelemetryBackend", "setup"]

_MODES: tuple[str, ...] = ("FULL", "FEEDBACK_ONLY", "DISABLED")
_MODE_TO_SHARING = {name: SharingPolicy(name.lower()) for name in _MODES}
_POLL_S = 0.05
_MAX_BATCH = 512
_QUEUE_SIZE_DEFAULT = 10_000
_SCOPE = "lca.session.telemetry"


def _normalize_mode(mode: str) -> str:
    """大小写不敏感归一 mode 到闭集；非法值 fail-loud。"""
    key = str(mode).strip().upper()
    if key not in _MODES:
        msg = f"mode 必须是 {list(_MODES)} 之一, got {mode!r}"
        raise ValueError(msg)
    return key


class Config(BaseModel):
    """plugin 配置：共享 mode、OTLP 端点、服务名与停机排空上界。"""

    model_config = {"extra": "forbid"}

    mode: str = "DISABLED"
    """共享策略（大小写不敏感）：``FULL`` / ``FEEDBACK_ONLY`` / ``DISABLED``。"""

    otlp_endpoint: str | None = None
    """OTLP/HTTP logs 端点；缺省 = no-op exporter + warning（不导出）。"""

    service_name: str = "lca"
    """OTel Resource ``service.name``。"""

    shutdown_timeout_ms: int = Field(default=5000, ge=1)
    """停机排空上界（毫秒）：轮询自有队列 + provider force_flush 的时间预算。"""

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        return _normalize_mode(value)


class OtelTelemetryBackend:
    """OTel Logs 后端：有界队列 + daemon 线程批量导出（sink 契约实现）。

    ``emit`` 在调用线程非阻塞入队；daemon 线程批量取出并 ``logger.emit``
    到 OTel ``BatchLogRecordProcessor`` 导出。provider 惰性构建（首次
    emit）；DISABLED 不建 provider、不入队。
    """

    def __init__(
        self,
        mode: str = "DISABLED",
        *,
        otlp_endpoint: str | None = None,
        service_name: str = "lca",
        shutdown_timeout_ms: int = 5000,
        queue_size: int = _QUEUE_SIZE_DEFAULT,
        exporter: Any = None,
    ) -> None:
        """构造后端；``exporter`` 仅供测试注入（如 InMemoryLogExporter）。

        precondition：``mode`` 归一后属于 ``_MODES``，违反抛 ``ValueError``；
        注入的 ``exporter`` 归本后端，``shutdown`` 一并关闭。
        """
        self._mode = _normalize_mode(mode)
        self._sharing = _MODE_TO_SHARING[self._mode]
        self._otlp_endpoint = otlp_endpoint
        self._service_name = service_name
        self._shutdown_timeout_ms = shutdown_timeout_ms
        self._exporter_override = exporter
        self._queue: queue.Queue[TelemetryRecord] = queue.Queue(maxsize=max(1, queue_size))
        self._lock = threading.Lock()
        self._dropped_count = 0
        self._disabled_warned = False
        self._started = False
        self._closed = False
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._provider: Any | None = None
        self._logger: Any | None = None

    @property
    def disabled_warned(self) -> bool:
        """DISABLED 模式是否已 warning 过一次（诊断只读）。"""
        with self._lock:
            return self._disabled_warned

    @property
    def dropped_count(self) -> int:
        """队满被丢弃（丢最旧）的记录数（诊断只读）。"""
        with self._lock:
            return self._dropped_count

    @property
    def pending_count(self) -> int:
        """自有队列中待导出的记录数（诊断只读）。"""
        return self._queue.qsize()

    @property
    def sharing(self) -> SharingPolicy:
        """共享披露：``mode`` 直接映射到 :class:`SharingPolicy`。"""
        return self._sharing

    def emit(self, record: TelemetryRecord) -> None:
        """非阻塞入队；DISABLED 丢弃并 warning 一次，其余入自有队列。

        队满丢最旧（``dropped_count`` +1）后重试；永不阻塞/抛错回调用方
        （捕获侧 observer fire 热路径）。``shutdown`` 后的记录直接丢弃。
        """
        if self._sharing == SharingPolicy.DISABLED:
            self._warn_disabled_once()
            return
        with self._lock:
            if self._closed:
                return
        self._enqueue(record)
        self._ensure_started()

    def flush(self) -> None:
        """有界排空提示：等自有队列处理完 + provider force_flush；未启动 no-op。"""
        if not self._started:
            return
        self._drain_queue()
        self._force_flush_provider()

    def shutdown(self) -> None:
        """排空至静止后关闭 provider（幂等，预算 = ``shutdown_timeout_ms``）。

        时序：置停止位 → 有界排空 → force_flush → 关 provider → join worker。
        """
        with self._lock:
            if not self._started or self._closed:
                self._closed = True
                return
            self._closed = True
        self._stop.set()
        self._drain_queue()
        self._force_flush_provider()
        self._shutdown_provider()
        self._join_worker()

    def _drain_queue(self) -> None:
        """有界轮询自有队列直到未完成任务清零或超时。"""
        deadline = time.monotonic() + self._shutdown_timeout_ms / 1000.0
        while self._queue.unfinished_tasks > 0 and time.monotonic() < deadline:
            time.sleep(_POLL_S)

    def _enqueue(self, record: TelemetryRecord) -> None:
        """入队；队满丢最旧（``dropped_count`` +1）后重试一次。"""
        with self._lock:
            try:
                self._queue.put_nowait(record)
                return
            except queue.Full:
                pass
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
                self._dropped_count += 1
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(record)

    def _ensure_started(self) -> None:
        """首次 emit 惰性建 provider + logger + daemon worker（仅一次）。"""
        with self._lock:
            if self._started or self._closed:
                return
            self._provider = self._build_provider()
            self._logger = self._provider.get_logger(_SCOPE)
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._started = True
            self._worker.start()

    def _join_worker(self) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=self._shutdown_timeout_ms / 1000.0)

    def _run(self) -> None:
        """daemon 主循环：批量取队列记录转发 OTel logger，停止位 + 空则退出。"""
        while True:
            batch = self._next_batch()
            if batch is None:
                return
            for record in batch:
                self._export_one(record)
                self._queue.task_done()
            if self._stop.is_set() and self._queue.empty():
                return

    def _next_batch(self) -> list[TelemetryRecord] | None:
        """取一批记录；``None`` = 停止位已置且队列空（worker 退出信号）。"""
        try:
            first = self._queue.get(timeout=_POLL_S)
        except queue.Empty:
            return None if self._stop.is_set() else []
        batch = [first]
        while len(batch) < _MAX_BATCH:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _build_provider(self) -> Any:
        """建 LoggerProvider + BatchLogRecordProcessor（惰性 import，无副作用）。"""
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource

        provider = LoggerProvider(resource=Resource.create({"service.name": self._service_name}))
        provider.add_log_record_processor(BatchLogRecordProcessor(self._build_exporter()))
        return provider

    def _build_exporter(self) -> Any:
        """选 exporter：注入优先 → OTLP（缺包回退）→ no-op + warning。"""
        if self._exporter_override is not None:
            return self._exporter_override
        if self._otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            except ImportError:
                _log.warning("session.telemetry.otlp_exporter_unavailable")
            else:
                return OTLPLogExporter(endpoint=self._otlp_endpoint)
        else:
            _log.warning("session.telemetry.no_otlp_endpoint", service_name=self._service_name)
        return _NoOpExporter()

    def _export_one(self, record: TelemetryRecord) -> None:
        """把一条记录映射到 OTel logger.emit（contained，不抛回 worker）。"""
        logger = self._logger
        if logger is None:
            return
        try:
            logger.emit(
                body=record.body,
                severity_number=_severity_number(record.severity),
                severity_text=record.severity.upper(),
                timestamp=_ms_to_ns(record.time),
                observed_timestamp=_ms_to_ns(record.time),
                attributes=_otel_attributes(record),
            )
        except Exception:
            _log.warning("session.telemetry.logger_emit_failed", exc_info=True)

    def _force_flush_provider(self) -> None:
        provider = self._provider
        if provider is not None:
            with contextlib.suppress(Exception):
                provider.force_flush(timeout_millis=self._shutdown_timeout_ms)

    def _shutdown_provider(self) -> None:
        provider = self._provider
        if provider is not None:
            with contextlib.suppress(Exception):
                provider.shutdown()

    def _warn_disabled_once(self) -> None:
        with self._lock:
            if self._disabled_warned:
                return
            self._disabled_warned = True
        _log.warning("session.telemetry.disabled_drop", mode=self._mode)


class _NoOpExporter:
    """无端点时的空 exporter：吞掉批次并返回 SUCCESS（不产生副作用）。"""

    def export(self, batch: Any) -> Any:
        from opentelemetry.sdk._logs.export import LogRecordExportResult

        return LogRecordExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def shutdown(self) -> None:
        return None


def _ms_to_ns(ms: int) -> int:
    """epoch 毫秒 → 纳秒（OTel log timestamp 单位）。"""
    return int(ms) * 1_000_000


def _otel_attributes(record: TelemetryRecord) -> dict[str, Any]:
    """合并身份属性 + channel；值强制为 OTel 允许的原语（str/int/float/bool）。"""
    attrs: dict[str, Any] = {"telemetry.channel": record.channel}
    for key, value in record.attributes.items():
        attrs[str(key)] = value if isinstance(value, (str, int, float, bool)) else str(value)
    return attrs


def _severity_number(severity: str) -> Any:
    """severity 文本 → OTel :class:`SeverityNumber`（未知回退 INFO）。"""
    from opentelemetry._logs import SeverityNumber

    return {
        "info": SeverityNumber.INFO,
        "warn": SeverityNumber.WARN,
        "error": SeverityNumber.ERROR,
    }.get(str(severity).lower(), SeverityNumber.INFO)


# ── plugin manifest ────────────────────────────────────────────────────


@plugin(
    id="lca.plugins.session.telemetry_otel",
    provides=["session.telemetry.backend.otel"],
    requires=["session.telemetry"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="network",
    description=(
        "OtelTelemetryBackend（DSH session-telemetry-otel）：有界队列 + daemon"
        " 线程把 TelemetryRecord 批量导出到 OTel Logs（LoggerProvider +"
        " BatchLogRecordProcessor）。mode=FULL/FEEDBACK_ONLY/DISABLED 披露共享策略，"
        " 经 attach_backend 绑定捕获缝；提供 session.telemetry.backend.otel。"
    ),
    test_suite="tests/plugins/session/test_telemetry_otel.py",
    functional_group=FunctionalGroup.G12_EVIDENCE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G12_EVIDENCE),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.telemetry",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """OTel 后端 plugin boot（能力可用性驱动）：构造 :class:`OtelTelemetryBackend`
    （惰性 provider，import 无副作用）→ ``soft_get("session.telemetry")`` 拿捕获缝
    ``attach_backend`` 绑定 → provide ``session.telemetry.backend.otel``；
    capture 缺席时 warning，仍 provide（后装载再绑定）。
    """
    backend = OtelTelemetryBackend(
        mode=config.mode,
        otlp_endpoint=config.otlp_endpoint,
        service_name=config.service_name,
        shutdown_timeout_ms=config.shutdown_timeout_ms,
    )
    capture = ctx.soft_get("session.telemetry")
    if capture is None:
        _log.warning("session.telemetry.no_capture", id="lca.plugins.session.telemetry_otel")
    else:
        capture.attach_backend(backend)
    ctx.provide("session.telemetry.backend.otel", backend)
