"""Session 契约 —— DSH 风格 append-only session 真值的最小契约面（PR-3c）。

对齐 deepseek-harness ``packages/core/session/src/types.ts`` + ``index.ts`` 的
SessionHeader / SessionEvent / observer 语义；实现在
:mod:`lca.plugins.session.runtime.session`。

契约边界：

- 本模块只声明数据形态 + Protocol + 错误，不含 log / observer / fold 实现。
- 事件词表开放：``SessionEvent.type`` 是 category 字符串，本契约不做
  close-set 校验（新 category 走 yaml 注册，ADR-0183）。
- ``SessionProtocol.request_header`` 的 fold 复用 :mod:`lca_kernel.events.fold`
  （ADR-0185 PR-0）；``SessionEvent`` 暴露只读 ``category`` / ``payload``
  投影满足 :func:`lca_kernel.events.fold.foldRequestHeader` 的入参形态。

失败语义：契约层不抛错；``SessionReentryError`` 由实现层在嵌套 append 时抛出。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lca_kernel.events.fold import EpochHeader

SESSION_FORMAT_VERSION: int = 0
"""Session header 格式版本（对齐 dsh ``SESSION_FORMAT_VERSION``）。

harness 未发布期固定为 0：不承诺兼容，持久化后端按该值校验加载。
结构性变更（header 形态 / 事件信封 / 核心事件语义）才 bump。
"""


class SessionReentryError(RuntimeError):
    """进行中的 append 尚未结束（observer 正在 fire）时再次 append。

    实现层在 append 入口检测 ``_appending`` 标记后抛出；嵌套调用方
    （通常是 observer 内部再次 append）必须自行处理，外层 append 不受影响。
    """


@dataclass(frozen=True, slots=True)
class SessionHeader:
    """Session 存储元数据（不进事件日志，存储关注点而非可重放会话状态）。

    字段对齐 dsh ``SessionHeader`` 最小集：

    - ``version`` — 创建时盖章 :data:`SESSION_FORMAT_VERSION`
    - ``id`` — session 唯一标识（与所属 Session 的 id 一致）
    - ``created_at`` — 创建时刻 Unix epoch 毫秒（非负整数）
    - ``is_seeded`` — 是否含 fork/重放继承的事件前缀
    """

    version: int
    id: str
    created_at: int
    is_seeded: bool = False


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """Session 日志的一条不可变事件（对齐 dsh ``SessionEvent`` 信封）。

    - ``type`` — 事件 category 字符串（spine category 是本仓原生词表）
    - ``seq`` — 日志内单调连续序号，恒等于入日志时的 ``len(log)``
    - ``time`` — append 时刻 Unix epoch 毫秒
    - ``data`` — JSON 值域 payload；实现层入日志前做无损 JSON 快照，
      读回的 ``data`` 是落日志的值，不是调用方可变输入的引用

    ``category`` / ``payload`` 是只读投影，把信封适配成
    :func:`lca_kernel.events.fold.foldRequestHeader` 的 spine 事件形态；
    不引入第二份状态。
    """

    type: str
    seq: int
    time: int
    data: Mapping[str, Any]

    @property
    def category(self) -> str:
        """spine 事件形态投影：``foldRequestHeader`` 按 category 识别 fold 目标。"""
        return self.type

    @property
    def payload(self) -> Mapping[str, Any]:
        """spine 事件形态投影：``foldRequestHeader`` 从 payload 还原 header 字段。"""
        return self.data


@runtime_checkable
class SessionObserver(Protocol):
    """append 提交后的同步观察者。

    时序：事件已入日志后才被调用；单个观察者抛错被实现层 contained
    （记录后继续下一个），不改变 append 返回值，不阻止后续观察者。
    """

    def __call__(self, session: SessionProtocol, event: SessionEvent) -> None: ...


@runtime_checkable
class SessionProtocol(Protocol):
    """事件溯源 Session 的公开面（对齐 dsh ``Session`` 核心方法集）。

    不变量：

    - 日志是追加式唯一真值；``seq`` 从 0 连续递增（``seq = len(log)``）。
    - ``append`` 在 observer fire 期间拒绝重入（抛 :class:`SessionReentryError`）。
    - ``request_header`` 是 ``foldRequestHeader(snapshot_events())`` 的增量
      等价形态：每条 header 事件只在首次见到时被 fold 一次。
    """

    @property
    def header(self) -> SessionHeader:
        """创建时盖章的不可变存储元数据。"""
        ...

    @property
    def id(self) -> str:
        """session 唯一标识，派生自 ``header.id`` 的单份真值。"""
        ...

    @property
    def seq(self) -> int:
        """下一条事件的序号 —— 恒等于当前日志长度。"""
        ...

    def append(self, event_type: str, data: Mapping[str, Any]) -> SessionEvent:
        """校验 → 入日志 → fire observers（contained）→ 返回落日志的事件。

        precondition：``event_type`` 非空字符串；``data`` 可无损 JSON 序列化。
        失败语义：校验不过抛 ``TypeError`` / ``ValueError``，日志不变；
        observer 抛错被 contained，不影响返回值。重入抛
        :class:`SessionReentryError`，同样不改日志。
        """
        ...

    def snapshot_events(
        self, from_seq: int = 0, to_seq_exclusive: int | None = None
    ) -> tuple[SessionEvent, ...]:
        """半开区间 ``[from_seq, to_seq_exclusive)`` 的不可变事件快照。

        ``to_seq_exclusive`` 缺省 = 当前日志尾。全量快照在下次 append 前
        复用同一对象；已返回的快照不被后续 append 改变。
        """
        ...

    def event_at(self, seq: int) -> SessionEvent | None:
        """按精确序号取事件；不存在返回 ``None``。"""
        ...

    def request_header(self) -> EpochHeader | None:
        """最后一条 header 事件生效后的 :class:`EpochHeader`；无 header 返回 ``None``。

        增量维护：新事件才触发 fold，重复读是 O(1)。
        """
        ...

    def observe(self, observer: SessionObserver) -> Callable[[], None]:
        """注册 append 观察者；返回幂等取消函数。"""
        ...


__all__ = [
    "SESSION_FORMAT_VERSION",
    "SessionEvent",
    "SessionHeader",
    "SessionObserver",
    "SessionProtocol",
    "SessionReentryError",
]
