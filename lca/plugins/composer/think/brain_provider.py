"""Profile-visible provider for the plan-bound cognitive composer."""

from __future__ import annotations

from lca.plugins.composer._provider_factory import _register_composer_plugin
from lca.plugins.composer.think.brain_composer import BrainComposer

setup, Config = _register_composer_plugin(
    plane_key="brain",
    plane_noun="cognitive",
    interface="think-cluster",
    grants=("plugin.serve",),
    composer_cls=BrainComposer,
)

__all__ = ["Config", "setup"]
