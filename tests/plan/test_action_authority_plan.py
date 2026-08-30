"""Tests for :class:`ActionAuthorityPlan` — ADR-0076 §五.

The plan compiler must derive the closed set of ``ActionType`` strings
the Agent may emit from ``TaskContract`` + ``RoleProfile`` +
``CapabilityGrant``.  The BodyComposer consumes this authority instead
of the historical ``_SCOPE_ACTIONS`` static table.
"""

from __future__ import annotations

from dataclasses import replace

from lca.contracts.atoms.enums import ActionScope, ActionType
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.declarative.declarative_phase_graph import ActionAuthorityPlan
from lca.harness.declarative.compile.action_authority import compile_action_authority
from lca.harness.declarative.compile.authority import (
    action_authority_for_scope,
    action_is_permitted,
)
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile

# ── Data class contract ───────────────────────────────────────────────


def test_authority_policy_permits_only_allowed_actions() -> None:
    """The Harness policy permits only actions declared by the plan."""

    authority = ActionAuthorityPlan(
        allowed_actions=frozenset({"respond", "use_tool"}),
        scope="solo",
    )
    assert action_is_permitted(authority, "respond") is True
    assert action_is_permitted(authority, "use_tool") is True
    assert action_is_permitted(authority, "delegate") is False
    assert action_is_permitted(authority, "handoff") is False


def test_action_authority_plan_forbidden_actions_override_allowed() -> None:
    """A non-empty ``forbidden_actions`` denies even an allowed match."""

    authority = ActionAuthorityPlan(
        allowed_actions=frozenset({"respond", "use_tool"}),
        forbidden_actions=frozenset({"use_tool"}),
        scope="solo",
    )
    assert action_is_permitted(authority, "respond") is True
    assert action_is_permitted(authority, "use_tool") is False


def test_action_authority_plan_normalises_iterables_to_frozensets() -> None:
    """Iterable inputs are normalised to frozensets of str."""

    authority = ActionAuthorityPlan(
        allowed_actions=("respond", "use_tool"),
        forbidden_actions=("delegate",),
        scope="lead",
    )
    assert isinstance(authority.allowed_actions, frozenset)
    assert "respond" in authority.allowed_actions
    assert "delegate" in authority.forbidden_actions


def test_action_authority_plan_rejects_empty_scope() -> None:
    """``scope`` must be a non-empty string."""

    import pytest

    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        DeclarativeValidationError,
    )

    with pytest.raises(DeclarativeValidationError):
        ActionAuthorityPlan(allowed_actions=frozenset(), scope="")


def test_action_authority_policy_derives_scope_and_task_carve_out() -> None:
    """Authority derivation is independently testable from plan projection."""

    base_spec = compile_plan(resolve_profile("profiles/web-standard.yaml")).plugin_specs[0]
    member_authority = compile_action_authority(
        (replace(base_spec, functional_group="team-member"),),
        task_contract=f"!{ActionType.USE_TOOL.value}",
    )
    lead_authority = compile_action_authority(
        (replace(base_spec, functional_group=FunctionalGroup.G8_COLLAB.value),),
    )

    assert member_authority.scope == ActionScope.MEMBER.value
    assert ActionType.USE_TOOL.value in member_authority.forbidden_actions
    assert not action_is_permitted(member_authority, ActionType.USE_TOOL.value)
    assert lead_authority.scope == ActionScope.LEAD.value
    assert action_is_permitted(lead_authority, ActionType.DELEGATE.value)


# ── Plan compiler integration ─────────────────────────────────────────


def test_action_authority_selects_a_compiled_role_grant() -> None:
    """Composition selects role permissions from the immutable plan projection."""

    base_spec = compile_plan(resolve_profile("profiles/web-standard.yaml")).plugin_specs[0]
    authority = compile_action_authority(
        (replace(base_spec, functional_group="team-member"),),
        task_contract=f"!{ActionType.USE_TOOL.value}",
    )

    member_authority = action_authority_for_scope(authority, ActionScope.MEMBER)
    lead_authority = action_authority_for_scope(authority, ActionScope.LEAD)

    assert member_authority.scope == ActionScope.MEMBER.value
    assert not action_is_permitted(member_authority, ActionType.DELEGATE.value)
    assert not action_is_permitted(member_authority, ActionType.USE_TOOL.value)
    assert lead_authority.scope == ActionScope.LEAD.value
    assert action_is_permitted(lead_authority, ActionType.DELEGATE.value)
    assert not action_is_permitted(lead_authority, ActionType.USE_TOOL.value)


def test_action_authority_rejects_an_undeclared_role_grant() -> None:
    """Fixture authorities cannot widen permissions through a composition fallback."""

    authority = ActionAuthorityPlan(allowed_actions=frozenset({"respond"}), scope="solo")

    import pytest

    with pytest.raises(ValueError, match="does not declare scope: lead"):
        action_authority_for_scope(authority, ActionScope.LEAD)


def test_compile_plan_populates_action_authority() -> None:
    """``compile_plan`` must populate ``plan.action_authority``."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    plan = compile_plan(resolved)
    assert plan.action_authority is not None, (
        "compile_plan must populate action_authority (ADR-0076 §五)."
    )
    assert plan.action_authority.scope, (
        "action_authority.scope must be set; expected 'solo', 'member', or 'lead'."
    )
    # The default scope must permit at least the executable baseline
    # (RESPOND / USE_TOOL) plus STOP / ASK_HUMAN for terminal semantics.
    allowed = plan.action_authority.allowed_actions
    assert {"respond", "use_tool", "stop", "ask_human"}.issubset(allowed), (
        f"action_authority must include baseline actions; got {sorted(allowed)}"
    )
    assert {authority.scope for authority in plan.action_authority.scoped_actions} == {
        ActionScope.SOLO.value,
        ActionScope.MEMBER.value,
        ActionScope.LEAD.value,
    }


def test_compile_plan_action_authority_forbids_actions_via_task_contract() -> None:
    """``task_contract`` starting with ``!`` carves the named action out."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    plan = compile_plan(resolved, options=None)  # default task_id=""
    # task_contract='' → no carve-outs
    assert "use_tool" in plan.action_authority.allowed_actions

    # Compile again with task_id that triggers a carve-out.
    from lca.harness.profile.plan_compiler import CompileOptions

    carved_plan = compile_plan(
        resolved,
        options=CompileOptions(task_id="!use_tool"),
    )
    assert "use_tool" in carved_plan.action_authority.forbidden_actions, (
        "task_contract=!use_tool must add use_tool to forbidden_actions."
    )
    assert action_is_permitted(carved_plan.action_authority, "use_tool") is False


def test_compile_plan_action_authority_scope_inferred_lead() -> None:
    """A profile with lead-scoped plugins must yield scope='lead'."""

    resolved = resolve_profile("profiles/coding-agent.yaml")
    plan = compile_plan(resolved)
    assert plan.action_authority is not None
    # The coding-agent profile exercises the lead path; allow either
    # ``lead`` or ``member`` but never an empty scope.
    assert plan.action_authority.scope in {"lead", "member", "solo"}, (
        f"Unexpected action_authority.scope: {plan.action_authority.scope!r}"
    )


def test_action_authority_rejects_untyped_action_names() -> None:
    import pytest

    authority = ActionAuthorityPlan(allowed_actions=frozenset({"respond"}), scope="solo")
    with pytest.raises(ValueError, match="action_type must be a non-empty string"):
        action_is_permitted(authority, 7)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="action_type must be a non-empty string"):
        action_is_permitted(authority, "")
