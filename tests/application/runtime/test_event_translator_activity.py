from __future__ import annotations

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.infrastructure.observability.activity_projector import get_global_activity_projector


def test_event_translator_emits_activity_updated_on_start_and_end():
    translator = EventTranslator()

    # 1. tool start generates activity_updated running
    stamped_start = {
        "event": {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_abc",
                "run_id": "run_001",
                "assistant_id": "architect",
                "tool_name": "hatch_gws_cli",
                "arguments": {"action": "search", "service": "gmail", "query": "invoice"},
            },
        },
    }
    wire_events = translator.translate(stamped_start)
    assert isinstance(wire_events, list)
    activity_msg = next((e for e in wire_events if e.get("type") == "activity_updated"), None)
    assert activity_msg is not None
    data = activity_msg["data"]
    assert data["id"] == "call_abc"
    assert data["status"] == "running"
    assert data["title"] == "正在搜索 Gmail 邮件"
    assert data["icon"] == "mail"

    # 2. tool end generates activity_updated completed
    stamped_end = {
        "event": {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "invocation_id": "call_abc",
                "run_id": "run_001",
                "assistant_id": "architect",
                "tool_name": "hatch_gws_cli",
                "ok": True,
                "latency_ms": 250,
                "message": {"content": "Found 3 invoice emails"},
            },
        },
    }
    wire_end = translator.translate(stamped_end)
    assert isinstance(wire_end, list)
    end_activity_msg = next((e for e in wire_end if e.get("type") == "activity_updated"), None)
    assert end_activity_msg is not None
    end_data = end_activity_msg["data"]
    assert end_data["id"] == "call_abc"
    assert end_data["status"] == "completed"
    assert end_data["durationMs"] == 250
    assert "Found 3 invoice emails" in (end_data.get("resultSummary") or "")

    # 3. Global projector should be populated
    items = get_global_activity_projector().get_activities("architect")
    assert any(item.id == "call_abc" and item.status == "completed" for item in items)
