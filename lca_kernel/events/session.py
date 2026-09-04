"""Session 契约 —— ADR-0185 PR-3a。

对齐 deepseek-harness ``packages/core/session/src/types.ts`` + ``index.ts``
的 Session / SessionHeader / SessionEvent 语义;只写契约,不写 Session 实现类。

DSH Session 拥有 in-memory log 真值;fold 是纯函数离线重建。本模块定义:

- :class:`SessionHeader` —— 不可变存储元数据(version / id / 创建时间 / 谱系)
- :class:`SessionEvent` —— 不可变日志条目(seq / time / type / data)
- :class:`SessionObserver` Protocol —— ``on_session_event`` 观察入口
- :class:`SessionProtocol` Protocol —— Session 公开面(id / header / event_count /
  event_at / snapshot_events / append / request_header / step_tree)
- :class:`SessionReentryError` —— append 重入守卫异常

设计原则:

- 全部 frozen + slots,与 :mod:`lca_kernel.events.fold` 的 ``EpochHeader`` 一致
- Protocol 不含实现;SessionProtocol 描述 Session 实现的公开面,
  实现类在 PR-3b 引入
- ``SessionEvent.type`` 用字符串(对齐 DSH discriminated union),
  LCA 不引入额外枚举层
- 与 spine SpineEventRecord 解耦:SessionEvent 是 in-memory log 形态,
  SpineEventRecord 是落盘字节布局;两者通过 projection 映射

delete-when:PR-3b 实现 Session 类后,Protocol 转为 concrete class 的
structural supertype 检查;tracking ADR-0185 PR-3。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SessionHeader:
    """不可变存储元数据(对齐 DSH ``SessionHeader``)。

    字段语义:

    - ``version`` —— 磁盘格式版本,创建时打戳,加载时校验
    - ``id`` —— Session 唯一标识
    - ``created_at`` —— 创建时间(epoch 秒)
    - ``cwd`` —— 创建时工作目录(可选)
    - ``parent_session`` —— 父 Session id(fork 谱系,可选)
    - ``is_seeded`` —— 是否含 fork 继承的事件前缀
    - ``origin`` —— 粗粒度分类(目前仅 ``"subagent"``)
    - ``delegation_depth`` —— 委派深度(0 = 顶层)
    - ``agent_preset`` —— Agent 预设 id(可选)
    """

    version: int
    id: str
    created_at: float
    is_seeded: bool = False
    cwd: str | None = None
    parent_session: str | None = None
    origin: str | None = None
    delegation_depth: int = 0
    agent_preset: str | None = None


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """不可变日志条目(对齐 DSH ``SessionEvent``)。

    字段语义:

    - ``seq`` —— 单调递增序列号(= log 中的位置)
    - ``time`` —— Unix epoch 秒
    - ``type`` —— 事件类型(DSH discriminated union key)
    - ``data`` —— 事件负载(JSON-compatible dict)
    - ``ignorable`` —— True 表示 reader 不认识 type 时可跳过

    frozen + slots 保证 append 后不可原地改;与 fold 纯函数配合:
    fold 只读 ``type`` + ``data``,不修改 ``SessionEvent`` 实例。
    """

    seq: int
    time: float
    type: str
    data: dict[str, Any]
    ignorable: bool = False


class SessionReentryError(RuntimeError):
    """Session.append 重入守卫异常(对齐 DSH ``append cannot reenter``)。

    DSH Session 在 append 执行期间禁止再次 append(防递归 / 保证
    observer 通知时序)。本异常是该守卫的显式错误形态。
    """


@runtime_checkable
class SessionObserver(Protocol):
    """Session 事件观察者(对齐 DSH ``session/event`` 事件回调)。

    ``on_session_event`` 在 append 提交后同步调用;失败由 caller contained
    吞错(不改变 append 返回值)。
    """

    def on_session_event(self, session: SessionProtocol, event: SessionEvent) -> None:
        """Session 日志增长后回调。

        Precondition: ``event`` 已进入 session log,seq 有效。
        Failure: 实现抛错由 caller contained;不影响后续 observer。
        """
        ...


@runtime_checkable
class SessionProtocol(Protocol):
    """Session 公开面契约(对齐 DSH ``Session`` 类公开面)。

    描述 Session 实现的只读 + append 面;不描述内部(如 surface manager、
    derived message cache)。实现类在 PR-3b 引入;本 Protocol 先行锁定
    语义边界,防止 PR-3b 实现漂移。

    属性语义:
    - ``id`` —— Session 唯一标识(从 header.id 投影)
    - ``header`` —— 不可变存储元数据
    - ``event_count`` —— 当前日志长度(= next seq)

    方法语义:
    - ``event_at(seq)`` —— 按 seq 取单条事件;越界返回 None
    - ``snapshot_events(from_seq, to_seq)`` —— 半开区间事件快照
    - ``append(type, data)`` —— 追加事件;返回已入 log 的不可变事件
    - ``request_header()`` —— 当前有效 EpochHeader(增量 fold)
    - ``step_tree()`` —— 当前 StepTree(增量 fold)
    """

    @property
    def id(self) -> str: ...

    @property
    def header(self) -> SessionHeader: ...

    @property
    def event_count(self) -> int: ...

    def event_at(self, seq: int) -> SessionEvent | None: ...

    def snapshot_events(
        self, from_seq: int = 0, to_seq: int | None = None
    ) -> Sequence[SessionEvent]: ...

    def append(self, type: str, data: dict[str, Any]) -> SessionEvent: ...

    def request_header(self) -> Any | None: ...

    def step_tree(self) -> Any: ...


__all__ = [
    "SessionEvent",
    "SessionHeader",
    "SessionObserver",
    "SessionProtocol",
    "SessionReentryError",
]
