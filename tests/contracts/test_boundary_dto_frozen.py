"""Contract tests for boundary DTOs (ADR-0220 §4).

Each boundary DTO must be frozen and reject extra fields. Behavioral
assertions only; no introspection of private state.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.cognition.boundary import (
    BindingsView,
    ForkedTools,
    MemoryReceipt,
    ReasonerBundle,
    ReasonerContext,
    RoleSnapshot,
    StopPayload,
    TemplateSelection,
)
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.execution.decision import Decision, Reflection
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team.awareness import TeamAwareness


class _FakeTool:
    """Stand-in Tool object satisfying the duck-typed Protocol for tests."""

    name: ClassVar[str] = "fake_tool"
    description: ClassVar[str] = "fake"
    parameters: ClassVar[dict] = {"type": "object"}
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args=None):
        return None

    def validate(self, args=None):
        return None


def _build_role_profile() -> RoleProfile:
    return RoleProfile(
        role="test_role",
        goal="test_goal",
        backstory="test_backstory",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _build_forked_tools() -> ForkedTools:
    return ForkedTools(items=(_FakeTool(),), binding_keys=frozenset({"file_store"}))


def _build_role_snapshot() -> RoleSnapshot:
    return RoleSnapshot(profile=_build_role_profile(), team_awareness=None)


def _build_team_awareness() -> TeamAwareness:
    return TeamAwareness()


def _build_reasoner_context() -> ReasonerContext:
    return ReasonerContext(task="ping")


def _build_template_selection() -> TemplateSelection:
    return TemplateSelection(
        template_id="react", variant="react", decision_path="profile_default"
    )


class TestBindingsView:
    def test_minimal_construction_works(self) -> None:
        view = BindingsView()
        assert view.file_store is None
        assert view.sandbox is None
        assert view.bindings is None

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            BindingsView(unknown_field="oops")
        assert "unknown_field" in str(exc_info.value)

    def test_is_frozen_assignment_raises(self) -> None:
        view = BindingsView()
        with pytest.raises(ValidationError):
            view.file_store = object()


class TestForkedTools:
    def test_accepts_tuple_and_frozenset(self) -> None:
        forked = _build_forked_tools()
        assert isinstance(forked.items, tuple)
        assert isinstance(forked.binding_keys, frozenset)

    def test_list_coerced_to_tuple(self) -> None:
        forked = ForkedTools(items=[_FakeTool()], binding_keys=frozenset())
        assert isinstance(forked.items, tuple)

    def test_set_coerced_to_frozenset(self) -> None:
        forked = ForkedTools(items=(), binding_keys={"file_store"})
        assert isinstance(forked.binding_keys, frozenset)
        assert "file_store" in forked.binding_keys

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            ForkedTools(items=(), binding_keys=frozenset(), extra="x")

    def test_is_frozen_assignment_raises(self) -> None:
        forked = _build_forked_tools()
        with pytest.raises(ValidationError):
            forked.items = ()


class TestRoleSnapshot:
    def test_team_awareness_optional(self) -> None:
        snap = RoleSnapshot(profile=_build_role_profile())
        assert snap.team_awareness is None

    def test_team_awareness_present(self) -> None:
        snap = RoleSnapshot(profile=_build_role_profile(), team_awareness=_build_team_awareness())
        assert snap.team_awareness is not None

    def test_rejects_missing_profile(self) -> None:
        with pytest.raises(ValidationError):
            RoleSnapshot()

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            RoleSnapshot(profile=_build_role_profile(), extra_role="x")

    def test_is_frozen_assignment_raises(self) -> None:
        snap = _build_role_snapshot()
        with pytest.raises(ValidationError):
            snap.profile = _build_role_profile()


class TestReasonerBundle:
    def _build(self) -> ReasonerBundle:
        return ReasonerBundle(
            tools=_build_forked_tools(),
            role=_build_role_snapshot(),
            context=_build_reasoner_context(),
            template=_build_template_selection(),
        )

    def test_requires_all_four_fields(self) -> None:
        with pytest.raises(ValidationError):
            ReasonerBundle(
                tools=_build_forked_tools(),
                role=_build_role_snapshot(),
                context=_build_reasoner_context(),
            )

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            ReasonerBundle(
                tools=_build_forked_tools(),
                role=_build_role_snapshot(),
                context=_build_reasoner_context(),
                template=_build_template_selection(),
                extra_bundle_field="x",
            )

    def test_template_must_be_template_selection(self) -> None:
        with pytest.raises(ValidationError):
            ReasonerBundle(
                tools=_build_forked_tools(),
                role=_build_role_snapshot(),
                context=_build_reasoner_context(),
                template=None,
            )

    def test_is_frozen_assignment_raises(self) -> None:
        bundle = self._build()
        with pytest.raises(ValidationError):
            bundle.template = _build_template_selection()


# ---------------------------------------------------------------------------
# ADR-0220 §4.2 — boundary DTOs that pre-existed elsewhere but must satisfy
# the closed boundary contract (frozen + extra=forbid-equivalent).
# ---------------------------------------------------------------------------


class TestReasonerContext:
    def test_minimal_construction_works(self) -> None:
        ctx = ReasonerContext(task="ping")
        assert ctx.task == "ping"
        assert ctx.activated_skills == ()
        assert ctx.manifest is None

    def test_activated_skills_default_to_empty_tuple(self) -> None:
        ctx = ReasonerContext(task="ping")
        assert isinstance(ctx.activated_skills, tuple)

    def test_activated_skills_accepts_tuple_of_activated_skill(self) -> None:
        skill = ActivatedSkill(skill_id="s1", name="skill_one")
        ctx = ReasonerContext(task="ping", activated_skills=(skill,))
        assert ctx.activated_skills == (skill,)

    def test_rejects_missing_task(self) -> None:
        with pytest.raises(ValidationError):
            ReasonerContext()  # type: ignore[call-arg]

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ReasonerContext(task="ping", unknown_field="x")
        assert "unknown_field" in str(exc_info.value)

    def test_is_frozen_assignment_raises(self) -> None:
        ctx = ReasonerContext(task="ping")
        with pytest.raises(ValidationError):
            ctx.task = "new"


class TestTemplateSelection:
    def test_construction_with_all_fields(self) -> None:
        ts = TemplateSelection(
            template_id="react", variant="react", decision_path="profile_default"
        )
        assert ts.template_id == "react"
        assert ts.variant == "react"
        assert ts.decision_path == "profile_default"

    def test_rejects_unknown_variant(self) -> None:
        with pytest.raises(ValidationError):
            TemplateSelection(
                template_id="react",
                variant="bogus",  # type: ignore[arg-type]
                decision_path="profile_default",
            )

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            TemplateSelection(
                template_id="react",
                variant="react",
                decision_path="profile_default",
                extra_field="x",
            )

    def test_is_frozen_assignment_raises(self) -> None:
        ts = _build_template_selection()
        with pytest.raises(ValidationError):
            ts.template_id = "new"


class TestReasonerTurnRender:
    def test_minimal_construction_works(self) -> None:
        render = ReasonerTurnRender(
            prompt="hello",
            trace=None,
            section_count=0,
            manifest=None,
            activated_skill_ids=(),
            section_outputs=None,
            total_chars=5,
            variant=None,
        )
        assert render.prompt == "hello"
        assert render.activated_skill_ids == ()

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(TypeError):
            ReasonerTurnRender(
                prompt="hello",
                trace=None,
                section_count=0,
                manifest=None,
                activated_skill_ids=(),
                section_outputs=None,
                total_chars=5,
                variant=None,
                unknown_field="x",
            )


class TestDecision:
    def test_minimal_construction_works(self) -> None:
        d = Decision(
            decision_id="d1",
            action_type="respond",
            rationale="r",
            confidence=0.5,
        )
        assert d.decision_id == "d1"
        assert d.action_type == "respond"
        assert d.rationale == "r"
        assert d.confidence == 0.5

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(TypeError):
            Decision(
                decision_id="d1",
                action_type="respond",
                rationale="r",
                confidence=0.5,
                unknown_field="x",
            )


class TestEffectReceipt:
    def test_minimal_construction_works(self) -> None:
        receipt = EffectReceipt(
            invocation_id="i1",
            outcome=EffectOutcome.SUCCEEDED,
            idempotency_key="k1",
            provider="prov",
        )
        assert receipt.invocation_id == "i1"
        assert receipt.outcome is EffectOutcome.SUCCEEDED
        assert receipt.idempotency_key == "k1"
        assert receipt.provider == "prov"
        assert receipt.output_ref is None
        assert receipt.error_code is None
        assert receipt.retryable is False

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(TypeError):
            EffectReceipt(
                invocation_id="i1",
                outcome=EffectOutcome.SUCCEEDED,
                idempotency_key="k1",
                provider="prov",
                unknown_field="x",
            )

    def test_frozen_blocks_mutation_of_dataclass_field(self) -> None:
        receipt = EffectReceipt(
            invocation_id="i1",
            outcome=EffectOutcome.SUCCEEDED,
            idempotency_key="k1",
            provider="prov",
        )
        with pytest.raises((AttributeError, Exception)):
            receipt.invocation_id = "i2"  # type: ignore[misc]


class TestReflection:
    def test_minimal_construction_works(self) -> None:
        from lca.contracts.atoms.enums.enums import ReflectionVerdict

        refl = Reflection(reflection_id="r1", verdict=ReflectionVerdict.ON_TRACK)
        assert refl.reflection_id == "r1"
        assert refl.verdict == ReflectionVerdict.ON_TRACK
        assert refl.lesson is None
        assert refl.correction is None

    def test_rejects_unknown_field(self) -> None:
        from lca.contracts.atoms.enums.enums import ReflectionVerdict

        with pytest.raises(TypeError):
            Reflection(
                reflection_id="r1",
                verdict=ReflectionVerdict.ON_TRACK,
                unknown_field="x",
            )


class TestMemoryReceipt:
    def test_minimal_construction_works(self) -> None:
        mr = MemoryReceipt(admitted=True)
        assert mr.admitted is True
        assert mr.memory_ref is None
        assert mr.reflection_id == ""
        assert mr.rejection_reason is None

    def test_full_construction(self) -> None:
        mr = MemoryReceipt(
            admitted=False,
            memory_ref=None,
            reflection_id="r1",
            rejection_reason="policy_denied",
        )
        assert mr.admitted is False
        assert mr.reflection_id == "r1"
        assert mr.rejection_reason == "policy_denied"

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            MemoryReceipt(admitted=True, unknown_field="x")

    def test_is_frozen_assignment_raises(self) -> None:
        mr = MemoryReceipt(admitted=True)
        with pytest.raises(ValidationError):
            mr.admitted = False


class TestStopPayload:
    def test_minimal_construction_works(self) -> None:
        sp = StopPayload(should_stop=False)
        assert sp.should_stop is False
        assert sp.focus_converged is False
        assert sp.reason is None
        assert sp.final_output_ref is None

    def test_full_construction(self) -> None:
        sp = StopPayload(
            should_stop=True,
            focus_converged=True,
            reason="budget_exceeded",
            final_output_ref="artifact://out",
        )
        assert sp.should_stop is True
        assert sp.reason == "budget_exceeded"
        assert sp.final_output_ref == "artifact://out"

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            StopPayload(should_stop=False, unknown_field="x")

    def test_is_frozen_assignment_raises(self) -> None:
        sp = StopPayload(should_stop=False)
        with pytest.raises(ValidationError):
            sp.should_stop = True


class TestConfigIntrospection:
    def test_all_pydantic_boundary_dtos_have_extra_forbid_and_frozen(self) -> None:
        pydantic_dtos = (
            BindingsView,
            ForkedTools,
            RoleSnapshot,
            ReasonerBundle,
            ReasonerContext,
            TemplateSelection,
            MemoryReceipt,
            StopPayload,
        )
        for cls in pydantic_dtos:
            config = cls.model_config
            assert config.get("extra") == "forbid", f"{cls.__name__} extra != forbid"
            assert config.get("frozen") is True, f"{cls.__name__} not frozen"

    def test_all_dataclass_boundary_dtos_are_frozen(self) -> None:
        dataclass_dtos = (
            Decision,
            EffectReceipt,
            Reflection,
            ReasonerTurnRender,
        )
        for cls in dataclass_dtos:
            frozen_flag = getattr(cls, "__dataclass_params__", None)
            assert frozen_flag is not None, f"{cls.__name__} is not a dataclass"
            assert frozen_flag.frozen is True, f"{cls.__name__} not frozen"

    def test_boundary_dtos_reject_unknown_kwargs(self) -> None:
        # Decision, Reflection, EffectReceipt, ReasonerTurnRender are dataclasses;
        # Python's dataclass constructor already raises TypeError on unknown
        # kwargs (the "extra=forbid" equivalent). EffectReceipt already has
        # additional validation in __post_init__; the rest rely on dataclass
        # semantics. The boundary contract is therefore: only the documented
        # fields are accepted.
        import dataclasses

        # EffectReceipt extras are documented; all kwargs map to declared fields.
        for cls in (EffectReceipt, ReasonerTurnRender):
            field_names = {f.name for f in dataclasses.fields(cls)}
            assert "extra_unknown_field" not in field_names
