"""ADR-0268 §4: only an in-process dispatcher can make a run a handoff turn.

``origin == "handoff"`` is what puts ``lca.nothing_to_do`` on the wire, and
that tool lets a model end a round without a visible bubble. So the value must
travel on a typed per-run field and must not be reachable from an HTTP body.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    CreateRunRequest,
    _to_run_request,
    decode_create_run,
)
from lca.plugins.transport.webserver.handlers.runs.session.setup.types import (
    RunSessionRequest,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest
from lca.plugins.transport.webserver.read.runs.identity.identity import AgentRef


def _carrier_request() -> CreateRunRequest:
    return CreateRunRequest(
        profile="web-assistant",
        question="hi",
        user_text="hi",
        mode="solo",
        attachment_ids=(),
        prior_turns=(),
        agent=AgentRef(agent_id="solo", name="solo"),
        device_id="",
        plane="",
        extra_plane="",
        execution_target="",
        options={},
        ctx=None,
    )


def test_run_request_defaults_to_a_user_turn() -> None:
    assert RunRequest(**_run_request_kwargs()).origin == "user"


def test_the_carrier_decode_target_has_no_origin_field() -> None:
    """No field means no body key can reach it, so no client can claim a handoff."""
    names = {f.name for f in dataclasses.fields(CreateRunRequest)}
    assert "origin" not in names


def test_to_run_request_never_carries_an_origin() -> None:
    assert _to_run_request(_carrier_request()).origin == "user"


@pytest.mark.asyncio
async def test_a_body_claiming_handoff_still_decodes_to_a_user_turn() -> None:
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": "hi"}],
        "origin": "handoff",
        "options": {"origin": "handoff"},
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=None,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert _to_run_request(decoded).origin == "user"


def test_run_session_request_defaults_to_a_user_turn() -> None:
    assert RunSessionRequest(question="hi", user_text="hi").origin == "user"


def test_run_session_request_carries_an_explicit_handoff() -> None:
    request = RunSessionRequest(question="hi", user_text="hi", origin="handoff")
    assert request.origin == "handoff"


def _run_request_kwargs() -> dict[str, Any]:
    return {
        "profile": "web-assistant",
        "question": "hi",
        "user_text": "hi",
        "mode": "solo",
        "attachment_ids": (),
        "prior_turns": (),
        "agent": AgentRef(agent_id="solo", name="solo"),
        "device_id": "",
        "plane": "",
        "extra_plane": "",
        "execution_target": "",
        "options": {},
        "ctx": None,
    }
