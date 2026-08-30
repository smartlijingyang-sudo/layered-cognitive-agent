"""Tests for ArtifactController + CapabilityArtifact + 4-state machine (PR-8 + acceptance §5.1 V6).

Per acceptance-criteria §5.1 V6 acceptance:

> 跑 1 个完整 agent run
> 取 journal 全量 facts
> **断言每条 fact 携带 plan_ref**
> **断言取任意 plan_ref 可重放该 plan 的 CapabilityPlan + ControlPlan + ScopePlan**

Wait — §5.1 V6 is actually 4-state machine (ArtifactController). Let me re-read.

Acceptance §5.1:
- 4 状态枚举闭合（DRAFT / VERIFIED / ACTIVE / RETIRED）
- 合法迁移覆盖：DRAFT→VERIFIED、VERIFIED→ACTIVE、ACTIVE→RETIRED、VERIFIED→DRAFT（修订）
- 非法迁移抛 InvalidStateTransitionError：PARSED→VERIFIED（旧路径直接进 VERIFIED）、
  DRAFT→ACTIVE（跳过 VERIFIED）、ACTIVE→DRAFT（不可回退）

This test covers:

- ArtifactState enum: 4 members + canonical values
- LEGAL_TRANSITIONS matrix: 4 transitions
- CapabilityArtifact frozen dataclass + make_capability_artifact factory
- migrate_artifact: legal transitions succeed
- migrate_artifact: illegal transitions raise InvalidStateTransitionError
- legal_next_states: from each state, return correct set of targets
- ArtifactController facade methods
- Property test: 100 iterations of state machine traversal (no invalid transitions)
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.artifact_state import (
    LEGAL_TRANSITIONS,
    ArtifactState,
    all_states,
    is_legal_transition,
    parse_artifact_state,
)
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.journal.artifact import (
    ArtifactController,
    CapabilityArtifact,
    InvalidStateTransitionError,
    artifact_with_state,
    capability_artifact_to_dict,
    controller_legal_next_states,
    controller_migrate,
    is_terminal_state,
    legal_next_states,
    make_capability_artifact,
    migrate_artifact,
    migrate_to_active,
    migrate_to_retired,
    migrate_to_verified,
)

# ── ArtifactState enum ──────────────────────────────────────────────


class TestArtifactStateEnum:
    def test_has_exactly_four_members(self) -> None:
        """4 状态 = DRAFT / VERIFIED / ACTIVE / RETIRED (ADR-0074 §三裁剪)。"""
        members = list(ArtifactState)
        assert len(members) == 4

    def test_canonical_values(self) -> None:
        assert ArtifactState.DRAFT.value == "draft"
        assert ArtifactState.VERIFIED.value == "verified"
        assert ArtifactState.ACTIVE.value == "active"
        assert ArtifactState.RETIRED.value == "retired"

    def test_str_enum_value_equality(self) -> None:
        assert ArtifactState.ACTIVE == "active"

    def test_no_duplicate_values(self) -> None:
        values = [s.value for s in ArtifactState]
        assert len(values) == len(set(values))

    def test_all_states_returns_all(self) -> None:
        states = all_states()
        assert len(states) == 4


class TestLegalTransitions:
    def test_legal_transitions_count(self) -> None:
        """4 合法迁移：DRAFT→VERIFIED, VERIFIED→ACTIVE, VERIFIED→DRAFT, ACTIVE→RETIRED。"""
        assert len(LEGAL_TRANSITIONS) == 4

    def test_draft_to_verified_legal(self) -> None:
        assert is_legal_transition(ArtifactState.DRAFT, ArtifactState.VERIFIED)

    def test_verified_to_active_legal(self) -> None:
        assert is_legal_transition(ArtifactState.VERIFIED, ArtifactState.ACTIVE)

    def test_verified_to_draft_revision_legal(self) -> None:
        """VERIFIED → DRAFT 是合法「修订」迁移。"""
        assert is_legal_transition(ArtifactState.VERIFIED, ArtifactState.DRAFT)

    def test_active_to_retired_legal(self) -> None:
        assert is_legal_transition(ArtifactState.ACTIVE, ArtifactState.RETIRED)

    def test_illegal_transitions_rejected(self) -> None:
        """非法迁移：DRAFT→ACTIVE（跳过 VERIFIED）等。"""
        # DRAFT → ACTIVE (跳过 VERIFIED)
        assert not is_legal_transition(ArtifactState.DRAFT, ArtifactState.ACTIVE)
        # DRAFT → RETIRED (跳过 VERIFIED + ACTIVE)
        assert not is_legal_transition(ArtifactState.DRAFT, ArtifactState.RETIRED)
        # ACTIVE → DRAFT (不可回退)
        assert not is_legal_transition(ArtifactState.ACTIVE, ArtifactState.DRAFT)
        # ACTIVE → VERIFIED (不可回退)
        assert not is_legal_transition(ArtifactState.ACTIVE, ArtifactState.VERIFIED)
        # RETIRED → 任何 (terminal，不可逆)
        for target in ArtifactState:
            assert not is_legal_transition(ArtifactState.RETIRED, target)
        # VERIFIED → RETIRED (跳过 ACTIVE)
        assert not is_legal_transition(ArtifactState.VERIFIED, ArtifactState.RETIRED)
        # self-loop
        for state in ArtifactState:
            assert not is_legal_transition(state, state)


class TestParseArtifactState:
    def test_round_trip_string(self) -> None:
        for s in ArtifactState:
            assert parse_artifact_state(s.value) is s

    def test_round_trip_enum(self) -> None:
        for s in ArtifactState:
            assert parse_artifact_state(s) is s

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown artifact state"):
            parse_artifact_state("invalid_state")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_artifact_state(42)


# ── CapabilityArtifact ────────────────────────────────────────────


class TestCapabilityArtifactConstruction:
    def test_minimal_valid(self) -> None:
        art = CapabilityArtifact(
            logical_id="plugin.a",
            revision_digest="abc1234567890def",
            state=ArtifactState.DRAFT,
            scope=Scope.RUN,
        )
        assert art.logical_id == "plugin.a"
        assert art.revision_digest == "abc1234567890def"
        assert art.state is ArtifactState.DRAFT
        assert art.scope is Scope.RUN
        assert art.grants == ()
        assert art.version == 1

    def test_blank_logical_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="logical_id must be non-empty"):
            CapabilityArtifact(
                logical_id="",
                revision_digest="abc",
                state=ArtifactState.DRAFT,
                scope=Scope.RUN,
            )

    def test_blank_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="revision_digest must be non-empty"):
            CapabilityArtifact(
                logical_id="plugin.a",
                revision_digest="",
                state=ArtifactState.DRAFT,
                scope=Scope.RUN,
            )

    def test_str_inputs_normalized(self) -> None:
        art = CapabilityArtifact(
            logical_id="plugin.a",
            revision_digest="abc",
            state="verified",
            scope="run",
        )
        assert art.state is ArtifactState.VERIFIED
        assert art.scope is Scope.RUN


class TestMakeCapabilityArtifact:
    def test_digest_auto_computed(self) -> None:
        art = make_capability_artifact("plugin.a", "content_v1")
        assert art.revision_digest != ""
        # SHA-256 hex 16 char
        assert len(art.revision_digest) == 16
        assert all(c in "0123456789abcdef" for c in art.revision_digest)

    def test_digest_deterministic(self) -> None:
        art1 = make_capability_artifact("plugin.a", "same_content")
        art2 = make_capability_artifact("plugin.b", "same_content")
        assert art1.revision_digest == art2.revision_digest

    def test_digest_changes_with_content(self) -> None:
        art1 = make_capability_artifact("plugin.a", "content_v1")
        art2 = make_capability_artifact("plugin.a", "content_v2")
        assert art1.revision_digest != art2.revision_digest

    def test_bytes_content(self) -> None:
        art = make_capability_artifact("plugin.a", b"binary_content")
        assert len(art.revision_digest) == 16

    def test_with_grants_and_metadata(self) -> None:
        art = make_capability_artifact(
            "plugin.a",
            "content",
            scope=Scope.AGENT,
            state=ArtifactState.ACTIVE,
            grants=("cap.memory", "cap.tools"),
            metadata={"author": "test"},
        )
        assert art.scope is Scope.AGENT
        assert art.state is ArtifactState.ACTIVE
        assert art.grants == ("cap.memory", "cap.tools")
        assert art.metadata == {"author": "test"}


# ── migrate_artifact / InvalidStateTransitionError ─────────────────────


class TestMigrateArtifact:
    def test_legal_migration(self) -> None:
        art = make_capability_artifact("plugin.a", "content")
        assert art.state is ArtifactState.DRAFT
        art_v = migrate_to_verified(art)
        assert art_v.state is ArtifactState.VERIFIED
        # Original is immutable
        assert art.state is ArtifactState.DRAFT

    def test_draft_to_verified(self) -> None:
        art = make_capability_artifact("plugin.a", "content")
        migrated = migrate_artifact(art, ArtifactState.VERIFIED)
        assert migrated.state is ArtifactState.VERIFIED

    def test_verified_to_active(self) -> None:
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.VERIFIED)
        migrated = migrate_to_active(art)
        assert migrated.state is ArtifactState.ACTIVE

    def test_active_to_retired(self) -> None:
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.ACTIVE)
        migrated = migrate_to_retired(art)
        assert migrated.state is ArtifactState.RETIRED

    def test_verified_to_draft_revision(self) -> None:
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.VERIFIED)
        migrated = migrate_artifact(art, ArtifactState.DRAFT)
        assert migrated.state is ArtifactState.DRAFT


class TestInvalidStateTransitionError:
    def test_draft_to_active_skips_verified_raises(self) -> None:
        """DRAFT → ACTIVE（跳过 VERIFIED）必须 raise。"""
        art = make_capability_artifact("plugin.a", "content")
        with pytest.raises(InvalidStateTransitionError, match="illegal state transition"):
            migrate_artifact(art, ArtifactState.ACTIVE)

    def test_active_to_draft_no_rollback_raises(self) -> None:
        """ACTIVE → DRAFT（不可回退）必须 raise。"""
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.ACTIVE)
        with pytest.raises(InvalidStateTransitionError, match="illegal state transition"):
            migrate_artifact(art, ArtifactState.DRAFT)

    def test_retired_terminal_no_transitions_raises(self) -> None:
        """RETIRED 不可逆；任何迁移必须 raise。"""
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.RETIRED)
        for target in ArtifactState:
            with pytest.raises(InvalidStateTransitionError):
                migrate_artifact(art, target)

    def test_invalid_transition_error_message(self) -> None:
        art = make_capability_artifact("plugin.a", "content")
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            migrate_artifact(art, ArtifactState.RETIRED)
        msg = str(exc_info.value)
        assert "plugin.a" in msg
        assert "draft" in msg
        assert "retired" in msg


# ── legal_next_states ────────────────────────────────────────────


class TestLegalNextStates:
    def test_draft_legal_next_states(self) -> None:
        art = make_capability_artifact("plugin.a", "content")
        next_states = legal_next_states(art)
        assert ArtifactState.VERIFIED in next_states
        assert len(next_states) == 1

    def test_verified_legal_next_states(self) -> None:
        """VERIFIED 有 2 个合法目标：ACTIVE + DRAFT（修订）。"""
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.VERIFIED)
        next_states = legal_next_states(art)
        assert ArtifactState.ACTIVE in next_states
        assert ArtifactState.DRAFT in next_states
        assert len(next_states) == 2

    def test_active_legal_next_states(self) -> None:
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.ACTIVE)
        next_states = legal_next_states(art)
        assert next_states == (ArtifactState.RETIRED,)

    def test_retired_legal_next_states_empty(self) -> None:
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.RETIRED)
        next_states = legal_next_states(art)
        assert next_states == ()

    def test_is_terminal_state(self) -> None:
        retired = make_capability_artifact("p", "c", state=ArtifactState.RETIRED)
        active = make_capability_artifact("p", "c", state=ArtifactState.ACTIVE)
        assert is_terminal_state(retired) is True
        assert is_terminal_state(active) is False


# ── artifact_with_state / capability_artifact_to_dict ──────────────


class TestArtifactAccessors:
    def test_artifact_with_state(self) -> None:
        art = make_capability_artifact("plugin.a", "content")
        new_art = artifact_with_state(art, ArtifactState.VERIFIED)
        assert new_art.state is ArtifactState.VERIFIED
        # Original is unchanged (frozen)
        assert art.state is ArtifactState.DRAFT

    def test_to_dict_round_trip(self) -> None:
        art = make_capability_artifact(
            "plugin.a",
            "content",
            scope=Scope.AGENT,
            state=ArtifactState.ACTIVE,
            grants=("cap.memory",),
            metadata={"k": "v"},
        )
        d = capability_artifact_to_dict(art)
        assert d["logical_id"] == "plugin.a"
        assert d["state"] == "active"
        assert d["scope"] == "agent"
        assert d["grants"] == ["cap.memory"]
        assert d["metadata"] == {"k": "v"}


# ── ArtifactController facade ─────────────────────────────────────


class TestArtifactControllerFacade:
    def test_controller_migrate_legal(self) -> None:
        controller = ArtifactController(name="test")
        art = make_capability_artifact("plugin.a", "content")
        migrated = controller_migrate(controller, art, ArtifactState.VERIFIED)
        assert migrated.state is ArtifactState.VERIFIED

    def test_controller_migrate_illegal_raises(self) -> None:
        controller = ArtifactController(name="test")
        art = make_capability_artifact("plugin.a", "content")
        with pytest.raises(InvalidStateTransitionError):
            controller_migrate(controller, art, ArtifactState.RETIRED)

    def test_controller_legal_next_states(self) -> None:
        controller = ArtifactController()
        art = make_capability_artifact("plugin.a", "content", state=ArtifactState.VERIFIED)
        next_states = controller_legal_next_states(controller, art)
        assert ArtifactState.ACTIVE in next_states
        assert ArtifactState.DRAFT in next_states


# ── Property test: state machine traversal ────────────────────────


class TestStateMachineProperty100:
    """V6 acceptance property test: 100 次合法路径遍历全部成功。"""

    def test_100_iterations_random_legal_paths(self) -> None:
        """模拟 100 次合法路径遍历，每步都应成功，最终达到 RETIRED。"""
        import random

        random.seed(42)
        controller = ArtifactController()

        for _ in range(100):
            # Start from DRAFT
            art = make_capability_artifact(f"plugin.{random.randint(1, 10000)}", "content")  # noqa: S311
            assert art.state is ArtifactState.DRAFT

            # Walk legal path: DRAFT → VERIFIED → ACTIVE → RETIRED
            # (skipping DRAFT↔VERIFIED revision path for determinism)
            art = controller_migrate(controller, art, ArtifactState.VERIFIED)
            art = controller_migrate(controller, art, ArtifactState.ACTIVE)
            art = controller_migrate(controller, art, ArtifactState.RETIRED)
            assert art.state is ArtifactState.RETIRED

    def test_100_iterations_with_revision_path(self) -> None:
        """随机合法路径（包含修订 oscillation）— 上限保护。"""
        import random

        random.seed(42)
        controller = ArtifactController()

        # Take 100 random walks but cap at 20 steps
        successful_retired = 0
        for _ in range(100):
            art = make_capability_artifact(f"plugin.{random.randint(1, 10000)}", "content")  # noqa: S311
            steps = 0
            max_steps = 20
            while not is_terminal_state(art) and steps < max_steps:
                next_states = controller_legal_next_states(controller, art)
                if not next_states:
                    break
                # Heuristic: prefer progress to ACTIVE/RETIRED (avoid oscillation)
                if (
                    ArtifactState.RETIRED in next_states and random.random() < 0.5  # noqa: S311
                ):
                    target = ArtifactState.RETIRED
                elif (
                    ArtifactState.ACTIVE in next_states and random.random() < 0.7  # noqa: S311
                ):
                    target = ArtifactState.ACTIVE
                else:
                    target = random.choice(next_states)  # noqa: S311
                art = controller_migrate(controller, art, target)
                steps += 1
            if is_terminal_state(art):
                successful_retired += 1

        # Most walks should reach RETIRED
        assert successful_retired >= 50, (
            f"Only {successful_retired}/100 walks reached RETIRED; expected ≥50"
        )

    def test_property_no_illegal_transitions_accepted(self) -> None:
        """从每个 state 出发，遍历所有 target；非法必须 raise。"""
        controller = ArtifactController()
        for source in ArtifactState:
            for target in ArtifactState:
                art = make_capability_artifact("p", "c", state=source)
                if is_legal_transition(source, target):
                    # Should succeed
                    migrated = controller_migrate(controller, art, target)
                    assert migrated.state is target
                else:
                    # Should raise
                    with pytest.raises(InvalidStateTransitionError):
                        controller_migrate(controller, art, target)
