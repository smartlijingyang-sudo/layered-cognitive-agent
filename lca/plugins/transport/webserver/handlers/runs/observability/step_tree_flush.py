"""Step-tree 派生产物的唯一写入入口(journal.json + narrative.md)。

所有权:``<run_id>.spine.jsonl`` 与 ``<run_id>.session.jsonl`` 是真值流;
本模块是两者到派生产物的唯一投影触发点。调用方只有两处:

- 终态物化(``terminal/materialization.py``)——run 收尾时的最后一次投影。
- 暂停点(``lifecycle/lifecycle.py`` 的 WAITING_INPUT 分支)——运行中的
  增量投影,派生物不等终态就可读。

outcome 映射(:func:`journal_outcome_from_session`)同样唯一:调用方传
``outcome=None`` 时由 session 当前状态推导,不允许旁路自带映射。

失败语义:bundle flush 异常被收进返回的 ``flush_errors``
(``{operation, error_type, error_message, traceback}``),不上抛——
观测面故障不阻塞控制面(暂停照常、终态照常),现场经
``manifest.extra.flush_errors`` 或 structlog 留痕。
"""

from __future__ import annotations

import traceback

import structlog

from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

_log = structlog.get_logger(__name__)

__all__ = ["flush_step_tree_artifacts", "journal_outcome_from_session"]


def journal_outcome_from_session(session: RunSession) -> str:
    """Map RunSession.status onto JournalMetadata.outcome vocabulary."""
    status = str(getattr(session.status, "value", session.status) or "").lower()
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status in {"canceled", "cancelled"}:
        return "stopped"
    if status == "waiting_input":
        return "paused"
    return "stopped"


def flush_step_tree_artifacts(
    session: RunSession,
    *,
    outcome: str | None = None,
) -> list[dict[str, str]]:
    """Fold 事件流并写 journal.json + narrative.md;返回 flush_errors。

    precondition: ``session.step_tree_bundle`` 由 RunSessionBuilder.build
    装配;缺省时无派生物可写,返回空列表。
    ``outcome`` 缺省时经 :func:`journal_outcome_from_session` 从当前
    状态推导(暂停 = ``paused``,取消 = ``stopped``)。
    """
    bundle = getattr(session, "step_tree_bundle", None)
    if bundle is None:
        return []
    errors: list[dict[str, str]] = []
    try:
        resolved = outcome if outcome is not None else journal_outcome_from_session(session)
        flush = getattr(bundle, "flush", None)
        if callable(flush):
            flush(outcome=resolved)
    except Exception as exc:
        errors.append(
            {
                "operation": "step_tree.flush",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "traceback": traceback.format_exc(limit=4),
            }
        )
        _log.error(
            "step_tree_flush_failed",
            run_id=session.run_id,
            exc_info=True,
        )
    return errors
