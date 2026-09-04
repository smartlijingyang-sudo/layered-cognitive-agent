"""Resume 路径重新绑定 Session publish/observe 槽位。

create 时的绑定发生在 create 请求的 context；resume 是新请求、新
context，槽位为空。``resume_approval`` 必须在 ``create_task`` 前把
``session.event_session.bridge`` 重新绑定（create_task 拷贝当前
context，run task 继承该绑定）。

断言放在同一 coroutine 内：ContextVar 写入只在当前 context 可见。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lca.plugins.events._session_observe import current_session, set_session
from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session
from lca.plugins.transport.webserver.handlers.runs.session.event_session import (
    BoundRunEventSession,
    RunEventSessionBridge,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunSession,
    RunStatus,
)
from lca.plugins.transport.webserver.handlers.runs.terminal import registry_commands


def _waiting_session(bound: BoundRunEventSession | None) -> RunSession:
    session = RunSession(
        run_id="run-resume-1",
        trace_id="trace-resume-1",
        spine_path=Path("traces/resume.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="q",
        user_text="q",
        mode="solo",
    )
    session.status = RunStatus.WAITING_INPUT
    session.snapshot = object()
    session.runnable = object()
    session.event_session = bound
    return session


@pytest.fixture
def _clean_slots():
    token = set_publish_session(None)  # type: ignore[arg-type]
    reset_publish_session(token)
    set_session(None)
    yield
    token = set_publish_session(None)  # type: ignore[arg-type]
    reset_publish_session(token)
    set_session(None)


def _commands_for(session: RunSession) -> registry_commands.RegistryRunCommands:
    class _RegistryStub:
        def get(self, run_id: str) -> RunSession | None:
            return session if run_id == "run-resume-1" else None

    return registry_commands.RegistryRunCommands(_RegistryStub())  # type: ignore[arg-type]


@pytest.mark.usefixtures("_clean_slots")
def test_resume_approval_rebinds_session_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_resume(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)

    bridge = RunEventSessionBridge(Session("run-resume-1"))
    bound = BoundRunEventSession(
        store=MagicMock(name="store"),
        bridge=bridge,
        publish_token=None,
        run_id="run-resume-1",
    )
    commands = _commands_for(_waiting_session(bound))

    async def _scenario() -> None:
        assert current_publish_session() is None
        receipt = await commands.resume_approval(
            run_id="run-resume-1",
            approval_id="ap-1",
            payload="answer",
            idempotency_key="k",
        )
        assert receipt.accepted
        # resume_approval 已在当前 context 重新绑定；紧随其后的
        # create_task 让 run task 继承该绑定。
        assert current_publish_session() is bridge
        assert current_session() is bridge

    asyncio.run(_scenario())


@pytest.mark.usefixtures("_clean_slots")
def test_resume_approval_without_event_session_still_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺 event_session（profile 未装 session.store）时不绑定但仍可 resume。"""

    async def _noop_resume(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)
    commands = _commands_for(_waiting_session(None))

    async def _scenario() -> None:
        receipt = await commands.resume_approval(
            run_id="run-resume-1",
            approval_id="ap-1",
            payload="answer",
            idempotency_key="k",
        )
        assert receipt.accepted
        assert current_publish_session() is None

    asyncio.run(_scenario())
