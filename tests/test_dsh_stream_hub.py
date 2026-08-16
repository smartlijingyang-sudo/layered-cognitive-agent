"""DeviceHub DSH streaming session tests."""

from __future__ import annotations

import asyncio

import pytest

from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.streaming_dsh_runtime import StreamingDshRuntime
from lca.layer0_infra.dsh.driver import DshTurnDriver, DshTurnSpec
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.projector import DshJournalProjector
from lca.layer0_infra.dsh.settings import DshSettings
from lca.layer0_infra.dsh.wire import DSH_RUN_TURN_REQUEST
from tests.test_dsh_driver import _Archive, _Sink


class _FakeConn:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class _FakeRegistry:
    def __init__(self, conn: _FakeConn | None) -> None:
        self._conn = conn

    def channel(self, device_id: str):
        del device_id
        return type("Conn", (), {"websocket": self._conn})() if self._conn else None


@pytest.mark.asyncio
async def test_hub_streams_notifications_before_turn_finished() -> None:
    conn = _FakeConn()
    hub = DeviceHub(_FakeRegistry(conn))
    seen: list[str] = []

    async def drive() -> DshTurnResult:
        def on_event(notification: DshNotification) -> None:
            event = notification.payload.get("event")
            if isinstance(event, dict):
                seen.append(str(event.get("type") or ""))

        return await hub.run_dsh_turn(
            "dev-1",
            turn_id="run_test",
            params={"prompt": "hi"},
            on_notification=on_event,
            timeout_s=5.0,
        )

    task = asyncio.create_task(drive())
    await asyncio.sleep(0.01)
    assert conn.sent and conn.sent[0]["type"] == DSH_RUN_TURN_REQUEST
    hub.relay_dsh_notification(
        "run_test",
        "session.event",
        {"sessionId": "run_test", "event": {"type": "assistant/chunk", "data": {}}},
    )
    assert seen == ["assistant/chunk"]
    hub.complete_dsh_turn(
        "run_test",
        {
            "success": True,
            "session_id": "run_test",
            "final_response": "done",
            "finish_reason": "completed",
        },
    )
    result = await task
    assert result.final_response == "done"
    assert result.finish_reason == "completed"


@pytest.mark.asyncio
async def test_streaming_runtime_projects_live_events() -> None:
    conn = _FakeConn()
    hub = DeviceHub(_FakeRegistry(conn))
    runtime = StreamingDshRuntime(hub, "dev-1", DshSettings())
    sink = _Sink()
    archive = _Archive()
    driver = DshTurnDriver(runtime, DshJournalProjector(sink), archive)
    spec = DshTurnSpec(
        prompt="hello",
        session_id="run_live",
        cwd="/home/sandbox-user",
        session_root="/home/sandbox-user/runs",
    )

    async def complete_turn() -> None:
        await asyncio.sleep(0.01)
        hub.relay_dsh_notification(
            "run_live",
            "session.event",
            {
                "sessionId": "run_live",
                "event": {
                    "type": "assistant/chunk",
                    "data": {
                        "chunk": {"type": "text-delta", "text": "hi"},
                    },
                },
            },
        )
        hub.complete_dsh_turn(
            "run_live",
            {
                "success": True,
                "session_id": "run_live",
                "final_response": "hi",
                "finish_reason": "completed",
            },
        )

    bg = asyncio.create_task(complete_turn())
    result = await driver.run_async(spec)
    await bg
    assert result.final_response == "hi"
    assert any(type(e).__name__ == "StepTextDelta" for e in sink.events)
    assert len(archive.rows) >= 1
