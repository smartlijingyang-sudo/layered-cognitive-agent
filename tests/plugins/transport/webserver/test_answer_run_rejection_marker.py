"""RA-138: the legacy POST /runs/{run_id}/answer ingress must not silently
default is_rejection to False.

Evidence (direction b): the LobeHub frontend still calls the legacy route --
``deploy/lobehub/patches/ui/WidgetCard.tsx:66`` POSTs to
``/lca-api/runs/${runId}/answer`` with ``{approval_id, idempotency_key,
payload}``, a pure-string payload that cannot express rejection. The port's
``is_rejection=False`` default then turned "cannot express" into "approved",
making RA-131's record-point guard a dead letter on this route.

Fix: ``answer_run`` now honors an in-band ``rejection_reason`` marker on the
legacy body (same marker as ``_dispatch_resume``'s RA-131 seam) and passes
``is_rejection`` explicitly to the port. A rejection sent via /answer is no
longer recorded into ``approved_tool_names``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.handlers.runs.api import (
    command_endpoints,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.registry import (
    commands as registry_commands,
)


def _answer_request(body: dict[str, Any], port: Any) -> MagicMock:
    request = MagicMock(spec=Request)
    request.path_params = {"run_id": "run-rej-1"}
    request.json = AsyncMock(return_value=body)
    request.app.state.run_port = port
    request.app.state.running_operation_store = None
    return request


async def _answer_run(body: dict[str, Any], port: Any):
    request = _answer_request(body, port)
    return await command_endpoints.answer_run(request)


def _fake_port() -> MagicMock:
    port = MagicMock()
    port.resume_approval = AsyncMock(
        return_value=MagicMock(accepted=True, status="resumed", error=None, error_status=200)
    )
    return port


@pytest.fixture(autouse=True)
def _skip_ownership_and_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(name="answer_session")
    monkeypatch.setattr(
        command_endpoints,
        "_validate_run_ownership",
        AsyncMock(return_value=(None, session)),
    )
    monkeypatch.setattr(
        command_endpoints,
        "_ensure_recovered_session",
        AsyncMock(return_value=session),
    )


def test_answer_run_forwards_is_rejection_true_with_marker() -> None:
    port = _fake_port()
    res = asyncio.run(
        _answer_run(
            {
                "approval_id": "widget",
                "idempotency_key": "run-rej-1:widget",
                "payload": "user said no",
                "rejection_reason": "user said no",
            },
            port,
        )
    )
    assert res.status_code == 200
    port.resume_approval.assert_awaited_once()
    assert port.resume_approval.call_args.kwargs["is_rejection"] is True


def test_answer_run_forwards_is_rejection_false_without_marker() -> None:
    """The current widget frontend posts no marker: legacy approve-only behavior."""
    port = _fake_port()
    res = asyncio.run(
        _answer_run(
            {
                "approval_id": "widget",
                "idempotency_key": "run-rej-1:widget",
                "payload": "option-a",
            },
            port,
        )
    )
    assert res.status_code == 200
    port.resume_approval.assert_awaited_once()
    assert port.resume_approval.call_args.kwargs["is_rejection"] is False
    # Wire contract unchanged: payload forwarded verbatim.
    assert port.resume_approval.call_args.args[2] == "option-a"


# ---------------------------------------------------------------------------
# Record-point level: a rejection sent via /answer is not recorded into
# approved_tool_names (the test that was unwritable before this fix).
# ---------------------------------------------------------------------------


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


def _real_port(session: RunSession) -> registry_commands.RegistryRunCommands:
    class _RegistryStub:
        def get(self, run_id: str) -> RunSession | None:
            return session if run_id == "run-rej-1" else None

    return registry_commands.RegistryRunCommands(_RegistryStub())  # type: ignore[arg-type]


def _noop_resume_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_resume(session, registry, answer):
        return None

    monkeypatch.setattr(registry_commands, "resume_run", _noop_resume)


def test_rejection_via_answer_not_recorded_into_approved_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _noop_resume_patch(monkeypatch)
    session = _waiting_session()
    res = asyncio.run(
        _answer_run(
            {
                "approval_id": "execute_code",
                "idempotency_key": "k-rej-answer-1",
                "payload": "user said no",
                "rejection_reason": "user said no",
            },
            _real_port(session),
        )
    )
    assert res.status_code == 200
    assert session.approved_tool_names == set()


def test_approval_via_answer_still_records_canonicalized_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _noop_resume_patch(monkeypatch)
    session = _waiting_session()
    res = asyncio.run(
        _answer_run(
            {
                "approval_id": "execute_code",
                "idempotency_key": "k-app-answer-1",
                "payload": "approved",
            },
            _real_port(session),
        )
    )
    assert res.status_code == 200
    assert session.approved_tool_names == {"executeCode"}
