"""跨异步边界传递委派关联的显式上下文原语（ADR-0037 关联骨架穿透）。

背景：AgentTransport.send_task(agent_card, subtask, context_refs) 的签名要与
Google A2A 的 AgentCard 模型保持一致，不能塞入 LCA 内部专用的委派身份字段；
同时 send_task 内部用 asyncio.create_task 异步调度、poll/receive 分离，
调用点与 handler 执行点不在同一次 await 里，无法用普通参数直接传递。
因此选择 contextvars：asyncio.create_task 会拷贝调用时的 Context，
handler 在被调度执行时读到的是"发起 delegate 那一刻"的委派关联。
这是一个刻意的设计选择，而非遗留副作用。

ADR-0037 扩展：除委派者角色外，另穿透 ``run_id`` / ``delegation_id``
（成员 run 的 parent_run_id / delegation_id 由此派生）与 member-invoke
标记（区分编排策略调用与决策驱动委派）——关联骨架经此跨越 task 边界。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class DelegatorContext:
    """委派发起时刻的关联快照（随 create_task 拷贝到成员任务）。"""

    role: str = ""
    run_id: str = ""
    delegation_id: str = ""


_delegator: ContextVar[DelegatorContext | None] = ContextVar("current_delegator", default=None)

_member_invoke: ContextVar[bool] = ContextVar("lca_member_invoke", default=False)


def get_current_delegator() -> str:
    """读取当前委派链路里最近一次 set 的委派者角色，无则返回空串。"""
    context = _delegator.get()
    return context.role if context is not None else ""


def get_delegator_context() -> DelegatorContext:
    """读取完整委派关联快照（角色 + run/delegation id），无则返回空快照。"""
    return _delegator.get() or DelegatorContext()


@contextmanager
def delegator_scope(role: str) -> Iterator[None]:
    """在委派发起点包裹此上下文，确保 asyncio.create_task 拷贝到正确的委派者身份。"""
    token = _delegator.set(DelegatorContext(role=role))
    try:
        yield
    finally:
        _delegator.reset(token)


@contextmanager
def delegation_scope(role: str, run_id: str, delegation_id: str) -> Iterator[None]:
    """委派关联全量穿透：成员任务由此派生 parent_run_id / delegation_id。"""
    token = _delegator.set(DelegatorContext(role=role, run_id=run_id, delegation_id=delegation_id))
    try:
        yield
    finally:
        _delegator.reset(token)


def in_member_invoke() -> bool:
    """当前是否处于编排策略的成员调用通道（区分机制：member_invoke vs delegate）。"""
    return _member_invoke.get()


@contextmanager
def member_invoke_scope() -> Iterator[None]:
    """编排策略（Pipeline/FanOut/Debate...）经 MemberInvoker 调用成员时包裹。"""
    token = _member_invoke.set(True)
    try:
        yield
    finally:
        _member_invoke.reset(token)
