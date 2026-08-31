"""Journal 内容字段截断策略（ADR-0055）+ 写入端 sensitivity 强制（评估文档 §49、§67）。"""

from __future__ import annotations

import unittest

from lca.infrastructure.observability.adapters.policy import (
    AttributePolicy,
    Verbosity,
    redact_restricted,
)

from lca.contracts.models.observability.journal import ReasoningDelta, TeamRunFinished
from lca.infrastructure.observability.journal.engine.engine import RunStore


class JournalContentPolicyTests(unittest.TestCase):
    def test_content_field_not_truncated_at_standard_verbosity(self) -> None:
        long_text = "答" * 5000
        store = RunStore(policy=AttributePolicy(Verbosity.STANDARD))
        stamped = store.append(TeamRunFinished(status="completed", steps=1, output_text=long_text))
        event = stamped.event
        assert isinstance(event, TeamRunFinished)
        self.assertEqual(len(event.output_text), 5000)
        self.assertFalse(event.output_truncated)

    def test_content_field_marks_truncation_at_safety_cap(self) -> None:
        long_text = "x" * 60_000
        store = RunStore(policy=AttributePolicy(Verbosity.MINIMAL))
        stamped = store.append(TeamRunFinished(status="completed", steps=1, output_text=long_text))
        event = stamped.event
        assert isinstance(event, TeamRunFinished)
        self.assertLess(len(event.output_text), len(long_text))
        self.assertTrue(event.output_truncated)

    def test_redact_restricted_short_text_passes_through(self) -> None:
        assert redact_restricted("hello") == "hello"

    def test_redact_restricted_truncates_long_text(self) -> None:
        long = "x" * 500
        out = redact_restricted(long)
        assert len(out) < len(long)
        assert "[REDACTED]" in out

    def test_redact_restricted_redacts_secrets(self) -> None:
        credential = "Bearer sk-1234567890abcdefghij"
        out = redact_restricted(credential)
        assert "sk-1234567890abcdefghij" not in out
        assert "[REDACTED]" in out

    def test_confidential_event_text_redacted_at_writer(self) -> None:
        """ReasoningDelta 是 sensitivity=confidential + audience=restricted 的事件。

        写入端必须强制 redact，覆盖 verbosity=verbose 的全文策略。
        """
        reasoning_text = "I think the answer is 42 because " + ("very " * 50) + "true."
        store = RunStore(policy=AttributePolicy(Verbosity.VERBOSE))
        stamped = store.append(ReasoningDelta(step=1, text_delta=reasoning_text))
        event = stamped.event
        assert isinstance(event, ReasoningDelta)
        # 标准 verbosity=VERBOSE 不截断文本；confidential 强制 80-char 截断 + [REDACTED]
        assert len(event.text_delta) <= 200  # 80 prefix + suffix + tag
        assert reasoning_text != event.text_delta
        assert event.text_delta.endswith("[REDACTED]")

    def test_internal_event_unaffected_by_confidential_redaction(self) -> None:
        """non-confidential 事件走标准 verbosity 路径，不被强制 redact。"""
        from lca.contracts.models.observability.journal import InboxFollowupCreated

        text = "a" * 200  # 在 standard 预算内
        store = RunStore(policy=AttributePolicy(Verbosity.STANDARD))
        stamped = store.append(
            InboxFollowupCreated(
                inbox_id="x",
                actor="user",
                target="t",
                priority="p",
                payload_preview=text,
            )
        )
        event = stamped.event
        assert isinstance(event, InboxFollowupCreated)
        assert event.payload_preview == text


if __name__ == "__main__":
    unittest.main()
