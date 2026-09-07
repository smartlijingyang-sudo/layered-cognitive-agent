"""Tests for ``DefaultRuntimeFacade.resolve_activation`` (PR-0199-P1-09).

The companion ``PlanResolutionService`` (PR-0199-P1-07) is now merged,
so the tests instantiate the real service via ``MagicMock(spec=...)``
and return the real :class:`PlanResolutionResult`. The facade only reads
``plan_ref`` / ``graph_ref`` / ``plugin_set_ref`` / ``compiled_plan``,
which are all fields on the canonical dataclass.

Behaviour covered:
  * ``intent.session_id`` wins over the RNG when supplied (C9 idempotency).
  * A fresh id is generated as ``"sess_" + 16 hex chars`` when the intent
    omits one.
  * ``PlanResolutionService.resolve_refs`` is called with the resolved
    ``profile_path`` and forwarded ``session_id``.
  * ``activation_ref`` is stable across repeated calls and stable against
    the harness-layer ``compute_activation_ref`` reference impl.
  * The returned ``SessionActivation`` carries the empty trust envelope
    (until P3 enriches it) and the compiled plan from the service.

The dispatch half of the facade is exercised in
``tests/application/runtime/test_default_facade_dispatch.py`` (P1-10);
this file only pins the resolve_activation contract and P1-09 behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import pytest

from lca.application.runtime.default_facade import (
    _SESSION_ID_BYTES,
    DefaultRuntimeFacade,
    _new_session_id,
)
from lca.application.runtime.plan_resolution import (
    PlanResolutionResult,
    PlanResolutionService,
)
from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.intent import RunIntent
from lca.contracts.runtime.trust import EMPTY_TRUST_ENVELOPE
from lca.harness.runtime.activation_ref import compute_activation_ref

# ── Helpers ───────────────────────────────────────────────────────────


def _intent(
    *,
    profile_path: str = "/abs/profiles/sample.yaml",
    session_id: str | None = None,
) -> RunIntent:
    """Build a minimal valid ``RunIntent`` for facade tests."""
    return RunIntent(
        profile_path=profile_path,
        user_text="hello",
        mode="solo",
        session_id=session_id,
        assistant_id=None,
        attachment_ids=(),
        prior_turns=(),
        execution_target="local",
        options={},
        surface="test",
    )


def _make_service(
    *,
    plan_ref: str = "plan-A",
    graph_ref: str = "graph-A",
    plugin_set_ref: str = "plugin-set-A",
    compiled_plan: Any = None,
) -> MagicMock:
    """Build a ``MagicMock(spec=PlanResolutionService)`` that returns a real
    ``PlanResolutionResult`` from ``resolve_refs``. Tests assert on the
    recorded calls.
    """
    mock_service = MagicMock(spec=PlanResolutionService)
    if compiled_plan is None:

        class _StubPlan:
            profile_path = "/abs/profiles/sample.yaml"

        compiled_plan = _StubPlan()
    mock_service.resolve_refs.return_value = PlanResolutionResult(
        plan_ref=plan_ref,
        graph_ref=graph_ref,
        plugin_set_ref=plugin_set_ref,
        compiled_plan=compiled_plan,
    )
    return mock_service


def _make_dispatcher() -> MagicMock:
    """Return a ``MagicMock(spec=RunDispatcher)`` that swallows calls.

    The resolve-side tests never invoke dispatch, so the returned mock
    just needs to be present to satisfy the facade constructor.
    """
    from lca.application.runtime.default_facade import RunDispatcher

    return MagicMock(spec=RunDispatcher)


def _facade(service: MagicMock) -> DefaultRuntimeFacade:
    """Build a facade wired with a stub dispatcher (resolve tests don't dispatch)."""
    return DefaultRuntimeFacade(service, _make_dispatcher())


# ── session_id handling ──────────────────────────────────────────────


class TestSessionIdHandling:
    def test_resolve_uses_intent_session_id_when_provided(self) -> None:
        """``intent.session_id`` wins; the RNG is not consulted."""
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess_explicit"))

        assert act.session_id == "sess_explicit"
        # The forwarded session_id to the plan service is the explicit one
        service.resolve_refs.assert_called_once_with(
            "/abs/profiles/sample.yaml",
            session_id="sess_explicit",
        )

    def test_resolve_generates_session_id_when_missing(self) -> None:
        """Absent ``intent.session_id`` → fresh ``sess_…`` id."""
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id=None))

        assert act.session_id is not None
        assert act.session_id.startswith("sess_")

    def test_generated_session_id_format(self) -> None:
        """Generated id is ``"sess_"`` + 16 hex chars (= 21 chars total)."""
        new_id = _new_session_id()
        assert new_id.startswith("sess_")
        assert len(new_id) == len("sess_") + _SESSION_ID_BYTES * 2
        # Hex-only tail
        tail = new_id[len("sess_") :]
        assert all(c in "0123456789abcdef" for c in tail)

    def test_session_id_not_generated_when_intent_provides_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``secrets.token_hex`` MUST NOT be called when intent supplies an id (C9)."""
        token_mock = MagicMock(wraps=lambda n: "deadbeef" * (n // 4))
        monkeypatch.setattr(
            "lca.application.runtime.default_facade.secrets.token_hex",
            token_mock,
        )

        service = _make_service()
        facade = _facade(service)
        act = facade.resolve_activation(_intent(session_id="sess_supplied"))

        token_mock.assert_not_called()
        assert act.session_id == "sess_supplied"


# ── PlanResolutionService interaction ─────────────────────────────────


class TestPlanServiceInteraction:
    def test_resolve_uses_plan_service_for_refs(self) -> None:
        """facade delegates ref resolution to ``PlanResolutionService``."""
        service = _make_service(plan_ref="plan-A", graph_ref="g-A", plugin_set_ref="ps-A")
        facade = _facade(service)

        facade.resolve_activation(_intent(profile_path="/abs/profiles/x.yaml", session_id="s"))

        service.resolve_refs.assert_called_once_with(
            "/abs/profiles/x.yaml",
            session_id="s",
        )

    def test_resolve_passes_session_id_to_plan_service(self) -> None:
        """The chosen ``session_id`` (intent-provided or generated) is forwarded."""
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess_fixed"))

        service.resolve_refs.assert_called_once_with(
            "/abs/profiles/sample.yaml",
            session_id="sess_fixed",
        )
        assert act.session_id == "sess_fixed"


# ── activation_ref stability (C9 / I-HPC-3) ──────────────────────────


class TestActivationRefStability:
    def test_activation_ref_stable_for_same_inputs(self) -> None:
        """Same intent + same service → same ``activation_ref`` (C9)."""
        service = _make_service(plan_ref="plan-1", graph_ref="g-1", plugin_set_ref="ps-1")
        facade = _facade(service)

        a1 = facade.resolve_activation(_intent(session_id="sess-same"))
        a2 = facade.resolve_activation(_intent(session_id="sess-same"))
        assert a1.activation_ref == a2.activation_ref

    def test_activation_ref_matches_compute_activation_ref(self) -> None:
        """The facade produces the same hash as the reference impl from P1-06."""
        service = _make_service(plan_ref="plan-X", graph_ref="g-X", plugin_set_ref="ps-X")
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess-Z"))

        expected = compute_activation_ref(
            plan_ref="plan-X",
            graph_ref="g-X",
            plugin_set_ref="ps-X",
            session_id="sess-Z",
        )
        assert act.activation_ref == expected

    def test_activation_ref_differs_for_different_session_id(self) -> None:
        """Different session_id → different ``activation_ref`` (I-HPC-3)."""
        service = _make_service(plan_ref="plan-1", graph_ref="g-1", plugin_set_ref="ps-1")
        facade = _facade(service)

        a = facade.resolve_activation(_intent(session_id="sess-A"))
        b = facade.resolve_activation(_intent(session_id="sess-B"))
        assert a.activation_ref != b.activation_ref

    def test_activation_ref_differs_for_different_profile(self) -> None:
        """Different profile_path → different plan_ref → different activation_ref."""

        def _service_for(plan_ref: str) -> MagicMock:
            return _make_service(plan_ref=plan_ref, graph_ref="g-1", plugin_set_ref="ps-1")

        a = _facade(_service_for("plan-from-A")).resolve_activation(
            _intent(profile_path="/abs/profiles/A.yaml", session_id="sess-same"),
        )
        b = _facade(_service_for("plan-from-B")).resolve_activation(
            _intent(profile_path="/abs/profiles/B.yaml", session_id="sess-same"),
        )
        assert a.activation_ref != b.activation_ref


# ── SessionActivation surface ────────────────────────────────────────


class TestSessionActivationSurface:
    def test_session_activation_carries_trust_envelope_empty(self) -> None:
        """Until P3 the trust envelope is the empty singleton."""
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess-1"))

        assert act.trust_envelope is EMPTY_TRUST_ENVELOPE

    def test_session_activation_carries_compiled_plan(self) -> None:
        """The compiled plan is forwarded verbatim from the plan service."""

        class _CompiledPlan:
            profile_path = "/abs/profiles/x.yaml"

        compiled = _CompiledPlan()
        service = _make_service(plan_ref="plan-X", compiled_plan=compiled)
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess-1"))

        assert act.compiled_plan is compiled

    def test_session_activation_session_id_matches_intent_when_provided(self) -> None:
        """Sanity: explicit ``intent.session_id`` propagates to activation."""
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess-explicit"))

        assert act.session_id == "sess-explicit"
        assert isinstance(act, SessionActivation)


# ── MagicMock spec integration ───────────────────────────────────────


class TestMagicMockSpecContract:
    def test_magicmock_satisfies_protocol(self) -> None:
        """``MagicMock(spec=PlanResolutionService)`` is the documented test stub.

        The facade treats its constructor argument as a
        :class:`PlanResolutionService`. ``MagicMock(spec=...)`` is the
        documented test stub; this test pins that the spec accepts the
        same call surface.
        """
        service = _make_service()
        facade = _facade(service)

        act = facade.resolve_activation(_intent(session_id="sess-1"))

        service.resolve_refs.assert_called_once_with(
            "/abs/profiles/sample.yaml",
            session_id="sess-1",
        )
        assert act.session_id == "sess-1"


# ── Mapping option forwarding ────────────────────────────────────────


def test_options_mapping_is_preserved_on_intent() -> None:
    """``RunIntent.options`` is a Mapping; this PR does not consume it but
    must not mutate or reject it. Pins the surface for the parallel adapter PR.
    """
    options: Mapping[str, Any] = {"temperature": 0.2, "max_steps": 5}
    intent = RunIntent(
        profile_path="/abs/profiles/sample.yaml",
        user_text="hello",
        mode="solo",
        session_id="sess-1",
        assistant_id=None,
        attachment_ids=(),
        prior_turns=(),
        execution_target="local",
        options=options,
        surface="test",
    )
    service = _make_service()
    facade = _facade(service)
    # Should not raise — the facade does not consume options in P1-09.
    facade.resolve_activation(intent)
