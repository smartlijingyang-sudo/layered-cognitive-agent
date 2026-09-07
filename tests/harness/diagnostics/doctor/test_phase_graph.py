"""Behavioral tests for the PhaseGraphDoctor pass (PR-0199-P2-06).

Per ADR-0199 §5 + C1 the cognitive phase graph is a closed set of 6 phases
(perceive, think, act, reflect, remember, stop). These tests assert:
every emitted code matches DOC-PG-NNN, the closed-set is the SSOT, and
the pass is deterministic (C8) + read-only (I-HPC-7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    CognitivePhaseGraphPlan,
    PhaseNode,
)
from lca.harness.diagnostics.doctor import (
    _CLOSED_PHASES,
    PhaseGraphDoctor,
)

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── helpers ───────────


@dataclass(frozen=True)
class _StubPhaseNode:
    """A node stub whose semantic_phase is a plain string.

    Used to exercise the doctor against phase names outside the
    ``SemanticPhase`` enum (e.g. ``"fantasize"``). The real
    ``PhaseNode.__post_init__`` rejects unknown phase values, so
    building a stub is the only way to drive the closed-set check
    with non-canonical phase names. The stub's ``name`` attribute is
    the canonical phase label so ``_collect_nodes`` returns the
    short form (e.g. ``"fantasize"``) used in DOC-PG-001 messages.
    """

    semantic_phase: str
    id: str = ""
    name: str = ""

    def __post_init__(self) -> None:
        # Default `name` to the phase string when not supplied.
        if not self.name:
            object.__setattr__(self, "name", self.semantic_phase)


def _make_node(phase_name: str, *, node_id: str | None = None) -> PhaseNode:
    """Build a real PhaseNode for a *canonical* phase (e.g. 'perceive')."""
    return PhaseNode(
        id=node_id or f"{phase_name}.main",
        semantic_phase=SemanticPhase(phase_name),
        binding=f"phase.{phase_name}.standard",
        max_visits=1,
    )


def _make_plan(phases: list[str]) -> CognitivePhaseGraphPlan:
    """Build a CognitivePhaseGraphPlan whose nodes map 1:1 to phase names.

    Unknown phase names (outside ``SemanticPhase``) are routed through
    :class:`_StubPhaseNode` because ``PhaseNode.__post_init__`` would
    otherwise reject them. The doctor only reads ``semantic_phase.value``
    or ``.name`` / ``.id``, so the stub is faithful for closed-set testing.
    """
    canonical = {p.value for p in SemanticPhase}
    nodes_list = []
    for p in phases:
        if p in canonical:
            nodes_list.append(_make_node(p))
        else:
            nodes_list.append(_StubPhaseNode(semantic_phase=p, id=f"{p}.main"))
    nodes = tuple(nodes_list)
    entry = f"{phases[0]}.main" if phases else ""
    return CognitivePhaseGraphPlan(entry=entry, nodes=nodes, edges=())


# ─────────── closed-set tests ───────────


class TestClosedPhasesConstant:
    """The closed-set IS the SSOT — adding a 7th phase requires an ADR (C1)."""

    def test_closed_phases_constant_is_complete(self) -> None:
        assert len(_CLOSED_PHASES) == 6

    def test_closed_phases_contains_canonical_names(self) -> None:
        canonical = {"perceive", "think", "act", "reflect", "remember", "stop"}
        assert set(_CLOSED_PHASES) == canonical

    def test_closed_phases_is_frozenset(self) -> None:
        # Frozen — cannot be mutated by a plugin or downstream doctor.
        assert isinstance(_CLOSED_PHASES, frozenset)


# ─────────── happy path ───────────


class TestCleanGraph:
    """All 6 phases present exactly once → no findings."""

    def test_clean_graph_no_findings(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "think", "act", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        assert report.summary.errors == 0
        assert report.summary.warnings == 0
        assert report.summary.total == 0

    def test_no_cycle_for_legal_linear_sequence(self) -> None:
        plan = _make_plan(["perceive", "think", "act", "reflect", "remember", "stop"])
        cycle = PhaseGraphDoctor._detect_cycle(PhaseGraphDoctor._collect_nodes(plan))
        assert cycle is None


# ─────────── DOC-PG-001 (unknown phases) ───────────


class TestUnknownPhase:
    """Phases outside the closed set must surface as DOC-PG-001."""

    def test_unknown_phase_emits_doc_pg_001(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "fantasize", "act", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        codes = [f.code for f in report.findings]
        assert "DOC-PG-001" in codes
        assert report.summary.errors >= 1

    def test_each_unknown_phase_emits_separate_finding(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "fantasize", "act", "dream", "remember", "stop"])
        report = doctor.run(plan)
        pg001 = [f for f in report.findings if f.code == "DOC-PG-001"]
        # Both 'fantasize' and 'dream' should yield DOC-PG-001 findings.
        unknown_in_messages = {
            f.message for f in pg001 if "fantasize" in f.message or "dream" in f.message
        }
        assert len(pg001) == 2
        assert len(unknown_in_messages) == 2

    def test_remediation_mentions_adr_0199_c1(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "fantasize", "act", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        pg001 = [f for f in report.findings if f.code == "DOC-PG-001"]
        assert pg001, "expected at least one DOC-PG-001 finding"
        assert all("ADR-0199 C1" in f.remediation for f in pg001)


# ─────────── DOC-PG-002 (duplicates) ───────────


class TestDuplicatePhase:
    """Phases appearing more than once must surface as DOC-PG-002."""

    def test_duplicate_phase_emits_doc_pg_002(self) -> None:
        doctor = PhaseGraphDoctor()
        # 'think' appears twice — closed-set requires exactly once.
        plan = _make_plan(["perceive", "think", "think", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        codes = [f.code for f in report.findings]
        assert "DOC-PG-002" in codes

    def test_duplicate_count_in_message(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "think", "think", "think", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        pg002 = [f for f in report.findings if f.code == "DOC-PG-002"]
        assert any("3 times" in f.message for f in pg002)


# ─────────── DOC-PG-003 (cycles) ───────────


class TestCycle:
    """Repeated phase names in the linear sequence indicate a cycle."""

    def test_cycle_emits_doc_pg_003(self) -> None:
        doctor = PhaseGraphDoctor()
        # 'perceive' repeats after 'think' → cycle.
        plan = _make_plan(["perceive", "think", "perceive"])
        report = doctor.run(plan)
        codes = [f.code for f in report.findings]
        assert "DOC-PG-003" in codes

    def test_cycle_message_includes_path(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "think", "perceive"])
        report = doctor.run(plan)
        pg003 = [f for f in report.findings if f.code == "DOC-PG-003"]
        assert pg003, "expected at least one DOC-PG-003 finding"
        msg = pg003[0].message
        assert "perceive" in msg
        assert "think" in msg
        assert " -> " in msg  # explicit path separator


# ─────────── severity & code conformance ───────────


class TestCodeConformance:
    """Stable machine codes — every emitted code matches DOC-XX-NNN."""

    def test_finding_severity_is_error(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "fantasize", "act", "reflect", "remember", "stop"])
        report = doctor.run(plan)
        assert all(f.severity == "error" for f in report.findings)
        assert all(f.owner == "ADR-0199" for f in report.findings)

    def test_finding_code_regex_compliance(self) -> None:
        doctor = PhaseGraphDoctor()
        plans = [
            _make_plan(["perceive", "fantasize", "act", "reflect", "remember", "stop"]),
            _make_plan(["perceive", "think", "think", "reflect", "remember", "stop"]),
            _make_plan(["perceive", "think", "perceive"]),
        ]
        for plan in plans:
            report = doctor.run(plan)
            for finding in report.findings:
                assert _CODE_RE.match(finding.code), (
                    f"code {finding.code!r} does not match DOC-<DOMAIN>-<NNN>"
                )
                assert finding.severity in ("error", "warning", "info")
                assert finding.message
                assert finding.remediation


# ─────────── determinism ───────────


class TestDeterminism:
    """C8 — same input must produce the same report."""

    def test_findings_are_deterministic(self) -> None:
        doctor = PhaseGraphDoctor()
        plan = _make_plan(["perceive", "fantasize", "act", "dream", "remember", "stop"])
        a = doctor.run(plan)
        b = doctor.run(plan)
        assert a.to_jsonable() == b.to_jsonable()


# ─────────── _collect_nodes helpers ───────────


class TestCollectNodes:
    """_collect_nodes must tolerate alternate plan shapes (C6)."""

    def test_collect_nodes_handles_dataclass_nodes(self) -> None:
        plan = _make_plan(["perceive", "think", "act", "reflect", "remember", "stop"])
        names = PhaseGraphDoctor._collect_nodes(plan)
        assert names == ["perceive", "think", "act", "reflect", "remember", "stop"]

    def test_collect_nodes_handles_missing_attribute(self) -> None:
        @dataclass(frozen=True)
        class _EmptyPlan:
            # No `nodes` and no `phases`.
            entry: str = ""

        names = PhaseGraphDoctor._collect_nodes(_EmptyPlan())
        assert names == []

    def test_collect_nodes_handles_alternate_phases_attribute(self) -> None:
        @dataclass(frozen=True)
        class _PhasesPlan:
            phases: tuple[str, ...] = ("perceive", "think", "stop")

        names = PhaseGraphDoctor._collect_nodes(_PhasesPlan())
        assert names == ["perceive", "think", "stop"]


# ─────────── subject / profile_path ───────────


class TestSubject:
    """Subject on the DoctorReport must reflect profile_path when given."""

    def test_profile_path_used_as_subject_when_provided(self) -> None:
        doctor = PhaseGraphDoctor(profile_path="profiles/sample.yaml")
        report = doctor.run(_make_plan(["perceive", "think", "act", "reflect", "remember", "stop"]))
        assert report.subject == "profiles/sample.yaml"

    def test_default_subject_when_no_profile_path(self) -> None:
        doctor = PhaseGraphDoctor()
        report = doctor.run(_make_plan(["perceive", "think", "act", "reflect", "remember", "stop"]))
        assert report.subject == "phase_graph"


# ─────────── multiple violations ───────────


class TestMultipleViolations:
    """A plan with all 3 violation classes emits findings for each."""

    def test_all_three_codes_emitted_for_combined_violation(self) -> None:
        doctor = PhaseGraphDoctor()
        # 'fantasize' (unknown) + 'think' (duplicate) + 'perceive' repeated (cycle)
        plan = _make_plan(["perceive", "fantasize", "think", "think", "act", "reflect", "perceive"])
        report = doctor.run(plan)
        codes = {f.code for f in report.findings}
        assert "DOC-PG-001" in codes
        assert "DOC-PG-002" in codes
        assert "DOC-PG-003" in codes


# ─────────── re-exports ───────────


class TestBarrelExports:
    """The doctor barrel must expose PhaseGraphDoctor + _CLOSED_PHASES."""

    def test_barrel_exports_phase_graph_doctor(self) -> None:
        from lca.harness.diagnostics.doctor import PhaseGraphDoctor as Exported

        assert Exported is PhaseGraphDoctor

    def test_barrel_exports_closed_phases(self) -> None:
        from lca.harness.diagnostics.doctor import _CLOSED_PHASES as _CLOSED_PHASES_BARREL

        assert _CLOSED_PHASES_BARREL is _CLOSED_PHASES
