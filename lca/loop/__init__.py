"""Loop 机制层(R1)—— 人读入口 + 事实生产门面。

权威决策:ADR-0194。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DefaultFactGateway",
    "append_catalog_bound",
    "commit_act_journal_receipt",
    "commit_memory_journal_receipt",
    "commit_memory_spine_receipt",
    "commit_tool_journal_receipt",
    "commit_tool_phase_call_end",
    "commit_tool_phase_call_start",
    "commit_tool_phase_denied",
    "fact_gateway_for_emit",
    "publish_ep_bound",
]


def __getattr__(name: str) -> Any:
    if name in {
        "DefaultFactGateway",
        "append_catalog_bound",
        "fact_gateway_for_emit",
        "publish_ep_bound",
    }:
        from lca.loop import fact_gateway as _fact_gateway

        return getattr(_fact_gateway, name)
    if name == "commit_act_journal_receipt":
        from lca.loop.commit.act_journal import commit_act_journal_receipt

        return commit_act_journal_receipt
    if name in {"commit_memory_journal_receipt", "commit_memory_spine_receipt"}:
        from lca.loop.commit import memory_journal as _memory

        return getattr(_memory, name)
    if name in {
        "commit_tool_journal_receipt",
        "commit_tool_phase_call_end",
        "commit_tool_phase_call_start",
        "commit_tool_phase_denied",
    }:
        from lca.loop.commit import tool_journal as _tool

        return getattr(_tool, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
