"""SessionTelemetryCapture —— DSH ``SessionTelemetryCoordinator`` 一比一 LCA 实现。

对齐 deepseek-harness ``packages/session/session-telemetry/src/coordinator.ts``
的捕获缝职责：投影已提交 Session 事件为 :class:`TelemetryRecord`，出站前过
脱敏钩子，再交给 :class:`SessionTelemetryBackend`。观察面派生物（AGENTS.md
§2.3 / C7）：只读事件，canonical 日志永不被改写；后端错误全部 contained，
永不反噬 ``Session.append`` 或打断其他消费者（C3/C9）。

捕获两模式（DSH ``SessionTelemetryCapture``）：``live`` 经 ``Session.observe``
订阅已提交事件逐条交付；``on_demand`` 不订阅，反馈触发
:meth:`SessionTelemetryCapture.capture_session` 时按 per-session 游标
(last_handoff_seq) 释放后缀。

与 DSH 的显式差异：脱敏走 :meth:`register_redactor` 钩子注册表（顺序管道）
而非 cordis ``session-telemetry/record`` waterfall（LCA 无等价全局钩子总线），
fail-closed 语义一致；无 backend 时记录丢弃并计数（能力可用性驱动，backend
plugin 装载后经 :meth:`attach_backend` 绑定）；游标在每条已消费记录后推进
（``capture_session`` 幂等），仅 ``backend.emit`` 抛错不推进以便重试 ——
DSH 对扣下记录也不推进（重复重放再扣下），LCA 视脱敏扣下为终局。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import structlog
from pydantic import BaseModel, field_validator

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
    CHANNEL_LEDGER,
    RedactionHook,
    SessionTelemetryBackend,
    SharingPolicy,
    TelemetryRecord,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.events.session import SessionEvent

_log = structlog.get_logger(__name__)

__all__ = ["Config", "SessionTelemetryCapture", "attach_to_session_store", "setup"]

_CAPTURE_MODES: frozenset[str] = frozenset({"live", "on_demand"})
_CURSOR_INIT: int = -1
"""on_demand 游标初值：尚未交付任何 seq（seq 从 0 起）。"""

# 单条记录的出站结局：决定 on_demand 游标是否推进（backend_error 不推进 → 重试）。
_DELIVERED: str = "delivered"
_REDACTED: str = "redacted"
_DROPPED: str = "dropped"
_BACKEND_ERROR: str = "backend_error"


class Config(BaseModel):
    """plugin 配置：捕获模式；拒绝未知键防声明漂移。"""

    model_config = {"extra": "forbid"}

    capture_mode: str = "live"
    """``live`` 订阅已提交事件即交付；``on_demand`` 仅反馈触发时释放。"""

    @field_validator("capture_mode")
    @classmethod
    def _validate_capture_mode(cls, value: str) -> str:
        if value not in _CAPTURE_MODES:
            msg = f"capture_mode 必须是 {sorted(_CAPTURE_MODES)} 之一, got {value!r}"
            raise ValueError(msg)
        return value


class SessionTelemetryCapture:
    """捕获协调器：事件投影 → 脱敏 → 后端交付（DSH coordinator 形态）。

    线程模型：``Session.append`` 在 observer fire 线程同步调用本类，
    :meth:`capture_session` 由反馈处理方调用；内部状态一把锁保护，交付
    非阻塞（后端 ``emit`` 契约 = 入队）。
    """

    def __init__(
        self,
        backend: SessionTelemetryBackend | None = None,
        capture_mode: str = "live",
    ) -> None:
        """构造协调器；``backend`` 缺省 = 未绑定（记录丢弃并计数）。

        precondition：``capture_mode`` in ``{"live", "on_demand"}``，违反抛
        ``ValueError``（fail-loud，禁止静默降级成 live）。
        """
        if capture_mode not in _CAPTURE_MODES:
            msg = f"capture_mode 必须是 {sorted(_CAPTURE_MODES)} 之一, got {capture_mode!r}"
            raise ValueError(msg)
        self._backend = backend
        self._capture_mode = capture_mode
        self._lock = threading.Lock()
        self._hooks: list[RedactionHook] = []
        self._cursors: dict[str, int] = {}
        self._redacted_count = 0
        self._backend_error_count = 0
        self._dropped_count = 0
        self._store_hooks: list[Callable[[], None]] = []

    # ── 公开面 ──────────────────────────────────────────────────────

    @property
    def backend(self) -> SessionTelemetryBackend | None:
        """当前绑定的后端；未绑定 = ``None``。"""
        return self._backend

    @property
    def backend_error_count(self) -> int:
        """``backend.emit`` 抛错被 contained 的次数（诊断只读）。"""
        with self._lock:
            return self._backend_error_count

    @property
    def capture_mode(self) -> str:
        """捕获模式（构造后不变）。"""
        return self._capture_mode

    @property
    def dropped_count(self) -> int:
        """无后端时被丢弃的记录数（诊断只读）。"""
        with self._lock:
            return self._dropped_count

    @property
    def redacted_count(self) -> int:
        """被脱敏钩子扣下的记录数（fail-closed；诊断只读）。"""
        with self._lock:
            return self._redacted_count

    @property
    def sharing(self) -> SharingPolicy:
        """共享披露：透传后端策略；未绑定后端 = ``DISABLED`` 语义。"""
        backend = self._backend
        if backend is None:
            return SharingPolicy.DISABLED
        return backend.sharing

    def attach_backend(self, backend: SessionTelemetryBackend) -> None:
        """绑定后端（能力可用性驱动：backend plugin setup 调用）。

        只影响后续交付；on_demand 游标不回退，未释放后缀在下次
        :meth:`capture_session` 时按新后端交付。
        """
        self._backend = backend

    def capture_session(self, session: Any, up_to_seq: int | None = None) -> int:
        """on_demand 释放：游标之后到 ``up_to_seq``（含）的记录交给后端。

        反馈触发时读 canonical 日志快照，逐条投影 → 脱敏 → 交付；缺省
        释放到日志尾。单条失败 contained，不打断同一次重放的其余记录。
        游标推进到本次处理末尾，重复调用幂等。返回释放到后端的记录数。
        """
        session_id = _session_id(session)
        with self._lock:
            cursor = self._cursors.get(session_id, _CURSOR_INIT)
        delivered = 0
        for event in session.snapshot_events():
            if event.seq <= cursor:
                continue
            if up_to_seq is not None and event.seq > up_to_seq:
                break
            outcome = self._release(session_id, event)
            if outcome == _DELIVERED:
                delivered += 1
            if outcome != _BACKEND_ERROR:
                with self._lock:
                    self._cursors[session_id] = event.seq
        return delivered

    def flush(self) -> None:
        """可选提示透传给后端（contained；后端缺省空实现）。"""
        backend = self._backend
        if backend is None:
            return
        try:
            backend.flush()
        except Exception:
            self._count_backend_error()
            _log.warning("session.telemetry.backend_flush_failed", exc_info=True)

    def observe_session(self, session: Any) -> Callable[[], None]:
        """live 订阅：把已提交事件观察者挂到给定 Session。

        返回 ``Session.observe`` 的幂等取消函数。on_demand 模式不订阅
        （canonical 日志即缓冲），返回 no-op 取消函数。

        ``FEEDBACK_ONLY`` 共享策略:live 也不逐条外送,仅在见到
        ``feedback.record.v1`` 时释放未释放前缀(DSH coordinator 对位)。
        """
        if self._capture_mode != "live":
            return lambda: None

        backend = self._backend
        if backend is not None and backend.sharing == SharingPolicy.FEEDBACK_ONLY:

            def _feedback_observer(sess: Any, event: SessionEvent) -> None:
                if event.type != "feedback.record.v1":
                    return
                self._contain(lambda: self.capture_session(sess, event.seq))

            return session.observe(_feedback_observer)

        def _observer(sess: Any, event: SessionEvent) -> None:
            self._contain(lambda: self._release(_session_id(sess), event))

        return session.observe(_observer)

    def register_redactor(self, hook: RedactionHook) -> Callable[[], None]:
        """注册脱敏钩子；返回幂等取消函数。

        每条记录出站前按注册顺序过全部钩子；任一钩子返回 ``None`` 或
        抛错 → 扣下该条并计数（fail-closed），其余记录不受影响。
        """
        with self._lock:
            self._hooks.append(hook)

        def _cancel() -> None:
            with self._lock:
                if hook in self._hooks:
                    self._hooks.remove(hook)

        return _cancel

    def shutdown(self) -> None:
        """转发停机给后端：排空至静止（失败 warning，不阻断 teardown）。"""
        backend = self._backend
        if backend is None:
            return
        try:
            backend.shutdown()
        except Exception:
            self._count_backend_error()
            _log.warning("session.telemetry.backend_shutdown_failed", exc_info=True)

    def reset_handoff_cursor(self, session_id: str, *, through_seq: int) -> None:
        """fork/seed 后重置 on_demand 游标,避免重复外送祖先前缀(DSH 对位)。"""
        with self._lock:
            self._cursors[session_id] = through_seq

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """披露面：共享策略 + 丢弃/脱敏/后端错误计数（Wave 3.3）。"""
        with self._lock:
            sharing = self.sharing.value
            return {
                "capture_mode": self._capture_mode,
                "sharing": sharing,
                "redacted_count": self._redacted_count,
                "dropped_count": self._dropped_count,
                "backend_error_count": self._backend_error_count,
            }

    # ── 内部 ────────────────────────────────────────────────────────

    def _apply_redactors(self, record: TelemetryRecord) -> TelemetryRecord | None:
        """顺序过全部钩子；``None`` / 抛错 = 扣下该条（fail-closed）。"""
        with self._lock:
            hooks = tuple(self._hooks)
        current = record
        for hook in hooks:
            try:
                result = hook(current)
            except Exception:
                result = None
            if result is None:
                with self._lock:
                    self._redacted_count += 1
                return None
            current = result
        return current

    def _contain(self, step: Callable[[], None]) -> None:
        """捕获侧单步 contained：任何异常不得逃逸到 observer fire 链。"""
        try:
            step()
        except Exception:
            _log.warning("session.telemetry.capture_step_failed", exc_info=True)

    def _count_backend_error(self) -> None:
        with self._lock:
            self._backend_error_count += 1

    def _deliver(self, record: TelemetryRecord) -> str:
        """把脱敏后的记录交给后端；返回出站结局。

        无后端 = 丢弃并计数 → ``"dropped"``；``emit`` 抛错 contained 计数
        → ``"backend_error"``（on_demand 游标不推进以便重试）；成功 →
        ``"delivered"``。
        """
        backend = self._backend
        if backend is None:
            with self._lock:
                self._dropped_count += 1
            return _DROPPED
        try:
            backend.emit(record)
            return _DELIVERED
        except Exception:
            self._count_backend_error()
            _log.warning(
                "session.telemetry.backend_emit_failed",
                channel=record.channel,
                exc_info=True,
            )
            return _BACKEND_ERROR

    def _project(self, session_id: str, event: SessionEvent) -> TelemetryRecord:
        """固定投影：账本记录 = 事件信封的最小镜像（body 取事件 type）。"""
        attributes = {"session.id": session_id, "event.type": event.type, "event.seq": event.seq}
        return TelemetryRecord(
            channel=CHANNEL_LEDGER,
            time=event.time,
            severity="info",
            attributes=attributes,
            body=event.type,
        )

    def _release(self, session_id: str, event: SessionEvent) -> str:
        """投影 → 脱敏 → 交付一条事件；返回出站结局。"""
        record = self._apply_redactors(self._project(session_id, event))
        if record is None:
            return _REDACTED
        return self._deliver(record)


def _session_id(session: Any) -> str:
    """从 Session 实例取 id；缺 id 属性时回退 ``"unknown"``。"""
    sid = getattr(session, "id", None)
    if isinstance(sid, str) and sid:
        return sid
    return "unknown"


@plugin(
    id="lca.plugins.session.telemetry_capture",
    provides=["session.telemetry"],
    requires=["session.store"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="network",
    description=(
        "SessionTelemetryCapture（DSH session-telemetry 捕获缝）：投影已提交"
        " Session 事件为 TelemetryRecord，过脱敏钩子后交给绑定的"
        " SessionTelemetryBackend；live 订阅 / on_demand 反馈释放两模式。"
        "后端错误 contained，canonical 日志只读。提供 session.telemetry capability。"
    ),
    test_suite="tests/plugins/session/test_telemetry_capture.py",
    functional_group=FunctionalGroup.G12_EVIDENCE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G12_EVIDENCE),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.store",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """遥测捕获 plugin boot。

    行为契约：构造 :class:`SessionTelemetryCapture`（无 backend；记录丢弃
    并计数，``sharing`` = DISABLED 语义）→ 以 ``session.telemetry``
    capability 提供 → live 模式挂 ``session.store``（现存 + 未来 Session）。
    能力可用性驱动：backend plugin 装载后经 ``ctx.soft_get("session.telemetry")``
    拿本服务并调 ``attach_backend`` 绑定。``session.store`` 未装载时 no-op
    （不抛），capability 仍提供。
    """
    capture = SessionTelemetryCapture(capture_mode=config.capture_mode)
    ctx.provide("session.telemetry", capture)
    attach_to_session_store(ctx, capture)


def attach_to_session_store(ctx: PluginContext, capture: SessionTelemetryCapture) -> None:
    """live 模式把观察者挂到当前 SessionStore（活 Session + 未来新 Session）。

    on_demand 不订阅（canonical 日志即缓冲），直接返回；``session.store``
    未装载时 no-op（保留 capability 供测试后注册）。
    """
    if capture.capture_mode != "live":
        return
    store = ctx.soft_get("session.store")
    if store is None:
        _log.info("session.telemetry.no_store", id="lca.plugins.session.telemetry_capture")
        return
    _attach_to_store(store, capture)


def _observe_contained(capture: SessionTelemetryCapture, session: Any) -> None:
    """挂入单个 Session，失败 contained（记 warning，不打断其余）。"""
    try:
        capture.observe_session(session)
        _seed_telemetry_cursor(capture, session)
    except Exception:
        _log.warning(
            "session.telemetry.attach_failed",
            session_id=getattr(session, "id", None),
            exc_info=True,
        )


def _seed_telemetry_cursor(capture: SessionTelemetryCapture, session: Any) -> None:
    """fork/restore 的 seeded session 从 seed 边界后开始计量/外送。"""
    header = getattr(session, "header", None)
    if header is None or not getattr(header, "is_seeded", False):
        return
    seed_length = getattr(header, "seed_length", None)
    if not isinstance(seed_length, int) or seed_length <= 0:
        return
    capture.reset_handoff_cursor(_session_id(session), through_seq=seed_length - 1)


def _attach_to_store(store: Any, capture: SessionTelemetryCapture) -> None:
    """对 store 现存 Session 订阅，并经 ``add_observer_hook`` 接管未来 Session。

    失败语义：``store`` 未提供 ``add_observer_hook`` 时抛 ``TypeError``
    （fail-loud，与 persistence_jsonl 一致）。
    """
    for session in getattr(store, "list", lambda: ())():
        _observe_contained(capture, session)
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)
    cancel = hook(lambda session: _observe_contained(capture, session))
    if callable(cancel):
        capture._store_hooks.append(cancel)
