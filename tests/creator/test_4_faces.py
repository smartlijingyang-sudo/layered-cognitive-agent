"""Tests for Creator 4 faces (ADR-0074 §三 + PR-9 + acceptance §5.2 V7).

Per acceptance-criteria §5.2 V7:

> 跑 1 次完整 agent run
> 取 journal 全量 facts
> **断言每条 fact 携带 plan_ref**
> **断言取任意 plan_ref 可重放该 plan 的 CapabilityPlan + ControlPlan + ScopePlan**

Wait — §5.2 V7 is actually 4 Creator faces (V7 acceptance). Re-read:

Acceptance §5.2:
- 4 状态枚举闭合 (DRAFT / VERIFIED / ACTIVE / RETIRED)
- 合法迁移覆盖 + 非法迁移抛 InvalidStateTransition

That's §5.1 (V6 acceptance for ArtifactController).

Acceptance §5.2:
- lca-ops creator --help 输出 4 subcommand (inspect / author / validate / promote)
- Creator action vocabulary is closed to those four faces

This test covers:

- CreatorFace enum: 4 members
- PromoteSpec dataclass + flags
- 4 face implementations: inspect / author / validate / promote
- dispatch_creator_face accepts only the four declared faces
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.plugins.creator.faces import (
    CreatorFace,
    CreatorResult,
    PromoteSpec,
    all_creator_faces,
    parse_creator_face,
)
from lca.plugins.creator.faces.implementations import (
    dispatch_creator_face,
    do_author,
    do_inspect,
    do_promote,
    do_validate,
)

# ── CreatorFace enum ──────────────────────────────────────────────


class TestCreatorFaceEnum:
    def test_has_exactly_four_members(self) -> None:
        """4 Creator faces (ADR-0074 §三 + V7 acceptance)."""
        members = list(CreatorFace)
        assert len(members) == 4

    def test_canonical_values(self) -> None:
        assert CreatorFace.INSPECT.value == "inspect"
        assert CreatorFace.AUTHOR.value == "author"
        assert CreatorFace.VALIDATE.value == "validate"
        assert CreatorFace.PROMOTE.value == "promote"

    def test_str_enum_value_equality(self) -> None:
        assert CreatorFace.PROMOTE == "promote"

    def test_all_creator_faces_returns_all(self) -> None:
        faces = all_creator_faces()
        assert len(faces) == 4


class TestParseCreatorFace:
    def test_round_trip_string(self) -> None:
        for f in CreatorFace:
            assert parse_creator_face(f.value) is f

    def test_round_trip_enum(self) -> None:
        for f in CreatorFace:
            assert parse_creator_face(f) is f

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown creator face"):
            parse_creator_face("stage")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_creator_face(42)


# ── PromoteSpec ────────────────────────────────────────────────────


class TestPromoteSpec:
    def test_default_values(self) -> None:
        spec = PromoteSpec()
        assert spec.target_scope is None
        assert spec.rollback is False
        assert spec.preset_id is None

    def test_with_values(self) -> None:
        spec = PromoteSpec(
            target_scope="release",
            rollback=True,
            preset_id="my-preset",
        )
        assert spec.target_scope == "release"
        assert spec.rollback is True
        assert spec.preset_id == "my-preset"


# ── 4 face implementations ───────────────────────────────────────


class TestInspectFace:
    def test_returns_inspect_face(self) -> None:
        result = do_inspect()
        assert result.face is CreatorFace.INSPECT
        assert isinstance(result, CreatorResult)

    def test_inspect_with_target(self) -> None:
        result = do_inspect(target="plugin.x")
        assert result.payload["target"] == "plugin.x"

    def test_inspect_state_does_not_change(self) -> None:
        """inspect 是 read-only; state_after 保持 DRAFT（默认值；不修改 state）。"""
        result = do_inspect()
        assert result.state_after is ArtifactState.DRAFT


class TestAuthorFace:
    def test_returns_author_face(self) -> None:
        result = do_author(name="plugin.x")
        assert result.face is CreatorFace.AUTHOR
        assert result.state_after is ArtifactState.DRAFT

    def test_author_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name is required"):
            do_author(name="")

    def test_author_with_path(self) -> None:
        result = do_author(
            name="plugin.x",
            path="/tmp/example.py",  # noqa: S108
        )
        assert result.payload["path"] == "/tmp/example.py"  # noqa: S108

    def test_author_with_content(self) -> None:
        result = do_author(name="plugin.x", content="def setup(): pass")
        assert result.payload["has_content"] is True


class TestValidateFace:
    def test_returns_validate_face(self) -> None:
        result = do_validate(name="plugin.x")
        assert result.face is CreatorFace.VALIDATE
        assert result.state_after is ArtifactState.VERIFIED

    def test_validate_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name is required"):
            do_validate(name="")

    def test_validate_verdict(self) -> None:
        result = do_validate(name="plugin.x")
        assert result.payload["verdict"] == "ok"
        assert "descriptor_complete" in result.payload["checks_passed"]
        assert "signature_valid" in result.payload["checks_passed"]
        assert "dependencies_resolvable" in result.payload["checks_passed"]


class TestPromoteFace:
    def test_default_promote_active(self) -> None:
        """默认 promote → ACTIVE 状态。"""
        result = do_promote(name="plugin.x")
        assert result.face is CreatorFace.PROMOTE
        assert result.state_after is ArtifactState.ACTIVE

    def test_rollback_promote_retired(self) -> None:
        """rollback=True projects ACTIVE → RETIRED."""
        result = do_promote(name="plugin.x", spec=PromoteSpec(rollback=True))
        assert result.state_after is ArtifactState.RETIRED
        assert result.payload["operation"] == "rollback"

    def test_experiment_promote(self) -> None:
        """A promotion may target the experiment scope."""
        result = do_promote(name="plugin.x", spec=PromoteSpec(target_scope="experiment"))
        assert result.state_after is ArtifactState.ACTIVE
        assert result.payload["target_scope"] == "experiment"

    def test_release_promote_with_preset(self) -> None:
        """A release promotion may name its preset."""
        result = do_promote(
            name="plugin.x",
            spec=PromoteSpec(target_scope="release", preset_id="my-preset"),
        )
        assert result.state_after is ArtifactState.ACTIVE
        assert result.payload["target_scope"] == "release"
        assert result.payload["preset_id"] == "my-preset"

    def test_promote_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name is required"):
            do_promote(name="")


# ── Unified dispatch ─────────────────────────────────────────────


class TestDispatchCreatorFace:
    def test_dispatch_inspect(self) -> None:
        result = dispatch_creator_face(CreatorFace.INSPECT, target="plugin.x")
        assert result.face is CreatorFace.INSPECT

    def test_dispatch_author(self) -> None:
        result = dispatch_creator_face(CreatorFace.AUTHOR, name="plugin.x")
        assert result.face is CreatorFace.AUTHOR

    def test_dispatch_validate(self) -> None:
        result = dispatch_creator_face(CreatorFace.VALIDATE, name="plugin.x")
        assert result.face is CreatorFace.VALIDATE

    def test_dispatch_promote(self) -> None:
        result = dispatch_creator_face(CreatorFace.PROMOTE, name="plugin.x")
        assert result.face is CreatorFace.PROMOTE

    def test_dispatch_with_string(self) -> None:
        """字符串 face 也接受（CLI 调用便利）。"""
        result = dispatch_creator_face("inspect", target="plugin.x")
        assert result.face is CreatorFace.INSPECT

    def test_dispatch_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError):
            dispatch_creator_face("unknown_face")


class TestCreatorVocabularyClosure:
    @pytest.mark.parametrize("old_action", ("mount", "unmount", "stage", "retire", "publish"))
    def test_old_action_is_not_a_creator_face(self, old_action: str) -> None:
        with pytest.raises(ValueError, match="unknown creator face"):
            dispatch_creator_face(old_action)
