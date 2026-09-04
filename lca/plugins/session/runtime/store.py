"""SessionStore —— in-memory Session 仓库（PR-3c 骨架）。

对齐 deepseek-harness ``packages/core/session/src/index.ts`` ``SessionStore``
的 create / get / dispose 核心；dsh 的 prepare / enter / announce / fork 与
cordis fiber 生命周期绑定，由后续 PR 按 LCA 装配需要叠加。

持久化不在本层（dsh 边界一致）：persistence 是订阅者关注点，订阅
session 事件流自行落盘；store 只持有活 Session 索引。

restore（ADR-0186）：从持久化层或父 session fork 重建 in-memory session，
带 ``is_seeded=True`` 标记、预填充事件日志、不触发 observer 派发。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence

import structlog

from lca.plugins.session.runtime.session import Session
from lca_kernel.events.fold import foldRequestHeader
from lca_kernel.events.session import SessionEvent, SessionHeader

__all__ = ["SessionStore"]

_log = structlog.get_logger("lca.session.store")


class SessionStore:
    """活 Session 的进程内索引：创建、查找、移除。

    id 策略对齐 dsh：显式 id 冲突抛错；缺省 id 按 ``session-<n>`` 单调
    递增并跳过已占用值。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._counter = 0
        self._creation_hooks: list[Callable[[Session], None]] = []

    def add_observer_hook(self, hook: Callable[[Session], None]) -> Callable[[], None]:
        """注册「新 Session 诞生」的 fan-out 回调；返回幂等反注册函数。

        时序：此后每个经 :meth:`create` / :meth:`restore` 入仓的 Session 都
        同步调一次 ``hook(session)``。``restore`` 路径不重放 seed 事件——
        hook 侧只拿 Session 引用（典型用法：``session.observe(...)`` 接管
        之后的 append 落盘）；对已存在 Session 的补偿由注册方自行 ``list()``。

        失败语义：单个 hook 抛错 contained（记 warning，不打断其他 hook 与
        Session 入仓），与 :meth:`Session.append` 的 observer 失败形态一致。
        所有权：返回的闭包幂等；重复调用不再移除。
        """
        self._creation_hooks.append(hook)

        def _cancel() -> None:
            with contextlib.suppress(ValueError):
                self._creation_hooks.remove(hook)

        return _cancel

    def _fanout_creation_hooks(self, session: Session) -> None:
        for hook in tuple(self._creation_hooks):
            try:
                hook(session)
            except Exception:
                _log.warning(
                    "session_store.creation_hook_failed",
                    session_id=session.id,
                    exc_info=True,
                )

    def create(self, session_id: str | None = None) -> Session:
        """创建并入仓一个 Session。

        precondition：``session_id`` 缺省时自动发号；显式 id 不得与活
        session 冲突。失败语义：冲突抛 ``ValueError``。
        所有权：返回的 Session 即仓内实例（``get`` 按同一对象返回）。
        """
        if session_id is None:
            while True:
                self._counter += 1
                candidate = f"session-{self._counter}"
                if candidate not in self._sessions:
                    session_id = candidate
                    break
        elif session_id in self._sessions:
            raise ValueError(f"session {session_id!r} 已存在")
        session = Session(session_id)
        self._sessions[session_id] = session
        self._fanout_creation_hooks(session)
        return session

    def restore(
        self,
        session_id: str,
        header: SessionHeader,
        events: Sequence[SessionEvent],
    ) -> Session:
        """从持久化或 fork 重建 session：预填事件日志，不入 observer 派发。

        precondition：

        - ``session_id`` 非空，不与活 session 冲突（冲突抛 ``ValueError``）。
        - ``header.id`` 必须等于 ``session_id``。
        - ``events`` 必须连续：``event.seq == index`` 且 ``event.type`` 非空；
          违反抛 ``ValueError``。

        时序：seed 期间不触发任何 observer / flush listener；``header.is_seeded``
        被强制为 ``True``（无论传入值）。header fold 从 seed 事件初始化，
        首次 ``request_header()`` 不需重算。
        """
        if session_id in self._sessions:
            raise ValueError(f"session {session_id!r} 已存在")
        if header.id != session_id:
            raise ValueError(f"header.id {header.id!r} 与 session_id {session_id!r} 不一致")

        session = Session(session_id, header=header)
        for index, event in enumerate(events):
            if event.seq != index:
                raise ValueError(f"seed 事件 seq 不连续: 期望 {index}, 实际 {event.seq}")
            if not event.type:
                raise ValueError(f"seed 事件 #{index} type 为空")
            session._log.append(event)
        # 强制 is_seeded=True（无论传入 header 的值）
        object.__setattr__(session._header, "is_seeded", True)

        # header fold 冷启动：从 seed 事件初始化，首读 O(1)。
        session._header_fold = foldRequestHeader(tuple(events))
        session._header_fold_seq = len(events)

        self._sessions[session_id] = session
        # Fan-out 只交付 Session 引用供接管之后的 append；seed 事件本身
        # 不重放给 observer（restore 时序契约）。
        self._fanout_creation_hooks(session)
        return session

    def get(self, session_id: str) -> Session | None:
        """查活 Session；不存在返回 ``None``（不抛）。"""
        return self._sessions.get(session_id)

    def dispose(self, session_id: str) -> bool:
        """从仓内移除 Session；返回是否移除了活条目。

        移除后 Session 对象变 detached（仍可读写自身日志，不再被 ``get``
        命中）。重复 dispose 返回 ``False``，不抛。
        """
        return self._sessions.pop(session_id, None) is not None

    def list(self) -> tuple[Session, ...]:
        """全部活 Session，按创建顺序；返回新 tuple，改它不影响仓。"""
        return tuple(self._sessions.values())

    def __repr__(self) -> str:
        return f"SessionStore(live={len(self._sessions)})"
