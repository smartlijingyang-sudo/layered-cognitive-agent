"""HIL: waiting_input must not close LiveTail; answer resumes the same run."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest
from starlette.testclient import TestClient

from gateway.runs.execute import create_run_session, execute_run, resume_run
from gateway.runs.session import RunRegistry, RunStatus
from lca.contracts.protocols import LLMAdapter
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond, use_tool
from tests.support.gateway_app import create_scripted_app

_ASK = {
    "questions": [
        {
            "question": "选哪个方案?",
            "header": "方案",
            "options": [
                {"label": "A", "description": "快"},
                {"label": "B", "description": "稳"},
            ],
        }
    ]
}


@dataclass(frozen=True)
class _Resolver:
    llm: LLMAdapter

    def is_available(self) -> bool:
        return True

    def resolve(self, *, mode: str | None = None) -> LLMAdapter:
        del mode
        return self.llm


def _ask_then_reply() -> ScriptedLLMAdapter:
    return ScriptedLLMAdapter(
        {
            "助手": [
                use_tool("askUserQuestion", _ASK),
                respond("收到，按 A 做"),
            ]
        }
    )


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LCA_OBS_BACKENDS", "console")


@pytest.mark.asyncio
async def test_waiting_input_does_not_close_tail() -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    resolver = _Resolver(_ask_then_reply())
    registry = RunRegistry()
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        ctx.provide("llm_resolver", resolver)
        session = create_run_session(
            registry,
            question="请用户选方案",
            user_text="请用户选方案",
            mode="solo",
            ctx=ctx,
        )
        await execute_run(
            registry, run_id=session.run_id, question=session.question, mode="solo", ctx=ctx
        )

    assert session.status == RunStatus.WAITING_INPUT
    assert not session.tail.is_closed
    assert session.hub is not None
    assert session.snapshot is not None
    assert session.runnable is not None
    assert session.approval_request is not None
    assert session.approval_request["type"] == "ask_user_question"


class _HangingResumable:
    async def resume(self, snapshot: object, *, input: str) -> object:
        del snapshot, input
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_resume_cancellation_terminalizes_run() -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    registry = RunRegistry()
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        ctx.provide("llm_resolver", _Resolver(_ask_then_reply()))
        session = create_run_session(
            registry,
            question="请用户选方案",
            user_text="请用户选方案",
            mode="solo",
            ctx=ctx,
        )
        await execute_run(
            registry, run_id=session.run_id, question=session.question, mode="solo", ctx=ctx
        )

    assert session.status == RunStatus.WAITING_INPUT
    session.runnable = _HangingResumable()
    task = asyncio.create_task(resume_run(session, registry, "A"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.status == RunStatus.CANCELED
    assert session.tail.is_closed


@pytest.mark.asyncio
async def test_answer_resumes_same_run_and_finalizes() -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    resolver = _Resolver(_ask_then_reply())
    registry = RunRegistry()
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        ctx.provide("llm_resolver", resolver)
        session = create_run_session(
            registry,
            question="请用户选方案",
            user_text="请用户选方案",
            mode="solo",
            ctx=ctx,
        )
        await execute_run(
            registry, run_id=session.run_id, question=session.question, mode="solo", ctx=ctx
        )
    assert session.status == RunStatus.WAITING_INPUT
    tail = session.tail

    await resume_run(session, registry, "A")

    assert session.status == RunStatus.COMPLETED
    assert tail.is_closed
    assert session.hub is not None


def test_http_waiting_input_snapshot_and_answer() -> None:
    registry = RunRegistry()
    app = create_scripted_app(registry, llm_resolver=_Resolver(_ask_then_reply()))
    with TestClient(app) as client:
        created = client.post(
            "/runs",
            json={"model": "solo", "messages": [{"role": "user", "content": "请用户选方案"}]},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        status = ""
        snapshot = {}
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            resp = client.get(f"/runs/{run_id}")
            assert resp.status_code == 200
            snapshot = resp.json()
            status = snapshot["status"]
            if status in {"waiting_input", "failed", "completed", "canceled"}:
                break
            time.sleep(0.05)

        assert status == "waiting_input", snapshot
        assert snapshot["approval_request"]["type"] == "ask_user_question"
        session = registry.get(run_id)
        assert session is not None
        assert not session.tail.is_closed
        assert session.tail.last_seq > 0

        answered = client.post(f"/runs/{run_id}/answer", json={"answer": "A"})
        assert answered.status_code == 200
        assert answered.json()["status"] == "resumed"

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = client.get(f"/runs/{run_id}").json()["status"]
            if status in {"completed", "failed", "canceled"}:
                break
            time.sleep(0.05)
        assert status == "completed"
        assert session.tail.is_closed
