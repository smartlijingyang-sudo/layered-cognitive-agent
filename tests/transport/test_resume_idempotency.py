"""resume_approval 幂等与审计语义的回归锁。

``POST /runs/<id>/answer`` 携带 ``idempotency_key``；同一 key 重放必须返回
原回执而不是再次 resume（历史缺陷：key 被 ``del`` 丢弃，重复提交触发二次
resume）。approval_id 不匹配时仍接受（前端当前上送工具名而非派生
``<plan_ref>:<node>:<visit>`` id），但接受日志记录匹配标志供审计。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunSession,
    RunStatus,
)
from lca.plugins.transport.webserver.handlers.runs.terminal import registry_commands

if TYPE_CHECKING:
    import pytest


def _waiting_session() -> RunSession:
    session = RunSession(
        run_id="run-idem-1",
        trace_id="trace-idem-1",
        spine_path=Path("traces/idem.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="q",
        user_text="q",
        mode="solo",
    )
    session.status = RunStatus.WAITING_INPUT
    session.snapshot = object()
    session.runnable = object()
    session.approval_request = {
        "type": "ask_user_question",
        "approval_id": "plan:think.main:1",
    }
    return session


def _commands_for(session: RunSession) -> registry_commands.RegistryRunCommands:
    class _RegistryStub:
        def get(self, run_id: str) -> RunSession | None:
            return session if run_id == "run-idem-1" else None

    return registry_commands.RegistryRunCommands(_RegistryStub())  # type: ignore[arg-type]


def test_duplicate_idempotency_key_replays_without_second_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _counting_resume(session, registry, answer):
        calls.append(answer)

    monkeypatch.setattr(registry_commands, "resume_run", _counting_resume)
    session = _waiting_session()
    commands = _commands_for(session)

    async def _scenario() -> None:
        first = await commands.resume_approval(
            run_id="run-idem-1",
            approval_id="askUserQuestion",
            payload="answer-1",
            idempotency_key="run-idem-1:msg-1:submit",
        )
        assert first.accepted
        assert session.status is RunStatus.RUNNING

        # 模型再次提问后第二次暂停；同一 key 重放不得再次 resume。
        session.status = RunStatus.WAITING_INPUT
        replay = await commands.resume_approval(
            run_id="run-idem-1",
            approval_id="askUserQuestion",
            payload="answer-1",
            idempotency_key="run-idem-1:msg-1:submit",
        )
        assert replay.accepted
        assert replay.status == "resumed"
        assert session.status is RunStatus.WAITING_INPUT

    asyncio.run(_scenario())
    assert calls == ["answer-1"]
    assert session.accepted_answer_keys == {"run-idem-1:msg-1:submit"}


def test_distinct_keys_resume_each_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _counting_resume(session, registry, answer):
        calls.append(answer)

    monkeypatch.setattr(registry_commands, "resume_run", _counting_resume)
    session = _waiting_session()
    commands = _commands_for(session)

    async def _scenario() -> None:
        first = await commands.resume_approval(
            run_id="run-idem-1",
            approval_id="askUserQuestion",
            payload="answer-1",
            idempotency_key="k-1",
        )
        assert first.accepted
        session.status = RunStatus.WAITING_INPUT
        second = await commands.resume_approval(
            run_id="run-idem-1",
            approval_id="askUserQuestion",
            payload="answer-2",
            idempotency_key="k-2",
        )
        assert second.accepted

    asyncio.run(_scenario())
    assert calls == ["answer-1", "answer-2"]


def test_approval_id_mismatch_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """前端上送工具名而非派生 approval_id；当前语义为接受并留审计标志。"""

    async def _noop_resume(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)
    commands = _commands_for(_waiting_session())

    async def _scenario() -> None:
        receipt = await commands.resume_approval(
            run_id="run-idem-1",
            approval_id="askUserQuestion",
            payload="answer",
            idempotency_key="k",
        )
        assert receipt.accepted

    asyncio.run(_scenario())


def test_cancel_at_waiting_input_transitions_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _waiting_session()
    commands = _commands_for(session)

    class _NoopTerminalizer:
        def __init__(self, registry: object, **kwargs: object) -> None: ...

        async def terminalize(self, *args: object, **kwargs: object) -> None:
            session._closed = True

    monkeypatch.setattr(registry_commands, "RunTerminalizer", _NoopTerminalizer)

    async def _scenario() -> None:
        receipt = await commands.cancel("run-idem-1")
        assert receipt.accepted
        assert receipt.status == RunStatus.CANCELED.value
        assert session.status is RunStatus.CANCELED
        assert session.cancel_requested

    asyncio.run(_scenario())


def test_cancel_unknown_run_rejected() -> None:
    commands = _commands_for(_waiting_session())

    async def _scenario() -> None:
        receipt = await commands.cancel("run-missing")
        assert not receipt.accepted
        assert receipt.error == "run not found"

    asyncio.run(_scenario())
