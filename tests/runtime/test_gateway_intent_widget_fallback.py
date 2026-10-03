"""Tests for Gateway deterministic connector widget fallback guard (INV-CAP-04)."""

from dataclasses import dataclass, field
from typing import Any

from lca.runtime.session.run_session_writer import (
    RunSessionWriter,
    ensure_intent_widget_in_assistant_message,
)


@dataclass
class _StoredEvent:
    type: str
    seq: int
    data: dict[str, Any]
    time: float = 0.0
    surface_op: Any | None = None
    source_event_seqs: tuple[int, ...] | None = None


@dataclass
class _InMemorySession:
    events: list[Any] = field(default_factory=list)
    next_seq: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> Any:
        event = _StoredEvent(
            type=event_type,
            seq=self.next_seq,
            data=dict(data),
            surface_op=surface_op,
            source_event_seqs=source_event_seqs,
        )
        self.next_seq += 1
        self.events.append(event)
        return event

    def snapshot_events(self) -> tuple[Any, ...]:
        return tuple(self.events)

    @property
    def id(self) -> str:
        return "test-session"


def test_gateway_appends_widget_when_model_omits():
    """INV-CAP-04: Gateway deterministically appends widget tag when model omits it."""
    final_content = ensure_intent_widget_in_assistant_message(
        raw_model_content="已为你发起连接，请点击卡片完成授权。",
        pending_intents=[{"intent_id": "cai_test123", "app_name": "Google Drive"}],
    )
    assert "[widget:connector_auth?intentId=cai_test123&appName=Google+Drive]" in final_content
    assert final_content.startswith("已为你发起连接，请点击卡片完成授权。")


def test_gateway_does_not_duplicate_when_model_already_included_intent():
    """INV-CAP-04: Gateway does not duplicate widget if intentId already in content."""
    original = "已为你发起连接：\n[widget:connector_auth?intentId=cai_test123&appName=Google+Drive]"
    final_content = ensure_intent_widget_in_assistant_message(
        raw_model_content=original,
        pending_intents=[{"intent_id": "cai_test123", "app_name": "Google Drive"}],
    )
    assert final_content == original
    assert final_content.count("cai_test123") == 1


def test_gateway_handles_none_raw_model_content():
    """INV-CAP-04: Returns widget markup when raw_model_content is None."""
    final_content = ensure_intent_widget_in_assistant_message(
        raw_model_content=None,
        pending_intents=[{"intent_id": "cai_test123", "app_name": "Google Drive"}],
    )
    assert final_content == "[widget:connector_auth?intentId=cai_test123&appName=Google+Drive]"


def test_run_session_writer_auto_appends_widget_from_prior_tool_result():
    """INV-CAP-04: RunSessionWriter.append_assistant_message automatically extracts unmounted intents."""
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    # 模拟 tool_result 事件携带 intent_id
    tool_obs_content = (
        "IMPORTANT DISPLAY INSTRUCTION: You MUST include the following card tag:\n"
        "[widget:connector_auth?appName=Google+Drive&connectionId=conn_123&intentId=cai_auto_456]\n"
        "Do NOT output any raw URL."
    )
    writer.append_tool_result(
        turn=1,
        step=1,
        call_id="call_123",
        content=tool_obs_content,
        error=None,
        meta={"tool_name": "composioConnect"},
    )

    # 模型输出文本遗漏了 widget 标签
    writer.append_assistant_message(
        turn=1,
        step=2,
        role="assistant",
        content="已为您发起连接，请授权后继续。",
        tool_calls=None,
        usage=None,
    )

    # 断言持久化到 session 中的事实必定携带了 widget 标签
    snapshot = session.snapshot_events()
    asst_event = next(e for e in snapshot if e.type == "surface/assistant_message")
    saved_content = asst_event.data["content"]
    assert "cai_auto_456" in saved_content
    assert "[widget:connector_auth?intentId=cai_auto_456" in saved_content


def test_run_session_writer_no_duplicate_on_subsequent_turns():
    """INV-CAP-04: Intents mounted on prior turns are not duplicated on subsequent turns."""
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    # Turn 1: tool_result 生成 intent
    writer.append_tool_result(
        turn=1,
        step=1,
        call_id="call_123",
        content="[widget:connector_auth?appName=Gmail&intentId=cai_turn1]",
        error=None,
        meta={"tool_name": "composioConnect"},
    )

    # Turn 1: 模型输出，网关自动挂载
    writer.append_assistant_message(
        turn=1,
        step=2,
        role="assistant",
        content="请点击下方卡片授权",
        tool_calls=None,
        usage=None,
    )

    # Turn 2: 新一轮对话，模型输出普通文本，没有新 tool_result
    writer.append_assistant_message(
        turn=2,
        step=1,
        role="assistant",
        content="好的，请问还有其他问题吗？",
        tool_calls=None,
        usage=None,
    )

    snapshot = session.snapshot_events()
    asst_events = [e for e in snapshot if e.type == "surface/assistant_message"]
    assert len(asst_events) == 2
    # Turn 1 携带了 widget
    assert "cai_turn1" in asst_events[0].data["content"]
    # Turn 2 绝对不重复挂载 Turn 1 的 widget
    assert "cai_turn1" not in asst_events[1].data["content"]
    assert asst_events[1].data["content"] == "好的，请问还有其他问题吗？"
