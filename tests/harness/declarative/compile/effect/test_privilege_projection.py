"""Behavioral tests for ``lca.harness.declarative.compile.effect.privilege_projection``.

ADR-0199 §3.1 + I-HPC-5 + P3-06: ``PluginContract.privileges`` is the
fourth orthogonal contract dimension. P3-06 projects it into
``EffectPolicyPlan.privileges`` so the Body path can enforce undeclared
privileges fail-closed at setup. The projector is a pure-data
normalisation seam: union + sorted-dedup (deterministic, C8).

These tests assert:
  - The wrapper does not mutate the input plan (frozen dataclass).
  - The result is sorted + deduped (C8).
  - Pre-existing ``privileges`` are preserved (union semantics).
  - ``build_effect_policy_with_privileges`` combines
    ``compile_effect_policy`` + projection.
  - Backward-compat: ``EffectPolicyPlan()`` still constructs without
    ``privileges=``.
"""

import dataclasses
import inspect
from typing import get_type_hints

import pytest

from lca.contracts.harness.composition.plugin_contract import (
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    EffectPolicyPlan,
)
from lca.harness.declarative.compile.effect.policy import compile_effect_policy
from lca.harness.declarative.compile.effect.privilege_projection import (
    build_effect_policy_with_privileges,
    project_privileges_into_effect_policy,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _contract(privileges: tuple[str, ...] = ()) -> PluginContract:
    """Minimal PluginContract carrying only privileges (other sections default)."""
    return PluginContract(
        identity=PluginIdentity(id=f"test.plugin.{len(privileges)}"),
        privileges=privileges,
    )


@pytest.fixture
def empty_plan() -> EffectPolicyPlan:
    """EffectPolicyPlan constructed without ``privileges=`` (backward-compat)."""
    return EffectPolicyPlan()


# ---------------------------------------------------------------------------
# 1. Empty / missing input
# ---------------------------------------------------------------------------


def test_plan_with_no_privileges_returns_unchanged(empty_plan: EffectPolicyPlan) -> None:
    """No contracts + empty existing privileges → return the input plan unchanged."""
    result = project_privileges_into_effect_policy(empty_plan, ())
    assert result is empty_plan


def test_plan_with_empty_contracts_returns_unchanged_privileges() -> None:
    """Empty contracts tuple preserves any existing privileges verbatim."""
    plan = EffectPolicyPlan(privileges=("journal.append", "state.write"))
    result = project_privileges_into_effect_policy(plan, ())
    assert result is plan
    assert result.privileges == ("journal.append", "state.write")


def test_plan_with_default_empty_contracts_arg() -> None:
    """``plugin_contracts`` is optional (defaults to empty tuple)."""
    plan = EffectPolicyPlan()
    # Omitting the second arg must not break the signature.
    result = project_privileges_into_effect_policy(plan)
    assert result is plan


# ---------------------------------------------------------------------------
# 2. Single & multiple contracts
# ---------------------------------------------------------------------------


def test_single_contract_privileges_projected() -> None:
    """A single contract's privileges are projected into the plan."""
    plan = EffectPolicyPlan()
    contract = _contract(("journal.append", "network.egress"))

    result = project_privileges_into_effect_policy(plan, (contract,))

    assert result.privileges == ("journal.append", "network.egress")


def test_multiple_contracts_privileges_unioned() -> None:
    """Privileges from multiple contracts are unioned."""
    plan = EffectPolicyPlan()
    c1 = _contract(("journal.append",))
    c2 = _contract(("network.egress",))
    c3 = _contract(("state.write", "tools.invoke"))

    result = project_privileges_into_effect_policy(plan, (c1, c2, c3))

    assert result.privileges == (
        "journal.append",
        "network.egress",
        "state.write",
        "tools.invoke",
    )


# ---------------------------------------------------------------------------
# 3. Deduplication & determinism (C8)
# ---------------------------------------------------------------------------


def test_duplicates_removed() -> None:
    """Duplicate privileges across contracts collapse to a single entry."""
    plan = EffectPolicyPlan()
    c1 = _contract(("journal.append", "state.write"))
    c2 = _contract(("state.write", "network.egress"))
    c3 = _contract(("network.egress",))

    result = project_privileges_into_effect_policy(plan, (c1, c2, c3))

    assert result.privileges == ("journal.append", "network.egress", "state.write")


def test_duplicates_within_a_single_contract_removed() -> None:
    """PluginContract is itself expected to dedupe; projector is robust."""
    plan = EffectPolicyPlan()
    # PluginContract.privileges is a tuple — duplicates here simply get
    # collapsed by the projector's set semantics.
    contract = _contract(("journal.append", "journal.append", "state.write"))

    result = project_privileges_into_effect_policy(plan, (contract,))

    assert result.privileges == ("journal.append", "state.write")


def test_result_privileges_sorted() -> None:
    """Privileges in the resulting plan are lexicographically sorted (C8)."""
    plan = EffectPolicyPlan()
    contract = _contract(("zeta.write", "alpha.read", "mid.do"))

    result = project_privileges_into_effect_policy(plan, (contract,))

    assert result.privileges == tuple(sorted(result.privileges))
    assert result.privileges == ("alpha.read", "mid.do", "zeta.write")


# ---------------------------------------------------------------------------
# 4. Union with existing privileges (idempotency)
# ---------------------------------------------------------------------------


def test_existing_privileges_preserved() -> None:
    """Pre-existing plan privileges are preserved (union, not replace)."""
    plan = EffectPolicyPlan(privileges=("journal.append",))
    contract = _contract(("network.egress",))

    result = project_privileges_into_effect_policy(plan, (contract,))

    assert result.privileges == ("journal.append", "network.egress")


def test_existing_and_new_overlap_merged() -> None:
    """When contract overlaps with existing privileges, the union is the superset."""
    plan = EffectPolicyPlan(
        privileges=("journal.append", "tools.invoke"),
    )
    contract = _contract(("journal.append", "state.write"))

    result = project_privileges_into_effect_policy(plan, (contract,))

    # Sorted, deduplicated union: ``journal.append`` appears once.
    assert result.privileges == (
        "journal.append",
        "state.write",
        "tools.invoke",
    )


# ---------------------------------------------------------------------------
# 5. Immutability (frozen dataclass)
# ---------------------------------------------------------------------------


def test_input_plan_not_mutated() -> None:
    """The original ``EffectPolicyPlan`` is not modified by the projector."""
    plan = EffectPolicyPlan(privileges=("journal.append",))
    original_privileges = plan.privileges
    contract = _contract(("network.egress", "state.write"))

    result = project_privileges_into_effect_policy(plan, (contract,))

    # Input plan is frozen + its privileges did not change.
    assert plan.privileges == original_privileges
    assert dataclasses.is_dataclass(plan)
    # The frozen dataclass raises FrozenInstanceError on direct mutation.
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.privileges = ("different",)  # type: ignore[misc]

    # Result is a distinct plan (not the same object) when privileges changed.
    assert result is not plan


def test_input_plan_not_mutated_when_no_change() -> None:
    """Identity is preserved (same plan returned) when no new privileges arrive."""
    plan = EffectPolicyPlan(privileges=("journal.append",))
    contract = _contract(("journal.append",))  # duplicate of existing

    result = project_privileges_into_effect_policy(plan, (contract,))

    # No new privileges → no copy.
    assert result is plan


# ---------------------------------------------------------------------------
# 6. Convenience wrapper: compile + project
# ---------------------------------------------------------------------------


def test_build_with_privileges_combines_compile_and_projection() -> None:
    """``build_effect_policy_with_privileges`` composes compile + projection.

    When ``compile_effect_policy`` returns the ``("none",)`` default plan
    (no specs), the wrapper just adds privileges and returns that plan.
    """
    contract = _contract(("journal.append", "network.egress"))

    result = build_effect_policy_with_privileges((), (contract,))

    assert isinstance(result, EffectPolicyPlan)
    assert result.privileges == ("journal.append", "network.egress")
    # compile_effect_policy default: gateway + allowed_effects = ("none",).
    assert result.gateway_capability == "effect.gateway"


def test_build_with_privileges_default_contracts() -> None:
    """``plugin_contracts`` defaults to empty tuple in the wrapper too."""
    result = build_effect_policy_with_privileges(())

    assert isinstance(result, EffectPolicyPlan)
    assert result.privileges == ()


# ---------------------------------------------------------------------------
# 7. Backward-compatibility: EffectPolicyPlan field default
# ---------------------------------------------------------------------------


def test_privileges_default_empty_in_plan() -> None:
    """``EffectPolicyPlan()`` constructs with ``privileges=()`` (backward-compat)."""
    plan = EffectPolicyPlan()
    assert plan.privileges == ()


def test_effect_policy_plan_accepts_privileges_kwarg() -> None:
    """``EffectPolicyPlan(privileges=...)`` accepts the new field explicitly."""
    plan = EffectPolicyPlan(privileges=("journal.append",))
    assert plan.privileges == ("journal.append",)


def test_effect_policy_plan_privileges_field_in_annotations() -> None:
    """The dataclass exposes ``privileges`` as a typed field."""
    annotations = get_type_hints(EffectPolicyPlan)
    assert "privileges" in annotations
    # Annotation is roughly ``tuple[str, ...]``; exact form depends on Python.
    assert "str" in str(annotations["privileges"])


def test_existing_compile_effect_policy_still_works() -> None:
    """Existing call sites of ``compile_effect_policy`` keep working.

    The projector does NOT alter the existing builder — backward-compat.
    """
    plan = compile_effect_policy(())
    assert isinstance(plan, EffectPolicyPlan)
    # Default ``privileges`` field added in P3-06 is empty.
    assert plan.privileges == ()


# ---------------------------------------------------------------------------
# 8. Module purity (no I/O imports)
# ---------------------------------------------------------------------------


def test_no_io_imports_in_module() -> None:
    """The projector module is pure (no I/O, no env reads, no logging).

    Per ADR-0015 contracts purity: projection must be deterministic and
    free of side effects at module-load time.
    """
    from lca.harness.declarative.compile.effect import privilege_projection

    source = inspect.getsource(privilege_projection)
    forbidden = (
        "import os",
        "from os",
        "open(",
        "logging.",
        "print(",
        "requests.",
        "urllib.",
        "subprocess.",
    )
    for token in forbidden:
        assert token not in source, f"forbidden token {token!r} found in module source"


def test_projector_signature_is_pure() -> None:
    """``project_privileges_into_effect_policy`` is a regular function (pure)."""
    assert callable(project_privileges_into_effect_policy)
    sig = inspect.signature(project_privileges_into_effect_policy)
    # First parameter is positional-or-keyword; the rest are keyword-only
    # by intent (only ``plugin_contracts`` is extra).
    assert "plan" in sig.parameters
    assert "plugin_contracts" in sig.parameters
