"""R6 regression: 6 normalize helpers moved into ``plugin_declaration.py``.

The helpers used to live in ``lca.harness.plugin_declaration_normalization``;
R6 folds them into ``lca.harness.plugin_declaration`` as private
``_normalize_*`` / ``_config_from_annotations`` functions so the public
``@plugin`` decorator no longer fans out across two modules.
"""

from __future__ import annotations

import pytest


def test_normalize_helpers_importable_from_plugin_declaration() -> None:
    """The 6 helpers must be importable from ``lca.harness.plugin_declaration``.

    All are private (underscore-prefixed) because they are internal plumbing
    for ``@plugin`` / ``definition_from_plugin`` — public callers go through
    ``lca.harness.plugin_api``.
    """
    import lca.harness.plugin_declaration as pd

    for name in (
        "_normalize_keys",
        "_normalize_implements",
        "_normalize_effects",
        "_normalize_relations",
        "_normalize_contributes",
        "_config_from_annotations",
    ):
        assert hasattr(pd, name), f"missing {name} in plugin_declaration"


def test_plugin_declaration_normalization_module_deleted() -> None:
    """The old standalone normalization module must be gone."""
    with pytest.raises(ImportError):
        import lca.harness.plugin_declaration_normalization  # noqa: F401


def test_normalize_helpers_callable_and_stable() -> None:
    """Spot-check the consolidated helpers still return the expected shapes.

    Guards against accidental signature drift during the move.
    """
    from lca.harness.plugin_declaration import (
        _normalize_effects,
        _normalize_implements,
        _normalize_keys,
        _normalize_relations,
    )
    from lca.harness.plugin_manifest import EffectClass, PluginKind

    assert _normalize_keys(None) == ()
    assert _normalize_keys(("a.b", "c.d")) == ("a.b", "c.d")
    assert _normalize_implements("MyClass") == ("MyClass",)
    assert _normalize_implements(("a", "b")) == ("a", "b")
    assert _normalize_effects(None) == frozenset({EffectClass.NONE})
    assert _normalize_effects(EffectClass.TOOLS) == frozenset({EffectClass.TOOLS})
    assert _normalize_relations(None) == ()
    # Public PluginKind is reachable via plugin_api; use it for layer/kind.
    assert PluginKind.PRIMITIVE.value == "primitive"
