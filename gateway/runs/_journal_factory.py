"""gateway/runs journal 组件工厂 —— ADR-0065 L9 / PR-5。

把 gateway/runs/ 中的 ``JsonlJournalProjector`` / ``LiveTail`` /
``ProcessJournal`` 实例化集中到这一处;调用方经 ``create_run_journal_components``
获得 run-scoped writer trio。

实现细节:这些类仍由 ``gateway.runs.live`` / ``gateway.runs.process_journal`` /
``lca.layer0_infra.observability.journal.jsonl_projector`` 提供,但仅本
模块允许 ``new`` —— ``check_gateway_no_direct_journal_new.py`` 对本模块
豁免(``# ADR-0065 PR-5 gateway-exempt``)。

后续 PR 把这些类下沉到 layer0 + 改成 ``run_ledger_factory`` capability
直接构造;届时本模块消失。
"""

from __future__ import annotations

from pathlib import Path

from gateway.runs.live import LiveTail
from gateway.runs.process_journal import ProcessJournal
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector


def create_run_journal_components(
    *,
    jsonl_path: Path,
    registry_journal: ProcessJournal | None = None,
) -> tuple[JsonlJournalProjector, LiveTail]:
    """为单个 run 创建 journal 落盘 + LiveTail SSE 投影。

    ADR-0065 L9 / PR-5:本函数是 ``JsonlJournalProjector`` / ``LiveTail`` 在
    gateway/runs/ 路径下的唯一允许 ``new`` 入口;调用方必须经 ``registry.jsonl_path_for``
    取得 ``jsonl_path`` 再传入,不再 ``traces/runs/<id>/journal.jsonl`` 嵌套
    布局(嵌套布局是 PR-6 RunLocator 的工作)。

    ``registry_journal`` 跨 run 共享的 ProcessJournal(从 boot 期 ctx 拉);
    留 None 时 caller 自己新建。
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_writer = JsonlJournalProjector(jsonl_path)  #  ADR-0065 PR-5 gateway-exempt
    tail = LiveTail()  #  ADR-0065 PR-5 gateway-exempt
    return jsonl_writer, tail


def get_or_create_process_journal(*, registry_journal: ProcessJournal | None) -> ProcessJournal:
    """跨 run 共享的 ProcessJournal 单例 — 若调用方已持有一个,直接返回;否则新建。"""
    if registry_journal is not None:
        return registry_journal
    return ProcessJournal()  #  ADR-0065 PR-5 gateway-exempt


__all__ = [
    "create_run_journal_components",
    "get_or_create_process_journal",
]
