"""Profile-visible provider for the plan-bound perceive composer."""

from __future__ import annotations

from lca.plugins.composer._provider_factory import _register_composer_plugin
from lca.plugins.composer.perceive.composer import PerceiveComposer

setup, Config = _register_composer_plugin(
    plane_key="perceive",
    plane_noun="perceive",
    interface="context-and-state",
    grants=("context.read",),
    composer_cls=PerceiveComposer,
)

__all__ = ["Config", "setup"]
