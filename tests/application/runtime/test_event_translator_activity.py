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


def test_gateway_wire_path_feeds_activity_projector():
    """Web-UI runs use step.tool_call.record + ToolInvoked (catalog path).

    ``phase.tool.call.start`` / ``body.tool.execute.end`` are suppressed in
    the gateway pump, so the activity projector must be fed from the
    non-suppressed spine start and the catalog end.
    """
    translator = EventTranslator()

    # 1. step.tool_call.record → activity_updated running + tools_calling chunk
    stamped_start = {
        "event": {
            "execution_point": "step.tool_call.record",
            "payload": {
                "invocation_id": "call_gw_1",
                "run_id": "run_gw_1",
                "tool_name": "read_assistant_self_config",
                "arguments": {},
            },
        },
    }
    wire_events = translator.translate(stamped_start)
    assert isinstance(wire_events, list)
    assert any(e.get("type") == "stream_chunk" for e in wire_events)
    start_activity = next((e for e in wire_events if e.get("type") == "activity_updated"), None)
    assert start_activity is not None
    assert start_activity["data"]["id"] == "call_gw_1"
    assert start_activity["data"]["status"] == "running"

    # 2. ToolInvoked (catalog end) → activity_updated completed + tool_end
    stamped_end = {
        "event": {
            "type": "ToolInvoked",
            "isSuccess": True,
            "executionTime": 120,
            "projected_state": {},
            "result": {"content": "已读取 SOUL.md"},
            "payload": {
                "toolCalling": {
                    "id": "call_gw_1",
                    "apiName": "read_assistant_self_config",
                }
            },
        },
    }
    wire_end = translator.translate(stamped_end)
    assert isinstance(wire_end, list)
    assert any(e.get("type") == "tool_end" for e in wire_end)
    end_activity = next((e for e in wire_end if e.get("type") == "activity_updated"), None)
    assert end_activity is not None
    assert end_activity["data"]["id"] == "call_gw_1"
    assert end_activity["data"]["status"] == "completed"
    assert end_activity["data"]["durationMs"] == 120
    assert "已读取 SOUL.md" in (end_activity["data"].get("resultSummary") or "")

    # 3. Projector populated under the unstamped default bucket (gateway runs
    # do not carry assistant_id on these events).
    items = get_global_activity_projector().get_activities("asst_gw_any")
    assert any(item.id == "call_gw_1" and item.status == "completed" for item in items)


def test_tool_started_and_denied_catalog_events_emit_activity_updated():
    translator = EventTranslator()

    # ToolStarted catalog event
    stamped_started = {
        "event": {
            "type": "ToolStarted",
            "tool_name": "GITHUB_LIST_BRANCHES",
            "invocation_id": "call_gh_branches",
            "arguments": {"owner": "smartlijingyang-sudo", "repo": "layered-cognitive-agent"},
            "assistant_id": "asst_dev",
            "run_id": "run_gh_1",
            "timestamp": "2026-10-03T12:00:00Z",
            "payload": {
                "id": "call_gh_branches",
                "apiName": "GITHUB_LIST_BRANCHES",
            },
        }
    }
    wire_start = translator.translate(stamped_started)
    assert isinstance(wire_start, list)
    assert any(e.get("type") == "tool_start" for e in wire_start)
    act_start = next((e for e in wire_start if e.get("type") == "activity_updated"), None)
    assert act_start is not None
    assert act_start["data"]["id"] == "call_gh_branches"
    assert act_start["data"]["status"] == "running"
    assert act_start["data"]["title"] == "检索 GitHub 分支"

    # ToolDenied catalog event
    stamped_denied = {
        "event": {
            "type": "ToolDenied",
            "tool_name": "GITHUB_LIST_BRANCHES",
            "invocation_id": "call_gh_branches",
            "reason": "Permission denied by security policy",
            "assistant_id": "asst_dev",
            "run_id": "run_gh_1",
        }
    }
    wire_denied = translator.translate(stamped_denied)
    assert isinstance(wire_denied, list)
    assert any(e.get("type") == "tool_end" for e in wire_denied)
    act_denied = next((e for e in wire_denied if e.get("type") == "activity_updated"), None)
    assert act_denied is not None
    assert act_denied["data"]["id"] == "call_gh_branches"
    assert act_denied["data"]["status"] == "failed"
    assert "Permission denied" in (act_denied["data"].get("resultSummary") or "")
