"""PR-C end state: ``CordisComposer`` is constructed directly at assembly roots.

After PR-C deletes the Cordis provider plugin that previously published the
typed seam for runtime-bound Composer factories, assembly roots — the
``CordisControlToolFactory.create`` entry point and the
``application/api`` composition root — construct :class:`CordisComposer`
inline using ``build_default_invariant_checker``.

This test pins the relocated ``CordisComposer`` API surface and the
inline-construction wiring in ``cordis_control``. The string literals
guarding against leftover references live in
``tests/architecture/test_no_compat_residue.py`` to keep this file
clear of the negative-grep patterns.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from lca.contracts.capabilities import CORDIS_CONTROL_TOOL_FACTORY
from lca.plugins.composer.composition.cordis_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control import CordisControlToolFactory


def test_cordis_composer_importable_from_composer_composition() -> None:
    """The relocated ``CordisComposer`` is importable from the helper module."""
    composer = CordisComposer(MagicMock())
    assert composer is not None
    # Default invariant checker is wired when none is passed.
    assert composer._invariant is not None  # type: ignore[attr-defined]


def test_build_default_invariant_checker_returns_implementing_protocol() -> None:
    """``build_default_invariant_checker`` returns an InvariantChecker implementation."""
    from lca.contracts.mechanisms.composition.composition import InvariantChecker

    checker = build_default_invariant_checker()
    assert isinstance(checker, InvariantChecker)


def test_cordis_control_tool_factory_constructs_composer_inline() -> None:
    """``CordisControlToolFactory.create`` builds ``CordisComposer`` without capability lookup."""
    from lca.plugins.tools.cordis_control.tool import build_cordis_control_tool

    scope = SimpleNamespace(own_bindings={})
    factory = CordisControlToolFactory(caller_grant=("cordis_control.inspect",))

    # Spy on the helper to verify inline construction.
    captured: dict[str, object] = {}

    real_build = build_cordis_control_tool

    def spy_build(*args: object, **kwargs: object) -> object:
        captured["composer"] = kwargs.get("composer") or (args[0] if args else None)
        return real_build(*args, **kwargs)

    import lca.plugins.tools.cordis_control as cc_module

    cc_module.build_cordis_control_tool = spy_build  # type: ignore[assignment]
    try:
        factory.create(scope=scope, actor_role="creator")
    finally:
        cc_module.build_cordis_control_tool = real_build  # type: ignore[assignment]

    composer = captured.get("composer")
    assert isinstance(composer, CordisComposer), (
        f"CordisControlToolFactory must construct CordisComposer directly, "
        f"got {type(composer).__name__ if composer else None}"
    )


def test_cordis_control_tool_factory_capability_seam_unchanged() -> None:
    """The ``cordis_control_tool_factory`` capability is preserved (composition root)."""
    assert CORDIS_CONTROL_TOOL_FACTORY.key == "cordis_control_tool_factory"


__all__ = [
    "test_cordis_composer_importable_from_composer_composition",
    "test_build_default_invariant_checker_returns_implementing_protocol",
    "test_cordis_control_tool_factory_constructs_composer_inline",
    "test_cordis_control_tool_factory_capability_seam_unchanged",
]
