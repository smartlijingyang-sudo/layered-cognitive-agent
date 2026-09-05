"""SessionPersistenceService —— DSH SessionPersistence seam 的 LCA 服务契约。

deepseek-harness ``@deepseek-ai/dsh-session-persistence`` ``ctx.sessionPersistence``
Service Definition 的 LCA Protocol 形态:纯类型(Protocol + 异常),无 I/O,
无第三方依赖;Profile 据此选择持久化后端(JSONL / 数据库 / event store),
消费方不内嵌实现选择。

持久性时序(``docs/specs/session-event-pipeline-spec.md`` §4.2):

- **``append`` 接受 ≠ crash durable** —— 返回成功只代表后端接受事件
  (进入 write-behind 缓冲,对当前后端实例可见),不保证崩溃后仍存在;
- **``flush`` 成功才是 durability barrier** —— 跨进程/崩溃后的持久性以
  ``flush`` 成功返回为界。

事件/header 信封复用 contracts 平面类型
(:mod:`lca.contracts.harness.tasks.session`):contracts 层禁止 import
``lca_kernel``(pyproject 契约 6 kernel-domain-isolation),新平面信封
(:mod:`lca_kernel.events.session`)由实现侧在 seam 处适配,本契约不感知。

:class:`CheckpointFailure` 是 checkpoint 策略
(``lca.plugins.session.checkpoint_policy``)在 flush barrier 未完成时抛出的
fail-closed 异常;契约层只定义类型,不含行为。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.contracts.harness.tasks.session import SessionEvent, SessionHeader


class CheckpointFailure(RuntimeError):  # noqa: N818 —— checkpoint 契约词汇,非通用异常
    """durability checkpoint 未完成:flush barrier 失败,下游动作不得执行。

    由 checkpoint 策略的三个边界(模型请求前 / 顶层工具副作用前 / 步边界)
    抛出:``session.flush()`` 自身抛错,或任一 FlushListener 报 ``ok=False``。
    fail-closed 语义 —— 对应边界的下游(模型请求、工具体、下一步)不得执行;
    ``__cause__`` / message 携带原始失败供排查(spec §11 第 5 问)。
    """


@runtime_checkable
class SessionPersistenceService(Protocol):
    """durable append-only Session 持久化服务(唯一写盘者面,spec §8)。

    对齐 DSH ``SessionPersistence`` 的最小方法集(locate / append / flush /
    load / list);DSH 的 prepare / inspect / borrowSession / readFrom /
    readRaw / listSnapshots 属 resume-fusion 面,由 LCA 融合阶段按 ADR-0186
    另行叠加,不在本契约承载。

    所有权:实现拥有 per-session 持久工件 + header,是唯一授权写盘者;
    事件真值仍在 ``Session.append`` 的 in-process 日志,本服务是其 durable
    镜像与恢复来源,不得反向写事实。
    """

    def locate(self, session_id: str) -> Path | None:
        """解析 ``session_id`` 的后端自有工件路径;不读取、不创建、不 flush。

        返回值是位置提示,不是存在性或授权保证:路径可以指向尚未物化的工件。
        后端不按 session 拥有单一工件时返回 ``None``。
        """
        ...

    def append(self, session_id: str, events: Sequence[SessionEvent]) -> None:
        """把一段 seq 连续的事件批次追加到 ``session_id`` 的 durable 流。

        precondition:批次按 seq 有序,首条事件 ``seq`` 等于存储 next-seq;
        事件 data 可无损 JSON 序列化。

        失败语义:违反 precondition(seq 不连续、序列化失败)直接抛错,
        不做部分写入;**接受 ≠ crash durable** —— 返回成功只代表进入后端
        待写缓冲,跨崩溃的持久性以 :meth:`flush` 成功为界(durability
        barrier)。
        """
        ...

    def flush(self, session_id: str) -> None:
        """排空 ``session_id`` 的待写事件到 durable 介质 —— durability barrier。

        成功返回 ⇒ 此前经 :meth:`append` 接受的事件崩溃后仍存在;失败抛异常
        (排空/fsync 错误向上传播),已保留事件待重试,不丢失、不静默截断已
        提交前缀。checkpoint 策略以本方法为 fail-closed 判定点:flush 失败 →
        :class:`CheckpointFailure` → 下游不得执行。
        """
        ...

    def load(self, session_id: str) -> tuple[SessionHeader | None, tuple[SessionEvent, ...]]:
        """读取 ``session_id`` 的 durable 日志:header + 平衡的连续事件前缀。

        恢复语义(spec §4.2):崩溃恢复不截断已提交事件;撕裂尾行由读取端
        识别跳过;孤儿进行中的轮次以显式「中断」标记闭合,而非删除其事件;
        未知格式版本拒绝加载(不做隐式迁移)。``session_id`` 不存在 →
        ``(None, ())``。
        """
        ...

    def list_sessions(self) -> tuple[SessionHeader, ...]:
        """每个已物化 session 一个 header;轻量元数据列举,不解析全量日志。"""
        ...


__all__ = ["CheckpointFailure", "SessionPersistenceService"]
