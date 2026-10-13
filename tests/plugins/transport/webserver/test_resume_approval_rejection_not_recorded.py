"""RA-131: rejection answers must never be recorded into approved_tool_names.

The resume-approval record point in
``RegistryRunCommands.resume_approval`` used to record
``session.approval_request["tool_calls"]`` unconditionally. A human REJECTION
carries ``rejectionReason`` (the decoder supports it), so the rejected tool
was recorded as approved and ``act.authorize``'s approved-override auto-passed
it on retry -- "reject, retry, auto-approved". The port chain now carries
``is_rejection`` (set by ``_dispatch_resume`` from ``rejection_reason``), and
the record point skips recording for rejections.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.registry import (
    commands as registry_commands,
)

if TYPE_CHECKING:
    import pytest


def _waiting_session() -> RunSession:
    session = RunSession(
        run_id="run-rej-1",
        trace_id="trace-rej-1",
        spine_path=Path("traces/rej.spine.jsonl"),
        tail=MagicMock(name="tail"),
        question="q",
        user_text="q",
        mode="solo",
    )
    session.status = RunLifecycleStatus.WAITING_INPUT
    session.snapshot = object()
    session.runnable = object()
    session.approval_request = {
        "type": "tool_permission",
        "approval_id": "plan:think.main:1",
        "tool_calls": [
            {"tool_name": "execute_code"},  # snake_case on purpose: must be canonicalized
            {"tool_name": "askUserQuestion"},  # HITL tool: never recorded
        ],
    }
    return session


def _commands_for(session: RunSession) -> registry_commands.RegistryRunCommands:
    class _RegistryStub:
        def get(self, run_id: str) -> RunSession | None:
            return session if run_id == "run-rej-1" else None

    return registry_commands.RegistryRunCommands(_RegistryStub())  # type: ignore[arg-type]


def _answer(session: RunSession, is_rejection: bool, key: str) -> None:
    commands = _commands_for(session)

    async def _scenario() -> object:
        return await commands.resume_approval(
            run_id="run-rej-1",
            approval_id="execute_code",
            payload="user said no" if is_rejection else "approved",
            idempotency_key=key,
            is_rejection=is_rejection,
        )

    receipt = asyncio.run(_scenario())
    assert receipt.accepted, "rejection still resumes the run; only recording is skipped"


def test_rejection_answer_does_not_record_approved_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_resume(session, registry, answer):
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)
    session = _waiting_session()
    _answer(session, is_rejection=True, key="k-rej-1")
    assert session.approved_tool_names == set()


def test_approval_answer_records_canonicalized_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_resume(session, registry, answer):
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)
    session = _waiting_session()
    _answer(session, is_rejection=False, key="k-app-1")
    assert session.approved_tool_names == {"executeCode"}


def test_default_is_rejection_false_preserves_bypass_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callers that never pass the flag (``answer_run``, ws ``tool_result``)
    keep today's behavior: the tool is recorded, the 2e8264fb4 bypass stays."""
    async def _noop_resume(session, registry, answer):
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)
    session = _waiting_session()
    commands = _commands_for(session)

    async def _scenario() -> object:
        return await commands.resume_approval(
            run_id="run-rej-1",
            approval_id="execute_code",
            payload="approved",
            idempotency_key="k-app-2",
        )

    receipt = asyncio.run(_scenario())
    assert receipt.accepted
    assert session.approved_tool_names == {"executeCode"}


# ---------------------------------------------------------------------------
# _dispatch_resume level: the approve/reject distinction survives the fold.
# (create_run-level coverage is impossible here: the p1 integration resume
# path 404s on clean HEAD for pre-existing, unrelated reasons.)
# ---------------------------------------------------------------------------


def _dispatch_harness(payload_dict: dict) -> tuple:
    """Run ``_dispatch_resume`` with a recording AsyncMock port; return the port."""
    from unittest.mock import AsyncMock, MagicMock

    from starlette.requests import Request

    from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
        CreateRunRequest,
        _dispatch_resume,
    )

    async def _run() -> tuple:
        request = MagicMock(spec=Request)
        run_port = MagicMock()
        run_port.resume_approval = AsyncMock(
            return_value=MagicMock(accepted=True, status="resumed", error=None, error_status=200)
        )
        request.app.state.run_port = run_port
        store = MagicMock()
        store.record_answer_key = AsyncMock()
        request.app.state.running_operation_store = store

        decoded = MagicMock(spec=CreateRunRequest)
        decoded.run_id = "run-fwd-1"
        decoded.resume_tool_result = payload_dict if "content" in payload_dict else None
        decoded.resume_approval = (
            None if "content" in payload_dict else payload_dict
        )

        res = await _dispatch_resume(request, {"run_id": "run-fwd-1"}, decoded)
        assert res.status_code == 200
        return run_port

    port = asyncio.run(_run())
    return port


def test_dispatch_resume_forwards_is_rejection_true() -> None:
    port = _dispatch_harness(
        {
            "tool_call_id": "tc_rej",
            "approval_id": "tc_rej",
            "parent_message_id": "",
            "rejection_reason": "user said no",
        }
    )
    port.resume_approval.assert_awaited_once()
    kwargs = port.resume_approval.call_args.kwargs
    assert kwargs["is_rejection"] is True
    # The payload string fold is unchanged (wire contract preserved).
    assert port.resume_approval.call_args.args[2] == "user said no"


def test_dispatch_resume_forwards_is_rejection_false_for_tool_result() -> None:
    port = _dispatch_harness(
        {
            "tool_call_id": "tc_ans",
            "content": "the user's answer",
            "parent_message_id": "",
            "plugin_state": None,
        }
    )
    port.resume_approval.assert_awaited_once()
    kwargs = port.resume_approval.call_args.kwargs
    assert kwargs["is_rejection"] is False
