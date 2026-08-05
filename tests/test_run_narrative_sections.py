"""叙事分节无状态化 —— 并发交错下 span 行不再挂错角色节。"""

from __future__ import annotations

import io
import unittest

from lca.contracts.telemetry import ATTR_AGENT_ROLE, ATTR_MODEL, ATTR_STEP, SpanName
from lca.layer0_infra.observability import SpanView
from lca.layer0_infra.observability.exporters.console import ConsoleNarratorExporter
from lca.layer0_infra.observability.narrative import section_key_for_span


def _span(name: str, *, span_id: str, parent: str | None = None, **attrs: object) -> SpanView:
    return SpanView(
        name=name,
        span_id=span_id,
        trace_id="trace_n",
        parent_span_id=parent,
        attributes=dict(attrs),
        status="ok",
        duration_ms=10,
    )


class TestSectionKeyDerivation(unittest.TestCase):
    def test_llm_chat_with_role_is_self_describing(self) -> None:
        span = _span(
            SpanName.LLM_CHAT.value, span_id="s1", **{ATTR_AGENT_ROLE: "Alice", ATTR_STEP: 0}
        )
        self.assertEqual(section_key_for_span(span), "Alice · step 0")

    def test_phase_span_with_role_and_step(self) -> None:
        span = _span(
            SpanName.LOOP_PHASE_THINK.value,
            span_id="s2",
            **{ATTR_AGENT_ROLE: "Bob", ATTR_STEP: 1},
        )
        self.assertEqual(section_key_for_span(span), "Bob · step 1")

    def test_team_level_spans_group_under_team(self) -> None:
        span = _span(SpanName.TEAM_STRATEGY.value, span_id="s3")
        self.assertEqual(section_key_for_span(span), "team")

    def test_never_returns_none(self) -> None:
        span = _span(SpanName.TOOL_EXECUTE.value, span_id="s4")
        self.assertIsInstance(section_key_for_span(span), str)


class TestConcurrentInterleaving(unittest.TestCase):
    """Alice/Bob 的 span 按完成顺序交错到达，行必须落在各自角色的节里。"""

    def _render(self, spans: list[SpanView]) -> str:
        buf = io.StringIO()
        console = ConsoleNarratorExporter(stream=buf)
        for span in spans:
            console.emit_view(span)
        return buf.getvalue()

    def test_interleaved_llm_spans_land_in_correct_sections(self) -> None:
        # 交错顺序：Bob 的 think 先结束，然后是 Alice 的 llm、Bob 的 llm 交替
        spans = [
            _span(
                SpanName.LOOP_PHASE_THINK.value,
                span_id="b1",
                **{ATTR_AGENT_ROLE: "Bob", ATTR_STEP: 0},
            ),
            _span(
                SpanName.LOOP_PHASE_THINK.value,
                span_id="a1",
                **{ATTR_AGENT_ROLE: "Alice", ATTR_STEP: 0},
            ),
            _span(
                SpanName.LLM_CHAT.value,
                span_id="a2",
                **{ATTR_AGENT_ROLE: "Alice", ATTR_STEP: 0, ATTR_MODEL: "m-alice"},
            ),
            _span(
                SpanName.LLM_CHAT.value,
                span_id="b2",
                **{ATTR_AGENT_ROLE: "Bob", ATTR_STEP: 0, ATTR_MODEL: "m-bob"},
            ),
        ]
        out = self._render(spans)

        sections: dict[str, list[str]] = {}
        current = ""
        for line in out.splitlines():
            if line.startswith("── ") and "digest" not in line:
                current = line.strip("─ ")
                sections[current] = []
            elif current:
                sections[current].append(line)

        alice_block = "\n".join(sections.get("Alice · step 0", []))
        bob_block = "\n".join(sections.get("Bob · step 0", []))
        self.assertIn("m-alice", alice_block)
        self.assertNotIn("m-bob", alice_block)
        self.assertIn("m-bob", bob_block)
        self.assertNotIn("m-alice", bob_block)


if __name__ == "__main__":
    unittest.main()
