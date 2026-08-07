"""Starlette 网关集成测试（scripted LLM，无 API Key）。"""

from __future__ import annotations

import json
import time
import unittest

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.run_registry import RunRegistry


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
        client = TestClient(create_app(RunRegistry()))
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("llm_available", payload)
        self.assertIn("default_track", payload)

    def test_create_run_and_stream_events(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry))
        create = client.post(
            "/runs",
            json={"question": "solo probe", "mode": "solo", "track": "scripted"},
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
        self.assertEqual(sorted(seqs), list(range(min(seqs), min(seqs) + len(seqs))))

    def test_last_event_id_replay(self) -> None:
        registry = RunRegistry()
        client = TestClient(create_app(registry))
        create = client.post(
            "/runs",
            json={"question": "quick", "mode": "solo", "track": "scripted"},
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
