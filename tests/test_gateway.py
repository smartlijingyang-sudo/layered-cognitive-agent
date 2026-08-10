"""Starlette 网关集成测试（scripted LLM 经依赖注入，无 API Key）。"""

from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.llm_resolver import ProductionLLMResolver
from gateway.run_registry import RunRegistry
from lca.contracts.models.core.llm import LLMResponse
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond
from tests.support.gateway_scripted import ScriptedLLMResolver


def _collect_sse(client: TestClient, run_id: str, *, max_frames: int = 500) -> list[dict]:
    frames: list[dict] = []
    with client.stream("GET", f"/runs/{run_id}/events") as response:
        buffer = ""
        for chunk in response.iter_bytes():
            buffer += chunk.decode("utf-8")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                if not block.strip():
                    continue
                data_line = next((ln for ln in block.splitlines() if ln.startswith("data: ")), None)
                if data_line is None:
                    continue
                frames.append(json.loads(data_line[6:]))
                if len(frames) >= max_frames:
                    return frames
    return frames


def _collect_sse_until_types(
    client: TestClient,
    run_id: str,
    required: set[str],
    *,
    timeout_s: float = 15.0,
) -> set[str]:
    """订阅 SSE 直到出现所需事件类型（不必等 run 全程结束）。"""
    seen: set[str] = set()
    deadline = time.monotonic() + timeout_s
    with client.stream("GET", f"/runs/{run_id}/events") as response:
        buffer = ""
        for chunk in response.iter_bytes():
            if time.monotonic() > deadline:
                break
            buffer += chunk.decode("utf-8")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                data_line = next((ln for ln in block.splitlines() if ln.startswith("data: ")), None)
                if data_line is None:
                    continue
                payload = json.loads(data_line[6:])
                seen.add(payload["event_type"])
                if required.issubset(seen):
                    return seen
    return seen


def _wait_until_done(client: TestClient, run_id: str, *, timeout_s: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(f"/runs/{run_id}")
        payload = response.json()
        if payload.get("status") in ("completed", "failed"):
            return payload
        time.sleep(0.02)
    raise TimeoutError(f"run {run_id} did not finish within {timeout_s}s")


class TestObservabilityGateway(unittest.TestCase):
    def test_health(self) -> None:
        client = TestClient(create_app(RunRegistry(), llm_resolver=ScriptedLLMResolver()))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("llm_available", payload)
        self.assertTrue(payload["llm_available"])

    def test_create_run_without_llm_returns_503(self) -> None:
        registry = RunRegistry()
        resolver = ProductionLLMResolver()
        with patch("gateway.llm_resolver.llm_credentials", return_value=(None, None, None)):
            client = TestClient(create_app(registry, llm_resolver=resolver))
            response = client.post(
                "/runs",
                json={"question": "solo probe", "mode": "solo"},
            )
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["error"], "llm_unavailable")

    def test_create_run_and_stream_events(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        create = client.post(
            "/runs",
            json={"question": "solo probe", "mode": "solo"},
        )
        self.assertEqual(create.status_code, 201)
        run_id = create.json()["run_id"]
        self.assertTrue(run_id)

        final = _wait_until_done(client, run_id)
        self.assertEqual(final["status"], "completed")

        events = _collect_sse(client, run_id)
        self.assertGreaterEqual(len(events), 2)
        types = {e["event_type"] for e in events}
        self.assertIn("AgentRunStarted", types)
        self.assertIn("AgentRunFinished", types)
        seqs = [e["seq"] for e in events]
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_create_run_auto_mode_streams_casting_events(self) -> None:
        registry = RunRegistry()
        plan = json.dumps(
            {
                "selected": [
                    {"role_id": "product/product-manager"},
                    {"role_id": "marketing/marketing-content-creator"},
                ],
                "governance": {"kind": "fan_out"},
                "rationale": "test",
            },
            ensure_ascii=False,
        )
        llm = ScriptedLLMAdapter(
            {
                "caster": [LLMResponse(text=plan, model="scripted-llm")],
                "产品经理": [respond("pm output")],
                "内容创作者": [respond("content output")],
            },
            default_respond=True,
        )

        class _Resolver:
            def is_available(self) -> bool:
                return True

            def resolve(self, *, mode: str) -> ScriptedLLMAdapter:
                del mode
                return llm

        client = TestClient(create_app(registry, llm_resolver=_Resolver()))
        create = client.post(
            "/runs",
            json={"question": "auto probe", "mode": "auto"},
        )
        self.assertEqual(create.status_code, 201)
        run_id = create.json()["run_id"]
        types = _collect_sse_until_types(
            client,
            run_id,
            {"CastingStarted", "CastingCompleted", "TeamRunStarted"},
        )
        self.assertIn("CastingStarted", types)
        self.assertIn("CastingCompleted", types)
        self.assertIn("TeamRunStarted", types)

    def test_last_event_id_replay(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry, llm_resolver=ScriptedLLMResolver()))
        create = client.post(
            "/runs",
            json={"question": "quick", "mode": "solo"},
        )
        run_id = create.json()["run_id"]
        _wait_until_done(client, run_id)
        all_events = _collect_sse(client, run_id)
        self.assertGreaterEqual(len(all_events), 2)
        mid = all_events[0]["seq"]
        with client.stream(
            "GET",
            f"/runs/{run_id}/events",
            headers={"Last-Event-ID": str(mid)},
        ) as response:
            replay: list[dict] = []
            buffer = ""
            for chunk in response.iter_bytes():
                buffer += chunk.decode("utf-8")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    data_line = next(
                        (ln for ln in block.splitlines() if ln.startswith("data: ")), None
                    )
                    if data_line:
                        replay.append(json.loads(data_line[6:]))
            for item in replay:
                self.assertGreater(item["seq"], mid)


if __name__ == "__main__":
    unittest.main()
