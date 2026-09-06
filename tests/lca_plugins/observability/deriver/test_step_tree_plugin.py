"""observability.deriver.step_tree pilot plugin tests (ADR-0195 P2-18)."""

from __future__ import annotations

from lca.harness.plugin.declaration import definition_from_plugin
from lca.plugins.observability.deriver.step_tree import plugin as step_tree_plugin
from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver, derive_step_tree


def test_step_tree_plugin_manifest() -> None:
    definition = definition_from_plugin(step_tree_plugin.setup, module=__name__)
    assert definition.id == "observability.deriver.step_tree"
    assert "deriver.step_tree" in tuple(definition.provided_capability_keys)


def test_step_tree_capability_surfaces_fold_deriver() -> None:
    cap = step_tree_plugin.StepTreeDeriverCapability(
        deriver_cls=StepTreeFoldDeriver,
        derive_fn=derive_step_tree,
    )
    assert cap.deriver_cls is StepTreeFoldDeriver
    assert cap.derive_fn is derive_step_tree
