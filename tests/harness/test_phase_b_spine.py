"""Phase B session spine: store, registry, commands, projections, flags."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from lca.contracts.harness.agent import UserMessage
from lca.contracts.harness.command import (
    AnswerCommand,
    MessageSendCommand,
    SessionCreateCommand,
)
from lca.contracts.harness.events import MessageAccepted, SessionCreated, TurnEnded
from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.harness.agent.registry import AgentRegistry
from lca.harness.command.gateway import CommandGateway
from lca.harness.diagnostics.normalizer import ResultNormalizer, compare_results
from lca.harness.flags import session_spine_mode
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.projection.web import ActivityProjection, ConversationProjection
from lca.harness.session.inbox import Inbox
from lca.harness.session.persistence import JsonlSessionPersistence
from lca.harness.session.store import SessionStore
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.tools.calculator import build_tools as build_calculator_tools
from lca.layer4_app.harness_bridge import build_live_agent


def _projections() -> InMemoryProjectionRegistry:
    registry = InMemoryProjectionRegistry()
    registry.register(ConversationProjection())
    registry.register(ActivityProjection())
    return registry


def _header(session_id: str = "ses-1") -> SessionHeader:
    return SessionHeader(version=SESSION_FORMAT_VERSION, id=session_id, created_at=1)


def test_session_store_seq_monotonic(tmp_path: Path) -> None:
    persist = JsonlSessionPersistence(tmp_path / "s.jsonl")
    store = SessionStore(_header(), persistence=persist)

    async def _go() -> None:
        await asyncio.gather(
            store.append(SessionCreated(profile="web-standard")),
            store.append(MessageAccepted(message_id="m1", role="user", content_ref="hi")),
            store.append(TurnEnded(turn=1, reason="completed")),
        )
        events = await store.read_from(0)
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)
        assert seqs == list(range(len(seqs)))

    asyncio.run(_go())


def test_session_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"

    async def _write() -> None:
        store = SessionStore(_header("ses-rt"), persistence=JsonlSessionPersistence(path))
        await store.append(SessionCreated(profile="web-standard"))
        await store.append(MessageAccepted(message_id="m", role="user", content_ref="q"))

    asyncio.run(_write())
    loaded = SessionStore.load(JsonlSessionPersistence(path))
    assert loaded.header.id == "ses-rt"
    assert [e.type for e in loaded.events()] == [
        "session.created.v1",
        "message.accepted.v1",
    ]


def test_inbox_dual_queue(tmp_path: Path) -> None:
    store = SessionStore(_header(), persistence=JsonlSessionPersistence(tmp_path / "i.jsonl"))
    inbox = Inbox(store)

    async def _go() -> None:
        await inbox.followup(UserMessage(content="next turn", message_id="a"))
        await inbox.steer(UserMessage(content="steer", message_id="b"))
        await inbox.inject(UserMessage(content="ctx", message_id="c"))
        assert inbox.claim_next_turn()[0].content == "next turn"
        step = inbox.claim_next_step()
        assert [m.message_id for m in step] == ["b", "c"]
        assert inbox.claim_next_turn() is None

    asyncio.run(_go())


def test_command_gateway_create_and_message(tmp_path: Path) -> None:
    projections = _projections()
    registry = AgentRegistry(
        sessions_dir=tmp_path, projections=projections, live_builder=build_live_agent
    )
    gateway = CommandGateway(registry, projections)

    async def _go() -> None:
        created = await gateway.handle_create_session(
            SessionCreateCommand(
                idempotency_key="id-1",
                profile="web-standard",
                agent_options={
                    "llm": MockLLMAdapter(),
                    "tools": build_calculator_tools(),
                    "max_steps": 8,
                },
            )
        )
        assert created.accepted
        again = await gateway.handle_create_session(
            SessionCreateCommand(idempotency_key="id-1", profile="web-standard")
        )
        assert again.session_id == created.session_id
        sent = await gateway.handle_send_message(
            MessageSendCommand(
                idempotency_key="id-2",
                session_id=created.session_id,
                role="user",
                content="123 乘以 456 等于多少？",
            )
        )
        assert sent.accepted
        snapshot = await gateway.get_snapshot(created.session_id)
        assert snapshot.as_of_seq >= 0
        activity = snapshot.values["activity"]
        assert activity["status"] in {"completed", "idle", "failed", "waiting_input"}
        conversation = snapshot.values["conversation"]
        if activity["status"] == "completed":
            assert conversation["last_assistant_message"]
            assert "56088" in conversation["last_assistant_message"]

    asyncio.run(_go())


def test_resume_after_reload(tmp_path: Path) -> None:
    projections = _projections()
    registry = AgentRegistry(
        sessions_dir=tmp_path, projections=projections, live_builder=build_live_agent
    )

    async def _go() -> None:
        handle = await registry.create(
            "web-standard",
            session_id="ses-resume",
            options={"llm": MockLLMAdapter(), "tools": build_calculator_tools()},
        )
        await handle.agent.followup(UserMessage(content="1+1"))
        assert (tmp_path / "ses-resume.jsonl").exists()

        projections2 = _projections()
        registry2 = AgentRegistry(
            sessions_dir=tmp_path,
            projections=projections2,
            live_builder=build_live_agent,
        )
        resumed = await registry2.resume("ses-resume")
        assert resumed.agent.session_id == "ses-resume"
        snap = projections2.snapshot("ses-resume")
        assert snap.values["activity"]["status"] in {"completed", "waiting_input", "failed"}

    asyncio.run(_go())


def test_answer_without_live_agent_resumes(tmp_path: Path) -> None:
    projections = _projections()
    registry = AgentRegistry(
        sessions_dir=tmp_path, projections=projections, live_builder=build_live_agent
    )
    gateway = CommandGateway(registry, projections)

    async def _go() -> None:
        created = await gateway.handle_create_session(
            SessionCreateCommand(
                idempotency_key="a",
                profile="web-standard",
                agent_options={"llm": MockLLMAdapter()},
            )
        )
        sid = created.session_id
        await registry.dispose(sid)
        assert registry.get(sid) is None
        receipt = await gateway.handle_answer(AnswerCommand(session_id=sid, answer="ok"))
        assert receipt.accepted
        assert registry.get(sid) is not None

    asyncio.run(_go())


def test_normalizer_status_buckets() -> None:
    class _Res:
        status = type("S", (), {"value": "completed"})()
        output = "hi"
        tool_calls = ()
        llm_calls = 0
        error = None
        journal_events = ()

    from lca.contracts.harness.projection import ProjectionSnapshot

    legacy = ResultNormalizer.from_task_result(_Res())
    snap = ProjectionSnapshot(
        as_of_seq=1,
        values={
            "conversation": {"last_assistant_message": "hi"},
            "activity": {"status": "completed"},
        },
    )
    report = compare_results(
        session_id="s",
        legacy=_Res(),
        snapshot=snap,
        journal=[],
    )
    assert report.divergences == ()
    assert legacy.status == "completed"


def test_session_spine_defaults_off() -> None:
    previous = os.environ.pop("LCA_SESSION_SPINE", None)
    try:
        assert session_spine_mode() == "off"
        os.environ["LCA_SESSION_SPINE"] = "shadow"
        assert session_spine_mode() == "shadow"
    finally:
        if previous is None:
            os.environ.pop("LCA_SESSION_SPINE", None)
        else:
            os.environ["LCA_SESSION_SPINE"] = previous


def test_command_gateway_import_boundary() -> None:
    source = Path("lca/harness/command/gateway.py").read_text(encoding="utf-8")
    assert "contracts.harness.agent" not in source
    assert "layer1_cognitive" not in source
    assert "layer2_runtime" not in source
    assert "layer3_agent" not in source


def test_v1_sessions_routes_exist() -> None:
    from gateway.app import create_app

    paths = {getattr(route, "path", "") for route in create_app().routes}
    assert "/v1/sessions" in paths
    assert "/v1/sessions/{session_id}/snapshot" in paths
    assert "/v1/sessions/{session_id}/events" in paths
