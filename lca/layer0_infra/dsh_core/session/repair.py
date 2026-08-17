"""1:1 port of ``@deepseek-ai/dsh-session/repair``.

Crash-recovery repair for an interrupted session log.  Preserves a fully
written final turn and supplies the missing tool, step, and turn boundaries
needed to resume with a provider-valid transcript.
"""

from __future__ import annotations

from lca.layer0_infra.dsh_core.session._llm_types import (
    MessageId,
    TextBlock,
    ToolResultContentBlock,
    ToolResultMessage,
)
from lca.layer0_infra.dsh_core.session.types import SessionEvent

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

TOOL_NOT_STARTED: str = "TOOL_NOT_STARTED"
"""Recovery code for an assistant tool request that never reached a recorded call start."""

TOOL_OUTCOME_UNKNOWN: str = "TOOL_OUTCOME_UNKNOWN"
"""Recovery code for a recorded tool call whose completed outcome was not durably recorded."""

# ---------------------------------------------------------------------------
# interrupted_turn_closers
# ---------------------------------------------------------------------------


def interrupted_turn_closers(events: list[SessionEvent]) -> list[SessionEvent]:
    """Return deterministic synthetic events that close an open tail turn.

    Unmatched calls receive error results first, followed by an open
    ``step/end`` and an interrupted ``turn/end``; sequences continue the log
    and timestamps reuse the last real event.  A balanced or empty log returns
    no events.
    """
    open_turn: int | None = None
    open_step: int | None = None
    pending_calls: dict[str, dict[str, object]] = {}

    for event in events:
        match event.type:
            case "turn/start":
                open_turn = event.data.turn if hasattr(event.data, "turn") else event.data["turn"]
                open_step = None
                pending_calls.clear()
            case "turn/end":
                open_turn = None
                open_step = None
                pending_calls.clear()
            case "step/start":
                open_step = event.data.step if hasattr(event.data, "step") else event.data["step"]
            case "step/end":
                pending_calls.clear()
                open_step = None
            case "assistant/message":
                msg = (
                    event.data.message
                    if hasattr(event.data, "message")
                    else event.data["message"]
                )
                content = msg.content if hasattr(msg, "content") else msg["content"]
                for block in content:
                    block_type = block.type if hasattr(block, "type") else block["type"]
                    if block_type == "tool-call":
                        call_id = block.id if hasattr(block, "id") else block["id"]
                        pending_calls[call_id] = {
                            "step": event.data.step if hasattr(event.data, "step") else event.data["step"],
                        }
            case "tool/call":
                call_id = (
                    event.data.callId
                    if hasattr(event.data, "callId")
                    else event.data["callId"]
                )
                entry = pending_calls.get(call_id)
                if entry is not None:
                    entry["callSeq"] = event.seq
            case "tool/result":
                msg = (
                    event.data.message
                    if hasattr(event.data, "message")
                    else event.data["message"]
                )
                src = msg.source if hasattr(msg, "source") else msg["source"]
                src_call_id = src["callId"] if isinstance(src, dict) else getattr(src, "callId", None)
                pending_calls.pop(src_call_id, None)
            case _:
                pass

    # Balanced log: nothing to close.
    last = events[-1] if events else None
    if open_turn is None or last is None:
        return []

    seq = last.seq + 1
    time = last.time
    closers: list[SessionEvent] = []

    # Close calls before their step.
    for call_id, entry in pending_calls.items():
        step = entry["step"]
        call_seq = entry.get("callSeq")
        started = call_seq is not None

        if started:
            error_text = (
                "The tool call was interrupted after it was recorded, but no "
                "result was durably recorded. Its outcome is unknown. Decide "
                "whether to retry from the tool semantics: retry only if the "
                "operation is read-only or idempotent; if it may have side "
                "effects, first verify external state or ask the user. Do not "
                "retry blindly."
            )
            error_info = {"name": "ToolOutcomeUnknownError", "code": TOOL_OUTCOME_UNKNOWN}
        else:
            error_text = (
                "The tool call was interrupted before the Harness recorded it "
                "as started. Retry it if it is still needed."
            )
            error_info = {"name": "ToolNotStartedError", "code": TOOL_NOT_STARTED}

        message = ToolResultMessage(
            id=MessageId(f"interrupted-tool-result-{call_id}-{seq}"),
            role="user",
            source={"kind": "tool", "callId": call_id},
            content=[
                ToolResultContentBlock(
                    type="tool-result",
                    toolCallId=call_id,
                    isError=True,
                    content=[TextBlock(type="text", text=error_text)],
                )
            ],
        )

        closer = SessionEvent(
            type="tool/result",
            seq=seq,
            time=time,
            data={
                "turn": open_turn,
                "step": step,
                "message": message,
                "error": error_info,
            },
            surfaceOp="append",
        )
        if started:
            closer.sourceEventSeqs = [call_seq]  # type: ignore[list-item]
        closers.append(closer)
        seq += 1

    # Close an open step next.
    if open_step is not None:
        closers.append(
            SessionEvent(
                type="step/end",
                seq=seq,
                time=time,
                data={"turn": open_turn, "step": open_step},
            )
        )
        seq += 1

    # Close the turn.
    from lca.layer0_infra.dsh_core.session.types import TurnEndInterrupted

    closers.append(
        SessionEvent(
            type="turn/end",
            seq=seq,
            time=time,
            data={"turn": open_turn, "reason": TurnEndInterrupted()},
        )
    )
    return closers
