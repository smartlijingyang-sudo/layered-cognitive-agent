"""cordis_name 派生表（ADR-0169 L12 / §D6 I-CURSOR-4 / §D8 五缝架构）。

spine 上的所有 execution_point（spine EP）派生到 cordis 事件总线的映射;
cordis_name 强制以 ``"agent."`` 前缀收口（PR-13,业务禁 emit
``'agent.*' / 'phase.*' / 'tool.*' / 'llm.*'`` 直字面量）。

设计来源:ADR-0169 §D6 Incarnation + §D8 五缝架构 + §D9 删除清单 + §L12
cordis_name 派生不变量;ADR-0168-final §D14 EventDescriptor.cordis_name。

表是 ``frozen=True`` 静态字典;查表是 O(1) 哈希;不引入 import 时副作用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from lca.contracts.observability.loop_cursor import PhaseName


class UnknownCordisEventError(KeyError):
    """未登记 execution_point 的查表失败（ADR-0169 L12 + L15 UnknownEventType）。

    KeyError 子类便于调用方 ``except KeyError`` 兜底;单独捕获请用本类。
    """


@dataclass(frozen=True)
class CordisEventTableEntry:
    """单条 EP → cordis 派生条目。"""

    execution_point: str
    cordis_name: str
    schema_version: int = 1
    ignorable: bool = False


# ─────────────────────────────────────────────────────────────────
# L12 cordis_name 派生表(PR-13 交付物;schema_version 与 ignorable 见 L15)
# ─────────────────────────────────────────────────────────────────
#
# 命名规则:cordis_name 一律以 "agent." 前缀收口 → 5 域(writable / step /
# phase / tool / llm / model_visible / iteration)在 cordis 词表中是
# 子树,避免与既有 plugin / 适配器自注册事件名冲突。
#
# 范围(PR-13 最小集;符合 ADR-0169 PR-13 表要求 + D2 状态图 + L1-L8 配对 EP):
#
# - writable.{step,segment,iteration}.{start,end,...} (L1, L2, L16)
# - step.{thinking.record,tool_call.record,tool_result.record}
# - phase.<name>.fold(for all 7 PhaseName)
# - llm.request.header
#
# Future PR 可向本表追加条目;**禁止**业务 / plugin 代码直接
# ``ctx.emit('agent.*')``,必须经 ``EventDescriptor.derive()`` 走本表。
# ─────────────────────────────────────────────────────────────────

_CORDIS_EVENT_TABLE_ENTRIES: Final[tuple[CordisEventTableEntry, ...]] = (
    # ── writable.step.*  (ADR-0169 L1:begin/end 配对) ─────────────
    CordisEventTableEntry(
        execution_point="writable.step.start",
        cordis_name="agent.writable.step.start",
    ),
    CordisEventTableEntry(
        execution_point="writable.step.end",
        cordis_name="agent.writable.step.end",
    ),
    # ── writable.segment.*  (ADR-0169 L2:begin/end 配对) ──────────
    CordisEventTableEntry(
        execution_point="writable.segment.start",
        cordis_name="agent.writable.segment.start",
    ),
    CordisEventTableEntry(
        execution_point="writable.segment.end",
        cordis_name="agent.writable.segment.end",
    ),
    # ── writable.iteration.*  (ADR-0169 L7-5 + L16) ───────────────
    # closing EP:CloseBarrier 协调消费;L16 Host 不订阅 close EP。
    CordisEventTableEntry(
        execution_point="writable.iteration.closing",
        cordis_name="agent.writable.iteration.closing",
    ),
    CordisEventTableEntry(
        execution_point="writable.iteration.close",
        cordis_name="agent.writable.iteration.close",
    ),
    CordisEventTableEntry(
        execution_point="writable.iteration.halt",
        cordis_name="agent.writable.iteration.halt",
    ),
    # ── step.* 事实记录(ADR-0169 D1,record_* 入口) ────────────────
    CordisEventTableEntry(
        execution_point="step.thinking.record",
        cordis_name="agent.step.thinking.record",
    ),
    CordisEventTableEntry(
        execution_point="step.tool_call.record",
        cordis_name="agent.step.tool_call.record",
    ),
    CordisEventTableEntry(
        execution_point="step.tool_result.record",
        cordis_name="agent.step.tool_result.record",
    ),
    # ── phase.<name>.fold  (all 7 PhaseName,ADR-0169 D2) ──────────
    *[
        CordisEventTableEntry(
            execution_point=f"phase.{phase}.fold",
            cordis_name=f"agent.phase.{phase}.fold",
        )
        for phase in PhaseName.__args__
    ],
    # ── llm.request.header  (ADR-0169 D7 + L6:必在 THINK 窗口开) ──
    CordisEventTableEntry(
        execution_point="llm.request.header",
        cordis_name="agent.llm.request.header",
    ),
)

_CORDIS_EVENT_TABLE_BY_EP: Final[dict[str, CordisEventTableEntry]] = {
    entry.execution_point: entry for entry in _CORDIS_EVENT_TABLE_ENTRIES
}


def lookup_cordis_name(execution_point: str) -> CordisEventTableEntry:
    """按 execution_point 查派生表;未登记抛 ``UnknownCordisEventError``。

    是 ``EventDescriptor.derive()`` 的内部入口;公开以利单测覆盖。
    """
    try:
        return _CORDIS_EVENT_TABLE_BY_EP[execution_point]
    except KeyError as exc:
        raise UnknownCordisEventError(f"未登记 execution_point={execution_point!r}") from exc


def all_execution_points() -> tuple[str, ...]:
    """全部已登记 execution_point(快照)。"""
    return tuple(_CORDIS_EVENT_TABLE_BY_EP.keys())


__all__ = [
    "CordisEventTableEntry",
    "UnknownCordisEventError",
    "all_execution_points",
    "lookup_cordis_name",
]
