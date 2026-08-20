"""Tests for the v3 diagnostic patterns (spec §24.5).

Spec-mandated test file (``tests/test_diagnose_patterns.py``).  The
behaviour lives in ``tests/test_v3_diagnose_patterns.py``; we re-export
its classes here so pytest discovers them under both names — that way
the spec requirement is satisfied without duplicating test bodies.
"""

from __future__ import annotations

from tests.test_v3_diagnose_patterns import (
    TestDiagnoseApprovalRejected,
    TestDiagnoseLoopStuck,
    TestDiagnoseMemoryPoisoned,
    TestDiagnoseModelNotSeen,
)

__all__ = [
    "TestDiagnoseApprovalRejected",
    "TestDiagnoseLoopStuck",
    "TestDiagnoseMemoryPoisoned",
    "TestDiagnoseModelNotSeen",
]
