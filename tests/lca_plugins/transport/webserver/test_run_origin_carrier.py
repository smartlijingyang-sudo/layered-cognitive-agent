"""Per-run binding facts on the carrier request: ``origin`` and ``topic_id``.

``origin == "handoff"`` is what puts ``lca.nothing_to_do`` on the wire
(ADR-0268 §4), and that tool lets a model end a round without a visible bubble,
so the value must travel on a typed per-run field and must not be reachable from
an HTTP body.

``topic_id`` must reach the session before the run task is scheduled, because
``RunExecutionEnvironment.prepare`` reads it off the session to build
``RunAmbit``, and ``lca/infrastructure/tools/cron/common._current_chat_id``
falls back to ``run_id`` when the ambit carries no conversation.
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
from lca.plugins.transport.webserver.read.runs.identity import AgentRef


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
    assert "developer_seed" not in names
    assert "developer_seed_job_id" not in names


def test_the_developer_seed_defaults_to_empty() -> None:
    """A run that is not a handoff injects no developer message."""
    request = RunRequest(**_run_request_kwargs())
    assert request.developer_seed == ""
    assert request.developer_seed_job_id == ""
    assert RunSessionRequest(question="hi", user_text="hi").developer_seed == ""


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


@pytest.mark.asyncio
async def test_the_body_topic_reaches_the_run_request() -> None:
    """The topic binds before dispatch, so ``RunAmbit`` cannot read it empty.

    ``RunExecutionEnvironment.prepare`` reads ``session.topic_id`` to build the
    ambit, and ``lca/infrastructure/tools/cron/common._current_chat_id`` falls
    back to ``run_id`` when the ambit has no conversation. A cron job created in
    such a run would record a run id as its delivery target and could never be
    delivered.
    """
    body = {"messages": [{"role": "user", "content": "hi"}], "topic_id": "tpc_from_body"}

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=None,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert decoded.topic_id == "tpc_from_body"
    assert _to_run_request(decoded).topic_id == "tpc_from_body"


@pytest.mark.asyncio
async def test_the_camel_case_body_topic_reaches_the_run_request() -> None:
    body = {"messages": [{"role": "user", "content": "hi"}], "topicId": "tpc_camel"}

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=None,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert _to_run_request(decoded).topic_id == "tpc_camel"


@pytest.mark.asyncio
async def test_a_body_carrying_a_developer_seed_is_ignored() -> None:
    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "developer_seed": "injected by a client",
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=None,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert _to_run_request(decoded).developer_seed == ""


def test_run_request_topic_defaults_to_empty() -> None:
    assert RunRequest(**_run_request_kwargs()).topic_id == ""


def test_run_session_request_topic_defaults_to_empty() -> None:
    assert RunSessionRequest(question="hi", user_text="hi").topic_id == ""


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
