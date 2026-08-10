"""SSEJournalProjector + sse_frames 单元测试。"""

from __future__ import annotations

import json
import unittest

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    DelegationIssued,
    RunScope,
    StampedEvent,
    StepTextDelta,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.layer0_infra.observability.journal.sse_frames import (
    frames_after_seq,
    parse_last_event_id,
    stamped_to_sse_frame,
)
from lca.layer0_infra.observability.journal.sse_projector import SSEJournalProjector


class TestSseFrames(unittest.TestCase):
    def test_stamped_to_sse_frame_shape(self) -> None:
        scope = RunScope(trace_id="t1", run_id="r1", agent_role="Lead")
        stamped = StampedEvent(
            seq=7,
            ts=100.0,
            scope=scope,
            event=DelegationIssued(delegation_id="d1", callee_role="Alice", subtask_preview="hi"),
        )
        frame = stamped_to_sse_frame(stamped)
        self.assertIn("id: 7\n", frame)
        self.assertIn("event: DelegationIssued\n", frame)
        self.assertTrue(frame.endswith("\n\n"))
        data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line[6:])
        self.assertEqual(payload["seq"], 7)
        self.assertEqual(payload["event_type"], "DelegationIssued")
        self.assertEqual(payload["domain"], "team")

    def test_parse_last_event_id(self) -> None:
        self.assertEqual(parse_last_event_id(None), 0)
        self.assertEqual(parse_last_event_id("42"), 42)
        self.assertEqual(parse_last_event_id("bad"), 0)

    def test_frames_after_seq(self) -> None:
        scope = RunScope(trace_id="t", run_id="r")
        f1 = stamped_to_sse_frame(
            StampedEvent(seq=1, ts=1.0, scope=scope, event=TeamRunStarted(team_id="x"))
        )
        f2 = stamped_to_sse_frame(
            StampedEvent(seq=2, ts=2.0, scope=scope, event=TeamRunFinished(status="ok"))
        )
        out = frames_after_seq([f1, f2], 1)
        self.assertEqual(len(out), 1)
        self.assertIn("TeamRunFinished", out[0])


class TestSseProjector(unittest.TestCase):
    def test_emit_on_event_and_close(self) -> None:
        received: list[str | None] = []
        projector = SSEJournalProjector(received.append)
        scope = RunScope(trace_id="t", run_id="r")
        projector.on_event(
            StampedEvent(seq=1, ts=1.0, scope=scope, event=TeamRunStarted(team_id="team"))
        )
        projector.close()
        self.assertEqual(len(received), 2)
        self.assertIn("TeamRunStarted", received[0])
        self.assertIsNone(received[1])


class TestSseProjectorStepTextDeltaFilter(unittest.TestCase):
    def test_decision_channel_filtered(self) -> None:
        """decision channel 的 StepTextDelta 不应出现在 SSE 输出中。"""
        received: list[str | None] = []
        projector = SSEJournalProjector(received.append)
        scope = RunScope(trace_id="t", run_id="r")

        # decision channel — 应被过滤
        projector.on_event(
            StampedEvent(
                seq=1,
                ts=1.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="raw token", seq=0, channel=StreamChannel.DECISION.value
                ),
            )
        )
        # answer channel — 应通过
        projector.on_event(
            StampedEvent(
                seq=2,
                ts=2.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="visible text", seq=1, channel=StreamChannel.ANSWER.value
                ),
            )
        )

        # 只有 answer channel 的帧（+ close 的 None）
        non_none = [f for f in received if f is not None]
        self.assertEqual(len(non_none), 1)
        self.assertIn("visible text", non_none[0])
        self.assertNotIn("raw token", non_none[0])

    def test_answer_channel_passes_through(self) -> None:
        """answer channel 的 StepTextDelta 正常通过。"""
        received: list[str | None] = []
        projector = SSEJournalProjector(received.append)
        scope = RunScope(trace_id="t", run_id="r")
        projector.on_event(
            StampedEvent(
                seq=1,
                ts=1.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="hello", seq=0, channel=StreamChannel.ANSWER.value
                ),
            )
        )
        non_none = [f for f in received if f is not None]
        self.assertEqual(len(non_none), 1)
        self.assertIn("hello", non_none[0])


if __name__ == "__main__":
    unittest.main()
