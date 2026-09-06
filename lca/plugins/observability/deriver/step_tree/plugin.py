"""observability.deriver.step_tree — fold deriver pilot (ADR-0195 §2.3 O7).

Production step_tree uses :class:`StepTreeFoldDeriver` (Session snapshot /
spine ledger single-stream fold). This plugin is the observability-chain
packaging point; fold logic remains in ``plugins/session/derivers/step_tree/``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver, derive_step_tree


@dataclass(frozen=True, slots=True)
class StepTreeDeriverCapability:
    """Fold deriver factory surface for profile / transport assembly."""

    deriver_cls: type[StepTreeFoldDeriver]
    derive_fn: Callable[..., Any]


@plugin(
    id="observability.deriver.step_tree",
    provides=("deriver.step_tree",),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="filesystem",
    description=("Step tree fold deriver — Session/spine events → JournalDocument / journal.json."),
    test_suite="tests.lca_plugins.observability.deriver.test_step_tree_plugin",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    del config
    ctx.provide(
        "deriver.step_tree",
        StepTreeDeriverCapability(
            deriver_cls=StepTreeFoldDeriver,
            derive_fn=derive_step_tree,
        ),
    )


__all__ = ["StepTreeDeriverCapability", "setup"]
