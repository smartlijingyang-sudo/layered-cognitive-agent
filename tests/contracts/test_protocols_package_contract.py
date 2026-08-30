"""Contract tests for ``lca.contracts.protocols`` package surface.

The barrel re-exports every public protocol symbol so callers can keep using
``from lca.contracts.protocols import X``. The contract is:

1. Every deliberate re-export (each ``from ... import ...`` line above) appears
   in ``__all__``.
2. Every name in ``__all__`` is importable from the package.
3. ``__all__`` is derived from the imports (single source of truth): a test
   catches drift if the two diverge.
4. Submodule side-effects (Python auto-binds submodule names when their
   children are imported) and ``from __future__ import annotations`` are not
   declared public.
"""

from __future__ import annotations

import types

import pytest

import lca.contracts.protocols as protocols


class TestProtocolsPackageSurface:
    def test_all_names_are_importable(self) -> None:
        for name in protocols.__all__:
            assert hasattr(protocols, name), (
                f"__all__ declares {name!r} but it is not bound on the package"
            )

    def test_all_names_resolve_to_real_objects(self) -> None:
        for name in protocols.__all__:
            value = getattr(protocols, name)
            assert value is not None
            assert not isinstance(value, types.ModuleType), (
                f"{name!r} resolves to a submodule; submodule side-effects "
                f"should be filtered out of __all__"
            )

    def test_all_derived_from_explicit_reexports(self) -> None:
        derived = sorted(
            name
            for name, value in vars(protocols).items()
            if not name.startswith("_")
            and not isinstance(value, types.ModuleType)
            and name != "annotations"
        )
        assert protocols.__all__ == derived, (
            "lca.contracts.protocols.__all__ drifted away from the "
            "explicit re-exports. The derivation is the source of truth."
        )

    def test_submodule_side_effects_excluded(self) -> None:
        """Python auto-binds submodule names when their children are imported."""
        for name in protocols.__all__:
            assert not name.startswith("lca"), (
                f"{name!r} looks like a module path that leaked into __all__"
            )

    def test_future_annotations_excluded(self) -> None:
        assert "annotations" not in protocols.__all__

    def test_public_surface_is_nonempty(self) -> None:
        assert len(protocols.__all__) > 100, (
            "Public surface should still cover the full protocol set"
        )


@pytest.mark.parametrize(
    "name",
    [
        "LLMAdapter",
        "Body",
        "Brain",
        "Runtime",
        "Reducer",
        "SkillPackage",
        "CompiledRunPlan",
        "PhaseExecutor",
        "ToolExecutionPipeline",
    ],
)
def test_well_known_symbols_remain_public(name: str) -> None:
    """Spot-check that flagship symbols survive the derivation."""
    assert name in protocols.__all__
    assert hasattr(protocols, name)
