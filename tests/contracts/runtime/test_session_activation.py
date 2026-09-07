"""Tests for ``SessionActivation`` (PR-0199-P1-03).

The parallel P1-01 / P1-02 contracts (``RunIntent``, ``TrustEnvelope``) and
the activation_ref hash util are not yet merged, so the tests build minimal
in-test stubs that satisfy the structural contracts. Once those PRs land the
stubs can be replaced with the canonical imports; the structural surface
(SessionActivation field shape + validation contract) is stable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.runtime.activation import SessionActivation

# ── Stubs (replaced by P1-01/P1-02 imports after they land) ──────────


@dataclass(frozen=True, slots=True)
class _StubTrustEnvelope:
    """Stand-in for ``lca.contracts.runtime.trust.TrustEnvelope``."""

    plugin_origins: tuple = ()
    granted_privileges: tuple = ()


@dataclass(frozen=True, slots=True)
class _StubCompiledRunPlan:
    """Stand-in for ``lca.contracts.protocols.state.plan.CompiledRunPlan``.

    Mirrors the minimal surface that ``SessionActivation`` consumers rely on:
    ``plan_ref`` as the canonical handle.
    """

    plan_ref: str
    profile_path: str = ""
    capability: object = None
    scope: object = None


def _activation(**overrides):
    """Build a minimal valid ``SessionActivation`` for tests."""
    kwargs = {
        "activation_ref": "act-1",
        "plan_ref": "plan-1",
        "graph_ref": "graph-1",
        "plugin_set_ref": "plugin-set-1",
        "profile_path": "/abs/profiles/x.yaml",
        "session_id": "sess-1",
        "trust_envelope": _StubTrustEnvelope(),
    }
    kwargs.update(overrides)
    return SessionActivation(**kwargs)


# ── Constructors ─────────────────────────────────────────────────────


def test_construct_minimal():
    """Construction without ``compiled_plan`` is accepted (None default)."""
    act = _activation()

    assert act.activation_ref == "act-1"
    assert act.plan_ref == "plan-1"
    assert act.graph_ref == "graph-1"
    assert act.plugin_set_ref == "plugin-set-1"
    assert act.profile_path == "/abs/profiles/x.yaml"
    assert act.session_id == "sess-1"
    assert act.compiled_plan is None
    assert isinstance(act.trust_envelope, _StubTrustEnvelope)


def test_construct_with_compiled_plan():
    """A ``CompiledRunPlan``-shaped stub can be attached as read-only reference."""
    plan = _StubCompiledRunPlan(plan_ref="plan-1")
    act = _activation(compiled_plan=plan)

    assert act.compiled_plan is plan
    assert act.compiled_plan.plan_ref == "plan-1"


def test_compiled_plan_optional():
    """``compiled_plan`` defaults to ``None`` and may be explicitly None."""
    assert _activation().compiled_plan is None
    assert _activation(compiled_plan=None).compiled_plan is None


# ── Validation: empty refs rejected ─────────────────────────────────


@pytest.mark.parametrize(
    "field_name",
    ["activation_ref", "plan_ref", "graph_ref", "plugin_set_ref"],
)
def test_rejects_empty_string_refs(field_name):
    with pytest.raises(ValueError, match=field_name):
        _activation(**{field_name: ""})


def test_rejects_empty_session_id():
    with pytest.raises(ValueError, match="session_id"):
        _activation(session_id="")


def test_rejects_empty_profile_path():
    with pytest.raises(ValueError, match="profile_path"):
        _activation(profile_path="")


def test_rejects_non_string_activation_ref():
    with pytest.raises(ValueError, match="activation_ref"):
        SessionActivation(
            activation_ref=None,  # type: ignore[arg-type]
            plan_ref="plan-1",
            graph_ref="graph-1",
            plugin_set_ref="plugin-set-1",
            profile_path="/abs/profiles/x.yaml",
            session_id="sess-1",
            trust_envelope=_StubTrustEnvelope(),
        )


# ── Frozen / slots guarantees ────────────────────────────────────────


def test_frozen_blocks_mutation():
    act = _activation()
    with pytest.raises((AttributeError, Exception)):
        act.session_id = "mutated"  # type: ignore[misc]


def test_slots_blocks_arbitrary_attributes():
    """``slots=True`` rejects unknown attributes at runtime.

    CPython surfaces this as ``AttributeError`` for ordinary classes; when
    ``frozen=True`` is layered on top, the C-level slot check may raise
    ``TypeError``. Accept both — the contract is "the assignment is rejected".
    """
    act = _activation()
    with pytest.raises((AttributeError, TypeError)):
        act.not_a_field = "x"  # type: ignore[attr-defined]
