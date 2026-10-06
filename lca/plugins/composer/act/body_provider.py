"""Profile-visible provider for the plan-bound execution composer."""

from __future__ import annotations

from lca.plugins.composer._provider_factory import _register_composer_plugin
from lca.plugins.composer.act.body_composer import BodyComposer

setup, Config = _register_composer_plugin(
    plane_key="body",
    plane_noun="execution",
    interface="act-cluster",
    grants=("plugin.serve",),
    composer_cls=BodyComposer,
)

__all__ = ["Config", "setup"]
