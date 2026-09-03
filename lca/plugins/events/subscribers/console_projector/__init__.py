"""Console projector subscriber plugin 包（ADR-0180 / plugin-universe PR-4）。

PR-4 可见性：本 ``__init__.py`` re-export ``setup_console_projector`` 为 ``setup``，
使 ``bundles/event-bus-components.yaml`` 的 ``$module: lca.plugins.events.subscribers.console_projector``
能被 profile resolver 经 ``getattr(module, "setup")`` 取到 plugin Manifest。
"""
from lca.plugins.events.subscribers.console_projector.manifest import (
    setup as setup,
)
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)

__all__ = ["ConsoleProjectorSubscriber", "setup"]
