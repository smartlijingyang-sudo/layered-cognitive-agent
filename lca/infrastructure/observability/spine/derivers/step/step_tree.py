"""COMPAT fold deriver re-export (ADR-0195 O7 / P2-20).

Production fold deriver is packaged as ``observability.deriver.step_tree`` plugin.
Infra callers/tests may import from here during migration; new code should use
the plugin capability key ``deriver.step_tree``.

# COMPAT(owner: ADR-0195 O7, from: infra step_tree_accumulator callback path,
# to: plugins/observability/deriver/step_tree/,
# delete_when: rg "infrastructure.observability.spine.derivers.step_tree" lca/ = 0,
# forbidden_new_usage: 新增 fold 逻辑不得写在本模块)
"""

from lca.plugins.observability.deriver.step_tree.plugin import StepTreeDeriverCapability
from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver, derive_step_tree

__all__ = [
    "StepTreeDeriverCapability",
    "StepTreeFoldDeriver",
    "derive_step_tree",
]
