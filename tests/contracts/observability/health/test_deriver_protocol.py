"""Contract tests for ``HealthDeriver`` Protocol + entry-point registration (PR-1 / Task 1.2).

Upholds AGENTS.md §3 C13 (information bloodline closure): the deriver
contract lives in ``lca/contracts/observability/health/deriver.py`` and
upholds the D1 (definition) and D2 (constraint) surfaces for the
``lca.health_derivers`` entry-point group. D3 (transform) and D4 (consumer)
live in ``lca/plugins/observability/health/`` (out of scope for this task).

Upholds AGENTS.md §5 (change closure): every new deriver is added by (a)
creating ``lca/plugins/observability/health/derivers/<name>_deriver.py`` with
a class implementing ``HealthDeriver.evaluate``, and (b) adding a single
line to ``pyproject.toml`` under ``[project.entry-points."lca.health_derivers"]``.
No contract change, no fold change, no consumer change.

Entry-point target functions DO NOT yet exist (Task 1.3 creates the actual
derivers). The ``test_entry_point_load_can_be_called`` case proves the
registration is wired correctly by capturing the expected ``ImportError``
on the not-yet-existing target module path.
"""

from __future__ import annotations

import importlib.metadata

from lca.contracts.observability.health import (
    RunHealthCondition as RunHealthCondition,
)

# The 8 PR-1 deriver types. ``tool`` covers sandbox as a sub-rule
# (spec §15 G-21); there is no separate ``sandbox`` deriver.
EXPECTED_DERIVER_NAMES: frozenset[str] = frozenset(
    {"perceive", "think", "act", "tool", "llm", "reflect", "remember", "lifecycle"}
)


def _expected_target(name: str) -> str:
    """The pyproject.toml target path for a given deriver name.

    e.g. ``perceive`` -> ``lca.plugins.observability.health.derivers.perceive_deriver:PerceiveDeriver``
    """
    camel = "".join(part.capitalize() for part in name.split("_"))
    return f"lca.plugins.observability.health.derivers.{name}_deriver:{camel}Deriver"


# ---------------------------------------------------------------------------
# Protocol definition (lca.contracts.observability.health.deriver)
# ---------------------------------------------------------------------------


def test_health_deriver_protocol_is_importable() -> None:
    """``HealthDeriver`` is importable from the new module path.

    Until Task 1.2 lands, this import raises ``ImportError`` (red phase).
    """
    from lca.contracts.observability.health.deriver import (
        HealthDeriver as HealthDeriver,
    )


def test_health_deriver_protocol_evaluate_signature() -> None:
    """``HealthDeriver`` exposes ``evaluate(self, events: list) -> list[RunHealthCondition]``.

    Confirms the structural shape of the protocol; consumers (the fold
    function in Task 1.4) rely on this signature.
    """
    from lca.contracts.observability.health.deriver import HealthDeriver

    annotations = HealthDeriver.evaluate.__annotations__
    # ``self`` is implicit; the parameters we care about are ``events``
    # and the return annotation.
    assert "events" in annotations
    assert annotations["events"] == "list"
    assert "return" in annotations
    assert annotations["return"] == "list[RunHealthCondition]"


def test_health_deriver_is_runtime_checkable() -> None:
    """``isinstance(obj, HealthDeriver)`` works for duck-typed objects.

    An object that defines ``evaluate(events)`` (regardless of return type
    or parameter annotation — ``runtime_checkable`` only checks method
    presence) must be recognized as a ``HealthDeriver`` instance even
    though it never subclasses the Protocol. Objects lacking ``evaluate``
    must NOT be recognized.
    """
    from lca.contracts.observability.health.deriver import HealthDeriver

    class _GoodDeriver:
        def evaluate(self, events: list) -> list[RunHealthCondition]:
            return []

    class _NoEvaluate:
        pass

    assert isinstance(_GoodDeriver(), HealthDeriver)
    assert not isinstance(_NoEvaluate(), HealthDeriver)


# ---------------------------------------------------------------------------
# Entry-point registration (pyproject.toml [project.entry-points."lca.health_derivers"])
# ---------------------------------------------------------------------------


def test_8_entry_points_registered() -> None:
    """The ``lca.health_derivers`` entry-point group has exactly 8 entries.

    Set equality, no extras, no missing. ``importlib.metadata.entry_points``
    reads the installed metadata; ``pip install -e .`` must have been run
    after the ``pyproject.toml`` change.
    """
    eps = importlib.metadata.entry_points(group="lca.health_derivers")
    names = frozenset(ep.name for ep in eps)
    assert names == EXPECTED_DERIVER_NAMES, (
        f"expected exactly {sorted(EXPECTED_DERIVER_NAMES)}, got {sorted(names)}"
    )
    assert len(eps) == 8


def test_entry_point_targets_match_documented_path() -> None:
    """Each entry-point target matches ``<name>_deriver:<Name>Deriver`` pattern.

    e.g. ``perceive`` -> ``lca.plugins.observability.health.derivers.perceive_deriver:PerceiveDeriver``.
    """
    eps = importlib.metadata.entry_points(group="lca.health_derivers")
    for ep in eps:
        assert ep.value == _expected_target(ep.name), (
            f"entry-point {ep.name!r} has wrong target {ep.value!r}; "
            f"expected {_expected_target(ep.name)!r}"
        )


def test_entry_point_load_can_be_called() -> None:
    """Each entry-point loads successfully and returns a ``HealthDeriver`` instance.

    Task 1.2 wrote this test in its RED phase to prove the registration
    was wired correctly by capturing the expected ``ImportError`` on
    the not-yet-existing target module. Task 1.3 has now created the
    eight deriver classes, so the green-phase check is that ``ep.load()``
    succeeds and returns an object that satisfies the ``HealthDeriver``
    Protocol (``isinstance(obj, HealthDeriver)``).

    This is the natural flip of the Task 1.2 red-phase assertion — the
    test was written to be brittle on purpose so a future maintainer
    who breaks the wiring will see this test go red.
    """
    from lca.contracts.observability.health.deriver import HealthDeriver

    eps = importlib.metadata.entry_points(group="lca.health_derivers")
    for ep in eps:
        obj = ep.load()()
        assert isinstance(obj, HealthDeriver), (
            f"entry-point {ep.name!r} loaded object is not a HealthDeriver instance"
        )
        assert hasattr(obj, "evaluate"), (
            f"entry-point {ep.name!r} loaded object lacks evaluate() method"
        )
