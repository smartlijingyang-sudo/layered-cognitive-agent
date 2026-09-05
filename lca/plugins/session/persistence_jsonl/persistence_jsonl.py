"""JsonlSessionPersistence —— ADR-0186 PR-3e/3f SessionObserver JSONL 落盘。

DSH ``JsonlSessionPersistence.onEvent()`` 形态的 LCA 实现：作为
:class:`SessionObserver` 注册到 :class:`Session`,把每条 :class:`SessionEvent`
追加写到 ``traces/runs/<session_id>/<session_id>.session.jsonl``,作为
in-process log 的 durable 镜像。

设计要点：

- **观察者形态**：append 提交后才被 fire；``on_session_event`` 只做入队
  (无 I/O),不阻塞生产者;落盘由 write-behind 批量窗口完成。
- **write-behind 落盘**（对齐 DSH ``SessionWriteBehind`` /
  ``docs/specs/session-event-pipeline-spec.md`` §3.2）：
  每 session 一个 :class:`WriteBehindBuffer` + :class:`JsonlFileSink`;
  首条待写事件开固定窗口(默认 200ms),窗口到期批量写(单次 ``flush`` +
  可选 ``fsync``);背景写失败事件保留、暂停自动重试,``flush()`` 显式
  排空并重抛错误(由 :class:`Session.flush` 链记 ``FlushResult(ok=False)``);
  ``close()`` 排空后关闭(幂等)。
- **持久性时序**：无显式 flush 时,事件的持久性以 ``max_delay_ms`` 窗口
  为上界;``Session.flush()`` 是下一动作前的顺序与持久性检查点。
- **JSONL 布局**：每行 = 一个 SessionEvent JSON；header 在文件首行,
  后续行为事件,与 :class:`lca.harness.session.persistence.JsonlSessionPersistence`
  字节布局兼容(``kind`` 字段区分)。**不**复用 :class:`SpineSink`
  的 9-键 ``SpineEventRecord`` 字节布局 —— SessionEvent 是 in-memory
  真值层的形态,经 ``to_dict()`` 走 SessionEvent 信封
  (``type/seq/time/data/session_id/actor/provider/visibility/scope``)。
  路径后缀 ``.session.jsonl``，与 ADR-0183 I-FW-SSOT-1 spine
  (SpineFileSink / SpineEventRecord)分离，无双写风险。
- **flush 链**：:meth:`Session.flush` 经 observer-duck-type 调用
  ``flush(session)``,本实现同步排空该 session 的待写缓冲。

注册路径：``setup`` 在 boot 时把 :class:`JsonlSessionPersistence` 注册到当前
:class:`SessionStore` 的所有活 Session;若 store 提供接管钩子,新 Session
也会自动挂入。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.write_behind import WriteBehindBuffer
from lca_kernel.events.session import SessionEvent, SessionHeader

_log = structlog.get_logger(__name__)

__all__ = ["Config", "JsonlSessionPersistence", "setup"]

_RUNS_ROOT_DEFAULT = "traces/runs"
_HEADER_KIND = "header"
_EVENT_KIND = "event"
_FILE_SUFFIX = ".session.jsonl"
_MAX_DELAY_MS_DEFAULT = 200
"""write-behind 批量窗口缺省值(对齐 DSH ``DEFAULT_WRITE_BATCH_MAX_DELAY_MS``)。"""


class Config(BaseModel):
    """plugin 配置:落盘根目录、批量窗口与 fsync 策略;拒绝未知键。"""

    model_config = {"extra": "forbid"}

    runs_root: str = _RUNS_ROOT_DEFAULT
    """traces/runs 等价基址;每个 session 在其下建子目录。"""

    max_delay_ms: int = Field(default=_MAX_DELAY_MS_DEFAULT, ge=1)
    """write-behind 批量窗口:首条待写事件后的最大等待时间。

    窗口到期或显式 ``flush()`` 时批量落盘;窗口只约束有意的批量等待,
    不约束 ``flush`` 的排空语义。
    """

    fsync: bool = False
    """每批写入后是否额外 ``os.fsync`` 强制落盘。

    每批写入后必然 ``flush`` 到 OS(durable 镜像契约,与开关无关);
    ``fsync=True`` 进一步保证物理介质持久(生产强一致,测试 ``False``)。
    """


class JsonlSessionPersistence:
    """``SessionObserver`` JSONL 落盘实现(ADR-0186 PR-3e/3f)。

    与 :class:`lca.harness.session.persistence.JsonlSessionPersistence` 的差异：

    - **直接吃 SessionEvent**：不再走 ``SessionPersistence`` 工厂,
      observer 入口 = ``on_session_event(session, event)``,只入队不写盘。
    - **提供 ``register_to`` 方法**：把 observer 挂到给定 Session,
      返回幂等取消函数。
    - **提供 ``flush`` / ``close`` 方法**：排空/关闭 per-session
      write-behind 缓冲;``Session.flush()`` observer-duck-type 链经此落盘。
    - **路径决定**：``traces/runs/<session_id>/<session_id>.session.jsonl``,
      session_id 取自 Session.id。
    """

    def __init__(
        self,
        runs_root: Path | str | None = None,
        *,
        fsync: bool = False,
        max_delay_ms: int = _MAX_DELAY_MS_DEFAULT,
    ) -> None:
        """构造 detached observer。

        precondition：``runs_root`` 是可写目录的基址；缺省 = ``Path("traces/runs")``;
        ``max_delay_ms >= 1``(违反由 :class:`WriteBehindBuffer` 抛 ``ValueError``)。
        失败语义：实例化阶段不创建文件；目录在首批落盘时按需建立。
        """
        self._runs_root = Path(runs_root) if runs_root is not None else Path(_RUNS_ROOT_DEFAULT)
        self._fsync = bool(fsync)
        self._max_delay_ms = max_delay_ms
        self._buffers: dict[str, WriteBehindBuffer] = {}
        self._lock = threading.Lock()
        self._header_written: set[str] = set()
        # SessionStore.add_observer_hook 返回的反注册闭包；全量 close 时释放。
        self._store_hooks: list[Callable[[], None]] = []

    # ── 公开面 ──────────────────────────────────────────────────────

    def on_session_event(self, session: Any, event: SessionEvent) -> None:
        """``SessionObserver`` 协议入口。

        时序：事件已入日志后被 Session 调用;本方法仅把序列化后的行入队
        (无 I/O,不阻塞生产者)。落盘失败由 write-behind 保留事件并暂停
        自动重试,不回滚已提交的 append。
        """
        session_id = _session_id(session, event)
        with self._lock:
            buffer = self._buffer_for(session_id)
            header_needed = session_id not in self._header_written
            if header_needed:
                self._header_written.add(session_id)
        if buffer is None:
            return
        if header_needed:
            header = _header_for(session, session_id)
            if header is not None:
                buffer.enqueue(_header_payload(header))
        buffer.enqueue(_session_event_to_dict(event))

    def register_to(self, session: Any) -> Any:
        """把 observer 挂到给定 Session;返回 ``Session.observe`` 的取消函数。

        注册的是 :class:`_ObserverAdapter` 对象(不是裸绑定方法):
        ``__call__`` 接 append 事件,``flush`` 接 :meth:`Session.flush` 的
        observer-duck-type 探测——否则显式 flush 链到不了本实现的排空面。
        """
        return session.observe(_ObserverAdapter(self))

    def flush(self, session_id: str | None = None) -> None:
        """排空待写缓冲到磁盘(阻塞);``session_id`` 缺省 = 全量。

        ``session_id`` 也接受 Session-like对象:``Session.flush()`` 的
        observer-duck-type 链以 ``observer.flush(session)`` 形态调用,
        此处经 ``.id`` 归一为 session id(ADR-0186 flush 链)。

        失败语义:批写入失败时重抛(事件已保留在缓冲),由
        :class:`Session.flush` 链记 ``FlushResult(ok=False)``。
        """
        with self._lock:
            targets = self._select(_normalize_session_key(session_id))
        for _, buffer in targets:
            buffer.flush()

    def close(self, session_id: str | None = None) -> None:
        """排空 + 关闭缓冲;``session_id`` 缺省 = 全量(接受同 :meth:`flush` 的归一)。

        全量 close 同时释放 ``SessionStore.add_observer_hook`` 反注册闭包；
        per-session close 不动 store 接管。close 后同 session 再来事件时
        按需重建缓冲(追加模式,不覆盖已落盘内容)。
        """
        with self._lock:
            targets = self._select(_normalize_session_key(session_id))
            for sid, buffer in targets:
                try:
                    buffer.dispose()
                finally:
                    self._buffers.pop(sid, None)
                    self._header_written.discard(sid)
        if session_id is None:
            for cancel in self._store_hooks:
                cancel()
            self._store_hooks.clear()

    def local_path(self, session_id: str) -> Path:
        """返回 ``session_id`` 对应的落盘路径(不创建文件)。"""
        return self._runs_root / session_id / f"{session_id}{_FILE_SUFFIX}"

    def pending_count(self, session_id: str) -> int:
        """该 session 待写事件数(诊断只读;未知 session = 0)。"""
        with self._lock:
            buffer = self._buffers.get(session_id)
        if buffer is None:
            return 0
        return buffer.pending_count

    # ── 内部 ────────────────────────────────────────────────────────

    def _select(self, session_id: str | None) -> list[tuple[str, WriteBehindBuffer]]:
        if session_id is None:
            return list(self._buffers.items())
        single = self._buffers.get(session_id)
        return [(session_id, single)] if single is not None else []

    def _buffer_for(self, session_id: str) -> WriteBehindBuffer | None:
        """取(或按需创建)session 的 write-behind 缓冲(持锁调用)。

        文件句柄在首批落盘时才由 :class:`JsonlFileSink` 惰性打开;
        打开/写入失败在批写入时经 ``on_failure`` 记录,事件保留待重试。
        """
        existing = self._buffers.get(session_id)
        if existing is not None and not existing.is_closed:
            return existing
        sink = JsonlFileSink(self.local_path(session_id), fsync=self._fsync)
        buffer = WriteBehindBuffer(
            sink,
            max_delay_ms=self._max_delay_ms,
            on_failure=self._make_on_failure(session_id),
        )
        self._buffers[session_id] = buffer
        return buffer

    def _make_on_failure(self, session_id: str) -> Callable[[Exception], None]:
        def _on_failure(exc: Exception) -> None:
            _log.warning(
                "session.persistence.batch_write_failed",
                session_id=session_id,
                path=str(self.local_path(session_id)),
                error=str(exc),
                exc_info=exc,
            )

        return _on_failure


class _ObserverAdapter:
    """把 :class:`JsonlSessionPersistence` 装成 Session observer 的适配器。

    ``__call__`` 承接 append 事件;``flush`` 承接 :meth:`Session.flush` 的
    duck-type 探测(同步排空,失败重抛由 flush 链记 ``FlushResult(ok=False)``)。
    """

    def __init__(self, persistence: JsonlSessionPersistence) -> None:
        self._persistence = persistence

    def __call__(self, session: Any, event: SessionEvent) -> None:
        self._persistence.on_session_event(session, event)

    def flush(self, session: Any) -> None:
        self._persistence.flush(session)


def _header_payload(header: SessionHeader) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": _HEADER_KIND, **asdict(header)}
    # ADR-0187 §3 D7 session-level assistant binding (PR-5).
    # ``assistant_id`` is an additive JSONL field: when present and
    # non-empty, the header advertises the binding; ``None`` / whitespace
    # is omitted to keep pre-PR-5 byte layout unchanged. Readers tolerate
    # absence (forward-compatible).
    assistant_id = payload.get("assistant_id")
    if not (isinstance(assistant_id, str) and assistant_id.strip()):
        payload.pop("assistant_id", None)
    return payload


# ── helpers ────────────────────────────────────────────────────────────


def _normalize_session_key(value: object) -> str | None:
    """把 flush / close 入参归一为 session id。

    - ``None`` → ``None``(全量);
    - ``str`` → 原样;
    - Session-like(带 ``.id``)→ ``.id``(:class:`Session.flush` 的
      observer-duck-type 链传 Session 对象,见 ADR-0186 flush 链);
    - 其它形态 → 原样透传(查不到文件时 no-op,与既有语义一致)。
    """
    if value is None or isinstance(value, str):
        return value
    sid = getattr(value, "id", None)
    if isinstance(sid, str) and sid:
        return sid
    return str(value)


def _session_id(session: Any, event: SessionEvent) -> str:
    """从 Session 实例派生 session_id;Session 缺 id 属性时回退 ``event.session_id``。

    Session 协议保证 :attr:`Session.id` 派生自 :attr:`SessionHeader.id`,
    与 :attr:`SessionEvent.session_id`(契约层可选字段)未必同源 —— 本
    plugin 优先 Session 实例权威。
    """
    sid = getattr(session, "id", None)
    if isinstance(sid, str) and sid:
        return sid
    return event.session_id or "unknown"


def _header_for(session: Any, session_id: str) -> SessionHeader | None:
    """从 Session 取 header;缺省时构造最小 header(仅 version + id + created_at=0)。

    ADR-0187 §3 D7 binding（PR-5）：Session 实例可能携带 ``assistant_id``
    属性（由 routing 层 session 创建时绑定），保留进 SessionHeader；
    缺省 = None（fail-open 旧 session）。
    """
    header = getattr(session, "header", None)
    if isinstance(header, SessionHeader):
        return header
    if header is not None:
        try:
            assistant_id = getattr(header, "assistant_id", None)
            if isinstance(assistant_id, str):
                assistant_id = assistant_id.strip() or None
            return SessionHeader(
                version=int(getattr(header, "version", 0)),
                id=str(getattr(header, "id", session_id)),
                created_at=int(getattr(header, "created_at", 0)),
                is_seeded=bool(getattr(header, "is_seeded", False)),
                assistant_id=assistant_id,
            )
        except (TypeError, ValueError):
            return None
    return None


def _session_event_to_dict(event: SessionEvent) -> dict[str, Any]:
    """SessionEvent → JSONL 字节布局。

    字段顺序固定(``kind`` 在前便于 reader 单行分类);``scope`` 是
    Optional[:class:`EventScope`],JSON 序列化时走 dataclasses.asdict。
    """
    payload: dict[str, Any] = {
        "kind": _EVENT_KIND,
        "type": event.type,
        "seq": event.seq,
        "time": event.time,
        "data": event.data,
    }
    session_id = getattr(event, "session_id", None)
    if session_id:
        payload["session_id"] = session_id
    actor = getattr(event, "actor", None)
    if actor is not None:
        payload["actor"] = actor
    provider = getattr(event, "provider", None)
    if provider is not None:
        payload["provider"] = provider
    visibility = getattr(event, "visibility", None)
    if visibility is not None:
        payload["visibility"] = visibility
    scope = getattr(event, "scope", None)
    if scope is not None:
        payload["scope"] = asdict(scope) if hasattr(scope, "__dataclass_fields__") else scope
    return payload


# ── plugin manifest ────────────────────────────────────────────────────


@plugin(
    id="lca.plugins.session.persistence_jsonl",
    provides=["session.persistence.jsonl"],
    requires=["session.store"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="filesystem",
    description=(
        "JsonlSessionPersistence（ADR-0186 PR-3e/3f）：SessionObserver 形态的"
        " JSONL 落盘；写 traces/runs/<session_id>/<session_id>.session.jsonl。"
        "挂到 session.store 当前活 Session；observer 失败由 Session contained。"
        "提供 session.persistence.jsonl capability。"
    ),
    test_suite="tests/plugins/session/test_persistence_jsonl.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.store",),
        emits=(),
        state_mutation="reducer-only",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """SessionObserver JSONL 落盘 plugin boot。

    行为契约：

    1. 构造一个 :class:`JsonlSessionPersistence` 实例;
    2. 从 ``session.store`` 拿到活 Session,observer 挂入每个;
    3. 把实例以 ``session.persistence.jsonl`` capability 提供,
       供后续 flush / close / 文件路径读取。

    失败语义：``session.store`` 未装载时 no-op(不抛),保留 capability
    让测试可在装载 session.store 后再注册。生产 profile 解析保证
    ``session.store`` 在本 plugin 之前 boot。
    """
    persistence = JsonlSessionPersistence(
        runs_root=config.runs_root,
        fsync=config.fsync,
        max_delay_ms=config.max_delay_ms,
    )
    ctx.provide("session.persistence.jsonl", persistence)
    register_to_session_store(ctx, persistence)


def register_to_session_store(ctx: PluginContext, persistence: JsonlSessionPersistence) -> None:
    """把 observer 挂到当前 SessionStore(活 Session + 未来新 Session)。

    SessionStore 未装载时 no-op(保留 capability 供测试后注册);装载时
    经 ``add_observer_hook`` 接管未来 ``create`` / ``restore`` 的 Session,
    并对当前活 Session 一次性挂入(兜底已存在条目)。
    """
    store = ctx.soft_get("session.store")
    if store is None:
        _log.info(
            "session.persistence.no_store",
            id="lca.plugins.session.persistence_jsonl",
        )
        return
    _attach_to_store(store, persistence)


def _attach_to_store(store: Any, persistence: JsonlSessionPersistence) -> None:
    """对 store 当前活 Session 注册 observer,并接管未来创建的新 Session。

    时序:先对 ``store.list()`` 现存 Session 一次性 ``register_to``(restore
    hook 不重放已存在条目的补偿),再经 ``store.add_observer_hook`` 接管未来
    ``create`` / ``restore``。
    失败语义:``store`` 未提供 ``add_observer_hook`` 时抛 ``TypeError``
    (fail-loud,禁止静默降级成"只挂当前活 Session");单个 Session 挂入
    失败 contained(记 warning,继续其余)。
    """
    for session in getattr(store, "list", lambda: ())():
        try:
            persistence.register_to(session)
        except Exception:
            _log.warning(
                "session.persistence.attach_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)

    def _on_create(session: Any) -> None:
        try:
            persistence.register_to(session)
        except Exception:
            _log.warning(
                "session.persistence.attach_failed",
                session_id=getattr(session, "id", None),
                exc_info=True,
            )

    cancel = hook(_on_create)
    if callable(cancel):
        persistence._store_hooks.append(cancel)
