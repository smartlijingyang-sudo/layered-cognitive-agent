"""投影单元契约 —— 投影家族的纯类型出口（DSH session-projection types 对照）。

本模块是消费模块②投影（``docs/specs/session-event-pipeline-spec.md`` §4.3）
的纯类型面：

- :class:`ProjectionUnit` —— 一个领域的状态驱动计算单元：纯同步 fold +
  声明 + 可选客户端视图。框架（投影注册表）驱动 ``apply``，单元自身
  不持任何订阅。
- :class:`ProjectionSnapshot` —— 一次一致读切（完整当前值 + 共享水位）。
- :class:`ProjectionCheckpoint` —— 一个单元的检查点行；检查点整体是
  ``key -> ProjectionCheckpoint`` 的映射（``key → {version, seq, state}``）。
  行是 fold 快捷方式，永不是真值。

契约边界：

- 本模块只含类型声明，无 I/O、无实现；契约层不依赖 ``lca_kernel``
  （import-linter kernel-domain-isolation），运行期的事件 / header 形态
  以 ``Any`` 结构对应 ``lca_kernel.events.session.SessionEvent`` /
  ``SessionHeader``。
- ``state`` 必须是可无损 JSON 序列化的纯 JSON（持久化投影缓存前提）；
  ``apply`` 必须纯同步，对无关事件返回同一引用（注册表以 ``==`` 比较
  视为无变化，产生零下游开销）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lca.contracts.harness.state.projection import ProjectionSnapshot

__all__ = ["ProjectionCheckpoint", "ProjectionSnapshot", "ProjectionUnit"]


class ProjectionUnit(Protocol):
    """一个领域的投影计算单元（对齐 DSH ``ProjectionDefinition``）。

    框架在每个已提交事件上驱动 ``apply``；单元只拥有计算，不持订阅。
    所有函数必须同步（异步单元会撕裂消费方的一致性切），``state``
    必须是纯 JSON（持久化缓存前提）。

    ``view`` 是可选成员：host-only 单元可不实现（注册表经
    ``getattr(unit, "view", None)`` 探测）；缺 ``view`` 的单元不出现在
    客户端 snapshot 中，但与其他单元一样被检查点。因成员可选，本
    Protocol 不做 ``runtime_checkable`` 检查，结构符合性由注册表运行期
    探测 + 静态检查器共同保证。

    Attributes:
        key: 单元拥有的投影 key（注册表内唯一；重复注册共享需版本一致）。
        state_version: 持久化缓存失效版本：序列化状态字段或 fold 语义
            变化时 bump，使旧版本行被整行丢弃而非前向套用。非负整数。
    """

    key: str
    state_version: int

    def init(self, header: Any) -> Any:
        """空日志及其不可变 Session 元数据下的初始状态。

        ``header`` 结构对应 ``lca_kernel.events.session.SessionHeader``。
        """
        ...

    def apply(self, state: Any, event: Any) -> Any:
        """纯转移：前一状态 + 一个已提交事件 → 下一状态。

        对事件不感兴趣的单元必须返回同一状态引用 —— 注册表以 ``==``
        比较视为无变化，产生零下游工作。``event`` 结构对应
        ``lca_kernel.events.session.SessionEvent``。
        """
        ...

    def view(self, state: Any) -> Any:
        """客户端视图：状态 → 完整当前值（读侧出口）。

        host-only 单元可省略本成员（见类说明）。
        """
        ...


@dataclass(frozen=True, slots=True)
class ProjectionCheckpoint:
    """一个单元的检查点行（持久化投影缓存的写侧形态）。

    检查点映射为 ``key -> ProjectionCheckpoint``；行记录折入时刻的
    单元版本、最后折入事件的 seq（空日志为 ``-1``）与单元内部状态
    （纯 JSON）。行永不是真值，只是 fold 快捷方式：``restore`` 在
    版本不匹配或 seq 越界时丢弃整行重折。
    """

    version: int
    seq: int
    state: Any
