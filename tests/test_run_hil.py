"""HIL: waiting_input must not close LiveTail; answer resumes the same run."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.runs.execute import create_run_session, execute_run, resume_run, set_llm_resolver
from gateway.runs.session import RunRegistry, RunStatus
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_resolver import ProductionLLMResolver
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond, use_tool

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


@pytest.fixture
def _restore_resolver() -> None:
    yield
    set_llm_resolver(ProductionLLMResolver())


@pytest.mark.asyncio
async def test_waiting_input_does_not_close_tail(_restore_resolver: None) -> None:
    set_llm_resolver(_Resolver(_ask_then_reply()))
    registry = RunRegistry()
    session = create_run_session(
        registry,
        question="请用户选方案",
        user_text="请用户选方案",
        mode="solo",
    )
    await execute_run(registry, run_id=session.run_id, question=session.question, mode="solo")

    assert session.status == RunStatus.WAITING_INPUT
    assert not session.tail.is_closed
    assert session.hub is not None
    assert session.snapshot is not None
    assert session.runnable is not None
    assert session.approval_request is not None
    assert session.approval_request["type"] == "ask_user_question"


@pytest.mark.asyncio
async def test_answer_resumes_same_run_and_finalizes(_restore_resolver: None) -> None:
    set_llm_resolver(_Resolver(_ask_then_reply()))
    registry = RunRegistry()
    session = create_run_session(
        registry,
        question="请用户选方案",
        user_text="请用户选方案",
        mode="solo",
    )
    await execute_run(registry, run_id=session.run_id, question=session.question, mode="solo")
    assert session.status == RunStatus.WAITING_INPUT
    tail = session.tail

    await resume_run(session, registry, "A")

    assert session.status == RunStatus.COMPLETED
    assert tail.is_closed
    assert session.hub is not None


def test_http_waiting_input_snapshot_and_answer(_restore_resolver: None) -> None:
    registry = RunRegistry()
    app = create_app(registry, llm_resolver=_Resolver(_ask_then_reply()))
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
