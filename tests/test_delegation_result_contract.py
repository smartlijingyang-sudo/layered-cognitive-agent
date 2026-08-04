"""DelegationResult 契约与幂等查询语义。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from lca.contracts.delegation import DelegationResult, find_result
from lca.contracts.team_awareness import TeamAwareness


def _result(
    role: str = "Alice", subtask: str = "s1", *, success: bool = True, output: str = "ok"
) -> DelegationResult:
    return DelegationResult(
        result_id="dres_1",
        target_role=role,
        subtask=subtask,
        output=output if success else None,
        success=success,
        error=None if success else "boom",
        task_id="task_1",
        step=0,
        returned_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )


class TestFindResult(unittest.TestCase):
    def test_exact_match_success_hits(self) -> None:
        hit = find_result([_result()], target_role="Alice", subtask="s1")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.output, "ok")

    def test_subtask_mismatch_misses(self) -> None:
        self.assertIsNone(find_result([_result()], target_role="Alice", subtask="other"))

    def test_role_mismatch_misses(self) -> None:
        self.assertIsNone(find_result([_result()], target_role="Bob", subtask="s1"))

    def test_failed_result_misses(self) -> None:
        self.assertIsNone(find_result([_result(success=False)], target_role="Alice", subtask="s1"))

    def test_empty_ledger_misses(self) -> None:
        self.assertIsNone(find_result([], target_role="Alice", subtask="s1"))

    def test_first_success_wins(self) -> None:
        failed = _result(success=False)
        ok = _result(output="second")
        hit = find_result([failed, ok], target_role="Alice", subtask="s1")
        assert hit is not None
        self.assertEqual(hit.output, "second")


class TestAwarenessLedgerSurface(unittest.TestCase):
    def test_results_field_exists_on_awareness(self) -> None:
        self.assertIn("results", set(TeamAwareness.__dataclass_fields__))

    def test_fresh_awareness_has_empty_ledger(self) -> None:
        self.assertEqual(TeamAwareness().results, [])

    def test_result_is_immutable(self) -> None:
        from dataclasses import FrozenInstanceError

        with self.assertRaises(FrozenInstanceError):
            _result().target_role = "Bob"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
