"""run_command timeout normalization tests."""

from __future__ import annotations

import unittest

from lca.infrastructure.tools.lca_computer.executor import (
    _resolve_timeout_s as _resolve_command_timeout_s,
)


class TestRunCommandTimeout(unittest.TestCase):
    def test_seconds_when_small_value(self) -> None:
        self.assertEqual(_resolve_command_timeout_s({"timeout": 60}), 60)

    def test_milliseconds_when_large_value(self) -> None:
        self.assertEqual(_resolve_command_timeout_s({"timeout": 60000}), 60)

    def test_timeout_s_explicit(self) -> None:
        self.assertEqual(_resolve_command_timeout_s({"timeout_s": 45}), 45)

    def test_default_when_missing(self) -> None:
        self.assertEqual(_resolve_command_timeout_s({}), 60)


if __name__ == "__main__":
    unittest.main()
