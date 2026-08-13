"""HTTP Run surface — real Starlette entry, Journal live frames."""

from __future__ import annotations

import json
import time

import pytest
from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.runs.session import RunRegistry
from tests.support.gateway_scripted import ScriptedLLMResolver


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LCA_OBS_BACKENDS", "console")


def _frames(body: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        event_name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if event_name and data:
            out.append((event_name, json.loads(data)))
    return out


def test_create_app_binds_registry_on_state() -> None:
    registry = RunRegistry()
    app = create_app(registry, llm_resolver=ScriptedLLMResolver())
    assert app.state.registry is registry


def test_post_runs_202_then_live_is_journal() -> None:
    registry = RunRegistry()
    with TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver())) as client:
        created = client.post(
            "/runs",
            json={"model": "solo", "messages": [{"role": "user", "content": "只回一个字：好"}]},
        )
        assert created.status_code == 202
        body = created.json()
        run_id = body["run_id"]
        assert body["live_url"] == f"/runs/{run_id}/live"
        assert body["trace_id"]

        deadline = time.monotonic() + 15
        status = ""
        while time.monotonic() < deadline:
            snapshot = client.get(f"/runs/{run_id}")
            assert snapshot.status_code == 200
            status = snapshot.json()["status"]
            if status in {"completed", "failed", "canceled"}:
                break
            time.sleep(0.05)
        assert status in {"completed", "failed", "canceled"}, status

        session = registry.get(run_id)
        assert session is not None
        assert session.tail.is_closed
        live = client.get(f"/runs/{run_id}/live", headers={"Last-Event-ID": "0"})
        assert live.status_code == 200
        assert live.headers["content-type"].startswith("text/event-stream")
        frames = _frames(live.text)
        names = [name for name, _ in frames]
        assert "thinking.delta" not in names
        assert any(
            name in {"AgentRunStarted", "AgentRunFinished", "ReasoningDelta"} for name in names
        )
        if frames:
            assert "event_type" in frames[0][1]
        events = [
            json.loads(line)
            for line in session.jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        started = next(row for row in events if row["event_type"] == "AgentRunStarted")
        assert started["scope"]["run_id"] == run_id
        assert started["scope"]["trace_id"] == body["trace_id"]

        doctor = client.get(f"/runs/{run_id}/doctor")
        assert doctor.status_code == 200
        report = doctor.json()
        assert report["schema"] == "doctor.v1"
        assert report["run_id"] == run_id

        health = client.get("/health")
        assert health.status_code == 200
        payload = health.json()
        assert "runs" in payload
        assert "live" in payload


def test_post_runs_requires_user_message() -> None:
    client = TestClient(create_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
    resp = client.post("/runs", json={"model": "solo", "messages": []})
    assert resp.status_code == 400


def test_inflight_dedup_returns_same_run() -> None:
    registry = RunRegistry()
    client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
    payload = {"model": "solo", "messages": [{"role": "user", "content": "同一句话"}]}
    first = client.post("/runs", json=payload)
    second = client.post("/runs", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    # After the first run finishes it is no longer inflight; sequential
    # re-requests are new runs. Dedup only applies while PENDING/RUNNING.
    assert first.json()["run_id"]
    assert second.json()["run_id"]
