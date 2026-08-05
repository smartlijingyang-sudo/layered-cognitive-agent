"""Mermaid 序列图渲染 —— 协作叙事的"一目了然"投影（ADR-0037）。

从 journal 事件流派发：委派发起/回执 → 参与者之间的消息箭头；
run 容器 → participant 声明。纯函数，无 OTel / IO 依赖，可脱离运行时
单测，也可由 jsonl replay 复用。

渲染约定（Mermaid sequenceDiagram）：
- participant 以 ``角色`` 为别名，重名/特殊字符由 ``_alias`` 归一为 id；
- ``DelegationIssued`` → ``caller ->> callee: subtask``（实线请求）；
- ``DelegationCompleted`` → ``callee -->> caller: status · 时长``（虚线回执）；
- handoff 机制用 ``-)>>`` 异步箭头区分（发完即返回，无回执）。
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.journal import (
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    StampedEvent,
)

_PARTICIPANT_RESERVE = {"team"}


def _alias(role: str) -> str:
    """角色名 → mermaid participant id（保留可读性，去掉会破坏语法的空格）。"""
    cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in role)
    return cleaned or "agent"


def _participants(events: Iterable[StampedEvent]) -> list[str]:
    """按首次出现顺序收集参与角色（lead/成员），team 不作 participant。"""
    seen: list[str] = []

    def _add(role: str) -> None:
        if role and role not in seen and role not in _PARTICIPANT_RESERVE:
            seen.append(role)

    for stamped in events:
        event = stamped.event
        if isinstance(event, AgentRunStarted):
            _add(event.agent_role)
        elif isinstance(event, DelegationIssued):
            _add(event.caller_role)
            _add(event.callee_role)
    return seen


def render_sequence_diagram(events: Iterable[StampedEvent]) -> str:
    """journal 事件流 → Mermaid sequenceDiagram 文本（无协作事件时返回空串）。"""
    event_list = list(events)
    issued_ts: dict[str, float] = {}
    arrows: list[str] = []
    has_delegation = False
    for stamped in event_list:
        event = stamped.event
        if isinstance(event, DelegationIssued):
            has_delegation = True
            issued_ts[event.delegation_id] = stamped.ts
            mechanism = getattr(event.mechanism, "value", event.mechanism)
            arrow = "-)>>" if mechanism == DelegationMechanism.HANDOFF.value else "->>"
            label = event.subtask_preview or "委派"
            arrows.append(
                f"    {_alias(event.caller_role)}{arrow}{_alias(event.callee_role)}: {label}"
            )
        elif isinstance(event, DelegationCompleted):
            start = issued_ts.get(event.delegation_id)
            duration = f"{(stamped.ts - start):.1f}s" if start is not None else ""
            detail = event.status if event.status else ("ok" if event.ok else "failed")
            suffix = f" · {duration}" if duration else ""
            callee = _callee_of(event_list, event.delegation_id)
            caller = _caller_of(event_list, event.delegation_id)
            arrows.append(f"    {_alias(callee)}-->>{_alias(caller)}: {detail}{suffix}")
    if not has_delegation:
        return ""

    lines = ["sequenceDiagram"]
    for role in _participants(event_list):
        lines.append(f"    participant {_alias(role)} as {role}")
    lines.extend(arrows)
    return "\n".join(lines)


def _caller_of(events: Iterable[StampedEvent], delegation_id: str) -> str:
    for stamped in events:
        event = stamped.event
        if isinstance(event, DelegationIssued) and event.delegation_id == delegation_id:
            return event.caller_role
    return ""


def _callee_of(events: Iterable[StampedEvent], delegation_id: str) -> str:
    for stamped in events:
        event = stamped.event
        if isinstance(event, DelegationIssued) and event.delegation_id == delegation_id:
            return event.callee_role
    return ""
