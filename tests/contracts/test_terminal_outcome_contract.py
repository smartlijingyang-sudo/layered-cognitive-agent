"""ADR-0077 TerminalOutcome contract tests.

Each invariant from ADR-0077 §决策一 / §决策四 must hold at construction time:
- Per-kind required ``*_ref``
- OutputRef discriminated union round-trip
- plan_ref / journal_seq_end invariants for replay
- Discriminator stable across frozen equality
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.terminal_outcome import (
    ArtifactRef,
    ErrorRef,
    ResumeCursor,
    StreamRef,
    StructuredRef,
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)


def _completed() -> TerminalOutcome:
    return TerminalOutcome(
        kind=TerminalOutcomeKind.COMPLETED,
        stop_reason="task_done",
        final_output_ref=TextRef(text="hello", seq=42, cursor="c-1"),
        plan_ref="plan-abc",
        journal_seq_end=100,
    )


class TestClosedSetOfKinds:
    """TerminalOutcomeKind is a closed set (宪法 C6); no string fallback."""

    def test_exactly_five_kinds(self) -> None:
        assert {k.value for k in TerminalOutcomeKind} == {
            "completed",
            "failed",
            "canceled",
            "waiting_input",
            "degraded",
        }

    def test_kind_values_are_strings(self) -> None:
        for k in TerminalOutcomeKind:
            assert isinstance(k.value, str)


class TestCompletedRequiresFinalOutputRef:
    def test_completed_with_final_output_ref_succeeds(self) -> None:
        outcome = _completed()
        assert outcome.kind is TerminalOutcomeKind.COMPLETED
        assert outcome.final_output_ref is not None

    def test_completed_without_final_output_ref_fails_closed(self) -> None:
        with pytest.raises(ValueError, match=r"COMPLETED.*requires final_output_ref"):
            TerminalOutcome(
                kind=TerminalOutcomeKind.COMPLETED,
                stop_reason="task_done",
                plan_ref="plan-abc",
                journal_seq_end=1,
            )


class TestFailedRequiresErrorRef:
    def test_failed_with_error_ref_succeeds(self) -> None:
        outcome = TerminalOutcome(
            kind=TerminalOutcomeKind.FAILED,
            stop_reason="crash",
            error_ref=ErrorRef(kind="crash", message="boom", source_ref="journal:7"),
            plan_ref="plan-abc",
            journal_seq_end=7,
        )
        assert outcome.kind is TerminalOutcomeKind.FAILED
        assert outcome.error_ref is not None

    def test_failed_without_error_ref_fails_closed(self) -> None:
        with pytest.raises(ValueError, match=r"FAILED.*requires error_ref"):
            TerminalOutcome(
                kind=TerminalOutcomeKind.FAILED,
                stop_reason="crash",
                plan_ref="plan-abc",
                journal_seq_end=7,
            )


class TestWaitingInputRequiresResumeCursor:
    def test_waiting_input_with_cursor_succeeds(self) -> None:
        outcome = TerminalOutcome(
            kind=TerminalOutcomeKind.WAITING_INPUT,
            stop_reason="approval_required",
            resume_cursor=ResumeCursor(cursor="cursor-1", session_seq=3, approval_id="ap-9"),
            plan_ref="plan-abc",
            journal_seq_end=12,
        )
        assert outcome.kind is TerminalOutcomeKind.WAITING_INPUT
        assert outcome.resume_cursor is not None

    def test_waiting_input_without_cursor_fails_closed(self) -> None:
        with pytest.raises(ValueError, match=r"WAITING_INPUT.*requires resume_cursor"):
            TerminalOutcome(
                kind=TerminalOutcomeKind.WAITING_INPUT,
                stop_reason="approval_required",
                plan_ref="plan-abc",
                journal_seq_end=12,
            )


class TestCanceledAndDegradedRequireAtLeastOneRef:
    @pytest.mark.parametrize(
        "kind",
        [TerminalOutcomeKind.CANCELED, TerminalOutcomeKind.DEGRADED],
    )
    def test_no_ref_fails_closed(self, kind: TerminalOutcomeKind) -> None:
        with pytest.raises(
            ValueError, match=f"{kind.value}.*requires final_output_ref or error_ref"
        ):
            TerminalOutcome(
                kind=kind,
                stop_reason="x",
                plan_ref="plan-abc",
                journal_seq_end=1,
            )

    @pytest.mark.parametrize(
        "kind",
        [TerminalOutcomeKind.CANCELED, TerminalOutcomeKind.DEGRADED],
    )
    def test_final_output_ref_satisfies(self, kind: TerminalOutcomeKind) -> None:
        outcome = TerminalOutcome(
            kind=kind,
            stop_reason="x",
            final_output_ref=TextRef(text="partial", seq=1),
            plan_ref="plan-abc",
            journal_seq_end=1,
        )
        assert outcome.final_output_ref is not None

    @pytest.mark.parametrize(
        "kind",
        [TerminalOutcomeKind.CANCELED, TerminalOutcomeKind.DEGRADED],
    )
    def test_error_ref_satisfies(self, kind: TerminalOutcomeKind) -> None:
        outcome = TerminalOutcome(
            kind=kind,
            stop_reason="x",
            error_ref=ErrorRef(kind="cancel", message="user"),
            plan_ref="plan-abc",
            journal_seq_end=1,
        )
        assert outcome.error_ref is not None


class TestReplayInvariants:
    def test_empty_plan_ref_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="plan_ref must be non-empty"):
            TerminalOutcome(
                kind=TerminalOutcomeKind.COMPLETED,
                stop_reason="x",
                final_output_ref=TextRef(text="ok"),
                plan_ref="",
                journal_seq_end=1,
            )

    def test_negative_journal_seq_end_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="journal_seq_end must be non-negative"):
            TerminalOutcome(
                kind=TerminalOutcomeKind.COMPLETED,
                stop_reason="x",
                final_output_ref=TextRef(text="ok"),
                plan_ref="plan-abc",
                journal_seq_end=-1,
            )


class TestOutputRefDiscriminator:
    """ADR-0077 §决策四: each ref type must be distinguishable by type/isinstance."""

    def test_each_ref_type_carries_distinct_payload(self) -> None:
        text = TextRef(text="hi", seq=1)
        artifact = ArtifactRef(artifact_id="a1", plan_ref="plan-abc", artifact_kind="file")
        structured = StructuredRef(schema_id="json", value_ref="v1")
        stream = StreamRef(first_seq=1, last_seq=10, model="m1")

        assert isinstance(text, TextRef)
        assert isinstance(artifact, ArtifactRef)
        assert isinstance(structured, StructuredRef)
        assert isinstance(stream, StreamRef)

    def test_discriminator_via_isinstance_round_trip(self) -> None:
        refs = [
            TextRef(text="t"),
            ArtifactRef(artifact_id="a"),
            StructuredRef(schema_id="s"),
            StreamRef(first_seq=0, last_seq=1),
        ]
        kinds_seen = set()
        for ref in refs:
            if isinstance(ref, TextRef):
                kinds_seen.add("text")
            elif isinstance(ref, ArtifactRef):
                kinds_seen.add("artifact")
            elif isinstance(ref, StructuredRef):
                kinds_seen.add("structured")
            elif isinstance(ref, StreamRef):
                kinds_seen.add("stream")
        assert kinds_seen == {"text", "artifact", "structured", "stream"}

    def test_outcome_output_ref_kind_method(self) -> None:
        outcome = _completed()
        assert outcome.output_ref_kind() == "text"

    def test_outcome_output_ref_kind_when_none(self) -> None:
        outcome = TerminalOutcome(
            kind=TerminalOutcomeKind.FAILED,
            stop_reason="x",
            error_ref=ErrorRef(kind="crash"),
            plan_ref="plan-abc",
            journal_seq_end=1,
        )
        assert outcome.output_ref_kind() == ""


class TestArtifactRefsCollection:
    """artifact_refs 是 tuple[ArtifactRef, ...]，可空（仅 final_output_ref 必填）。"""

    def test_empty_artifact_refs_allowed(self) -> None:
        outcome = _completed()
        assert outcome.artifact_refs == ()

    def test_multiple_artifact_refs_preserved(self) -> None:
        refs = (
            ArtifactRef(artifact_id="a1", plan_ref="p", artifact_kind="file"),
            ArtifactRef(artifact_id="a2", plan_ref="p", artifact_kind="image"),
        )
        outcome = TerminalOutcome(
            kind=TerminalOutcomeKind.COMPLETED,
            stop_reason="x",
            final_output_ref=TextRef(text="done"),
            artifact_refs=refs,
            plan_ref="plan-abc",
            journal_seq_end=5,
        )
        assert len(outcome.artifact_refs) == 2
        assert outcome.artifact_refs[0].artifact_id == "a1"


class TestFrozenAndHashable:
    """All TerminalOutcome / ref types must be frozen & hashable for use in sets/dicts."""

    def test_terminal_outcome_is_frozen(self) -> None:
        outcome = _completed()
        with pytest.raises(AttributeError):
            outcome.kind = TerminalOutcomeKind.FAILED  # type: ignore[misc]

    def test_terminal_outcome_is_hashable(self) -> None:
        outcome = _completed()
        in_set = {outcome}
        assert outcome in in_set

    def test_ref_types_are_hashable(self) -> None:
        text = TextRef(text="hi", seq=1)
        artifact = ArtifactRef(artifact_id="a", plan_ref="p", artifact_kind="file")
        structured = StructuredRef(schema_id="s", value_ref="v")
        stream = StreamRef(first_seq=0, last_seq=1, model="m1")
        assert {text, artifact, structured, stream} == {
            text,
            artifact,
            structured,
            stream,
        }


class TestADRBackwardCompatibilityNote:
    """ADR-0077 说 StopDecision.final_output 字段应被 TerminalOutcome 取代。

    本测试仅证明 TerminalOutcome 自身能独立构造即可；不触及 StopDecision
    与 AgentState 改造（属于后续 PR）。本 class 仅为显式锁定当前步 1
    范围，防止后续 PR 误吞本步。
    """

    def test_terminal_outcome_isolated_from_stop_decision(self) -> None:
        from lca.contracts.models.core.stop import StopDecision

        decision = StopDecision(should_stop=True, final_output="legacy")
        outcome = _completed()
        assert decision is not outcome
        assert outcome.kind is TerminalOutcomeKind.COMPLETED


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"cursor": "", "approval_id": "approval-1"}, "resume cursor must be a non-empty string"),
        (
            {"cursor": "cursor-1", "approval_id": ""},
            "resume approval_id must be a non-empty string",
        ),
        (
            {"cursor": "cursor-1", "approval_id": "approval-1", "session_seq": "3"},
            "resume session_seq must be an integer",
        ),
        (
            {"cursor": "cursor-1", "approval_id": "approval-1", "session_seq": -1},
            "resume session_seq must be non-negative",
        ),
    ],
)
def test_resume_cursor_rejects_non_durable_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ResumeCursor(**kwargs)  # type: ignore[arg-type]
