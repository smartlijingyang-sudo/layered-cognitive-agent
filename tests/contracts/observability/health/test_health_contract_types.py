"""Contract tests for ``RunHealthReport`` typed health contract (PR-1 / Task 1.1).

Upholds AGENTS.md §3 C13 (information bloodline closure): every cross-boundary
reference and every typed health DTO must be ``frozen=True, extra="forbid"``.
Upholds AGENTS.md §3 C8 (determinism): ``RunHealthReport`` must be hashable and
``conditions`` must be a ``tuple`` (not ``list``) so identical spines produce
identical reports.

The docstring obligations tested here (open ``type``, closed ``status``,
stable ``reason`` identifier) come from design spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§10.3 — the contract is the fold function, not the type vocabulary.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.health import (
    EvidenceRef,
    RunHealthCondition,
    RunHealthReport,
    RunHealthSummary,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        run_id="run_abc",
        spine_path="/tmp/spines/run_abc.spine.jsonl",
        event_id="run_abc:7",
        execution_point="perceive.phase.fold.end",
        seq=7,
    )


def _summary(
    *,
    ok: int = 1,
    degraded: int = 0,
    failed: int = 0,
    unknown: int = 0,
    by_type: dict[str, str] | None = None,
) -> RunHealthSummary:
    if by_type is None:
        by_type = {"perceive": "ok"}
    return RunHealthSummary(
        conditions_ok=ok,
        conditions_degraded=degraded,
        conditions_failed=failed,
        conditions_unknown=unknown,
        by_type=by_type,
    )


def _condition(
    *,
    type_: str = "perceive",
    status: str = "ok",
    reason: str = "phase_closed",
    evidence: tuple[EvidenceRef, ...] | None = None,
) -> RunHealthCondition:
    return RunHealthCondition(
        type=type_,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        evidence_refs=evidence if evidence is not None else (_evidence(),),
        observed_at=1700000000.0,
    )


def _report(
    *,
    conditions: tuple[RunHealthCondition, ...] | None = None,
) -> RunHealthReport:
    if conditions is None:
        conditions = (_condition(),)
    return RunHealthReport(
        schema_version="1.0",
        run_id="run_abc",
        generated_at=1700000000.0,
        conditions=conditions,
        summary=_summary(),
    )


# ---------------------------------------------------------------------------
# Contract: extra="forbid"
# ---------------------------------------------------------------------------


def test_evidence_ref_is_frozen() -> None:
    """``EvidenceRef`` rejects unknown kwargs (``extra='forbid'``)."""
    ref = _evidence()
    with pytest.raises(ValidationError):
        EvidenceRef(
            run_id=ref.run_id,
            spine_path=ref.spine_path,
            event_id=ref.event_id,
            execution_point=ref.execution_point,
            seq=ref.seq,
            extra_field="boom",
        )
    # frozen: no in-place mutation.
    with pytest.raises(ValidationError):
        ref.run_id = "run_other"  # type: ignore[misc]


def test_condition_rejects_extra_fields() -> None:
    """``RunHealthCondition`` rejects unknown kwargs (``extra='forbid'``)."""
    cond = _condition()
    with pytest.raises(ValidationError):
        RunHealthCondition(
            type=cond.type,
            status=cond.status,
            reason=cond.reason,
            evidence_refs=cond.evidence_refs,
            observed_at=cond.observed_at,
            made_up_field="nope",
        )


def test_summary_rejects_extra_fields() -> None:
    """``RunHealthSummary`` rejects unknown kwargs (``extra='forbid'``)."""
    with pytest.raises(ValidationError):
        RunHealthSummary(
            conditions_ok=1,
            conditions_degraded=0,
            conditions_failed=0,
            conditions_unknown=0,
            by_type={"perceive": "ok"},
            rogue_field="nope",
        )


def test_report_rejects_extra_fields() -> None:
    """``RunHealthReport`` rejects unknown kwargs (``extra='forbid'``)."""
    with pytest.raises(ValidationError):
        RunHealthReport(
            schema_version="1.0",
            run_id="run_abc",
            generated_at=1700000000.0,
            conditions=(_condition(),),
            summary=_summary(),
            rogue_field="nope",
        )


# ---------------------------------------------------------------------------
# Contract: hashable + tuple conditions (C8 determinism)
# ---------------------------------------------------------------------------


def test_report_is_hashable() -> None:
    """``RunHealthReport`` must hash identically for identical inputs.

    Exercises both ``__hash__`` directly AND use as a ``set`` member /
    ``dict`` key — the test does not pass on ``__hash__ is not None``
    because Pydantic v2 always defines ``__hash__`` even for unfrozen
    models; the actual hash contract is that two reports built from the
    same inputs produce the same hash and compare equal.
    """
    a = _report()
    b = _report()
    assert a == b
    assert hash(a) == hash(b)

    # Real exercise: deduplication and key lookup.
    dedup: set[RunHealthReport] = {a, b}
    assert len(dedup) == 1

    table: dict[RunHealthReport, str] = {a: "first"}
    assert table[b] == "first"

    # Mutating one field produces a different hash and inequality.
    other = _report(conditions=(_condition(status="failed", reason="orphan"),))
    assert other != a
    assert hash(other) != hash(a)


def test_conditions_is_tuple_not_list() -> None:
    """``conditions`` MUST be ``tuple`` — load-bearing for hashability & C8.

    A ``list`` would (a) break ``RunHealthReport.__hash__`` and (b) violate
    determinism because ``list`` equality is order-sensitive but mutable.
    """
    report = _report()
    assert isinstance(report.conditions, tuple)
    # ``list`` would be mutable; ``tuple`` is not.
    with pytest.raises((TypeError, ValidationError)):
        report.conditions.append(_condition(reason="extra"))  # type: ignore[attr-defined]


def test_evidence_refs_is_tuple_not_list() -> None:
    """``RunHealthCondition.evidence_refs`` MUST also be ``tuple``."""
    cond = _condition()
    assert isinstance(cond.evidence_refs, tuple)


# ---------------------------------------------------------------------------
# Contract: status closed alphabet + open type (spec §10.3)
# ---------------------------------------------------------------------------


def test_status_literal_4_values() -> None:
    """``status`` is the closed 4-value alphabet; anything else is rejected."""
    for good in ("ok", "degraded", "failed", "unknown"):
        cond = _condition(status=good)
        assert cond.status == good

    with pytest.raises(ValidationError):
        _condition(status="green")  # not in alphabet
    with pytest.raises(ValidationError):
        _condition(status="OK")  # case-sensitive


def test_type_is_open_string() -> None:
    """``type`` is intentionally an open string (k8s Conditions / OTel pattern).

    A new type like ``"experimental"`` is accepted without a contract change.
    """
    cond = _condition(type_="experimental")
    assert cond.type == "experimental"


def test_reason_is_str_no_parse_contract() -> None:
    """``reason`` is a stable identifier (k8s pattern), NOT a human message.

    The docstring contract requires that ``reason`` is a plain ``str`` whose
    value is meant for stable matching (``"tool_orphan_dropped"``,
    ``"sandbox_enter_unmatched"``) — agents MUST NOT parse it. This test
    pins the type and asserts the docstring states the identifier semantic.
    """
    cond = _condition(reason="tool_orphan_dropped")
    assert isinstance(cond.reason, str)
    assert cond.reason == "tool_orphan_dropped"
    # Docstring must declare the stable-identifier contract.
    assert "stable identifier" in RunHealthCondition.__doc__.lower()
    # And explicitly forbid parsing.
    assert "must not parse" in RunHealthCondition.__doc__.lower()


# ---------------------------------------------------------------------------
# Contract: by_type dict shape (spec §3 PR-1 contract code)
# ---------------------------------------------------------------------------


def test_summary_by_type_dict_str_to_status() -> None:
    """``by_type`` keys are condition ``type`` strings; values are status."""
    summary = _summary(
        ok=2,
        degraded=1,
        failed=0,
        unknown=0,
        by_type={"perceive": "ok", "think": "degraded"},
    )
    assert all(isinstance(k, str) for k in summary.by_type)
    assert set(summary.by_type.values()) <= {"ok", "degraded", "failed", "unknown"}
    # Mismatched value type is rejected.
    with pytest.raises(ValidationError):
        RunHealthSummary(
            conditions_ok=0,
            conditions_degraded=0,
            conditions_failed=0,
            conditions_unknown=0,
            by_type={"perceive": "green"},  # not in the 4-value alphabet
        )


# ---------------------------------------------------------------------------
# Contract: schema_version pinning
# ---------------------------------------------------------------------------


def test_report_schema_version_is_1_0() -> None:
    """``schema_version`` is the closed literal ``"1.0"``."""
    assert _report().schema_version == "1.0"
    with pytest.raises(ValidationError):
        RunHealthReport(
            schema_version="2.0",
            run_id="run_abc",
            generated_at=1700000000.0,
            conditions=(_condition(),),
            summary=_summary(),
        )


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_re_exports_all_four_models() -> None:
    """``lca.contracts.observability.health`` re-exports the 4 Pydantic models."""
    import lca.contracts.observability.health as health_mod

    assert health_mod.EvidenceRef is EvidenceRef
    assert health_mod.RunHealthCondition is RunHealthCondition
    assert health_mod.RunHealthSummary is RunHealthSummary
    assert health_mod.RunHealthReport is RunHealthReport