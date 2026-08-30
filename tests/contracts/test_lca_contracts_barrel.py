"""Round 90 regression: ``lca.contracts`` barrel derives ``__all__`` from
its explicit re-exports. Adding a new re-export is a one-line edit; the
derived ``__all__`` updates without a second maintenance step.
"""

from __future__ import annotations

import types

import pytest

import lca.contracts as contracts


class TestContractsBarrelSurface:
    def test_all_names_are_importable(self) -> None:
        for name in contracts.__all__:
            assert hasattr(contracts, name), (
                f"__all__ declares {name!r} but it is not bound on the package"
            )

    def test_all_names_resolve_to_real_objects(self) -> None:
        for name in contracts.__all__:
            value = getattr(contracts, name)
            assert value is not None
            assert not isinstance(value, types.ModuleType), (
                f"{name!r} resolves to a submodule; submodule side-effects "
                f"should be filtered out of __all__"
            )

    def test_all_derived_from_explicit_reexports(self) -> None:
        derived = sorted(
            name
            for name, value in vars(contracts).items()
            if not name.startswith("_")
            and not isinstance(value, types.ModuleType)
            and name != "annotations"
        )
        assert contracts.__all__ == derived, (
            "lca.contracts.__all__ drifted away from the explicit "
            "re-exports. The derivation is the source of truth."
        )

    def test_submodule_side_effects_excluded(self) -> None:
        for name in contracts.__all__:
            assert not name.startswith("lca"), (
                f"{name!r} looks like a module path that leaked into __all__"
            )

    def test_future_annotations_excluded(self) -> None:
        assert "annotations" not in contracts.__all__

    def test_public_surface_is_nonempty(self) -> None:
        assert len(contracts.__all__) > 50


@pytest.mark.parametrize(
    "name",
    [
        "AgentState",
        "Decision",
        "Result",
        "RunContext",
        "Pipeline",
        "create_budget",
    ],
)
def test_well_known_symbols_remain_public(name: str) -> None:
    """Spot-check flagship public surface survives the derivation."""
    assert name in contracts.__all__
    assert hasattr(contracts, name)