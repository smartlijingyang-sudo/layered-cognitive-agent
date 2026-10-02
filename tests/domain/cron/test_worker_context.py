"""Cron worker context tests (ADR-0268 §3.4, §14 item 1).

钉住结构保证：组装函数的参数里没有父 transcript；组装结果等于
存储里的 ``body`` 加上产品上下文，不附加父轮。
"""

from __future__ import annotations

import inspect
from typing import Any

from lca.contracts.models.cron.models import ChatDelivery
from lca.domain.cron.worker_context import (
    WorkerProductContext,
    assemble_worker_context,
)

_FORBIDDEN_PARAM_NAMES = (
    "transcript",
    "parent_transcript",
    "history",
    "messages",
    "prior_turns",
    "context",
    "chat_history",
    "session",
)


def _product(**overrides: Any) -> WorkerProductContext:
    base: dict[str, Any] = {
        "job_id": "job_1",
        "owner": "user_1",
        "workspace_path": "/home/user/assistants/asst_1",
        "timezone": "Asia/Shanghai",
        "report": "anomalies_only",
        "delivery_targets": (ChatDelivery(chat_id="chat_1"),),
        "run_id": "run_1",
    }
    base.update(overrides)
    return WorkerProductContext(**base)


def test_worker_context_signature_has_no_parent_transcript() -> None:
    sig = inspect.signature(assemble_worker_context)
    names = set(sig.parameters)
    assert "body" in names
    for forbidden in _FORBIDDEN_PARAM_NAMES:
        assert forbidden not in names, f"worker 上下文函数不得接收 {forbidden!r} 参数"


def test_worker_context_contains_body_and_product() -> None:
    body = "每天 9 点提醒我同步进度"
    product = _product()
    text = assemble_worker_context(body, product)
    assert body in text
    assert product.job_id in text
    assert product.owner in text
    assert product.workspace_path in text
    assert product.timezone in text
    assert product.report in text
    assert product.delivery_targets[0].chat_id in text
    assert product.run_id in text


def test_worker_context_body_passed_verbatim() -> None:
    body = "原样 body，含换行\n和特殊符号 {abc} [x]"
    text = assemble_worker_context(body, _product())
    assert body in text


def test_worker_context_does_not_attach_parent_turn() -> None:
    """组装函数参数里没有父轮可读，结果自然不包含父聊天内容。"""
    product = _product()
    text = assemble_worker_context("body", product)
    assert "user 说" not in text
    assert "assistant 回复" not in text
    assert "prior" not in text.lower()
