"""Journal 内容字段截断策略（BE-2）。"""

from __future__ import annotations

import unittest

from lca.contracts.models.observability.journal import TeamRunFinished
from lca.layer0_infra.observability.journal.engine import ExecutionJournal
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity


class JournalContentPolicyTests(unittest.TestCase):
    def test_content_field_not_truncated_at_standard_verbosity(self) -> None:
        long_text = "答" * 5000
        journal = ExecutionJournal(policy=AttributePolicy(Verbosity.STANDARD))
        stamped = journal.record(
            TeamRunFinished(status="completed", steps=1, output_text=long_text)
        )
        event = stamped.event
        assert isinstance(event, TeamRunFinished)
        self.assertEqual(len(event.output_text), 5000)
        self.assertFalse(event.output_truncated)

    def test_content_field_marks_truncation_at_safety_cap(self) -> None:
        long_text = "x" * 60_000
        journal = ExecutionJournal(policy=AttributePolicy(Verbosity.MINIMAL))
        stamped = journal.record(
            TeamRunFinished(status="completed", steps=1, output_text=long_text)
        )
        event = stamped.event
        assert isinstance(event, TeamRunFinished)
        self.assertLess(len(event.output_text), len(long_text))
        self.assertTrue(event.output_truncated)


if __name__ == "__main__":
    unittest.main()
