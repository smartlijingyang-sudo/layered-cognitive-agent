"""Plugin kernel — self-contained plugin runtime.

Mirrors DSH ``vendor/cordis/``: types, EventBus, Fiber, Context,
Service, lifecycle driver. Zero LCA framework imports.

Public API (re-exported for convenience)::

    from lca.layer0_infra.plugin.kernel import (
        PluginHost, PluginContext, PluginState,
        reconcile, activate, deactivate, Service,
    )
"""

from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._disposable import DisposableList
from lca.layer0_infra.plugin.kernel._effect_meta import EffectMeta
from lca.layer0_infra.plugin.kernel._events import EventBus
from lca.layer0_infra.plugin.kernel._handle import PluginHandle
from lca.layer0_infra.plugin.kernel._host import PluginHost
from lca.layer0_infra.plugin.kernel._lifecycle import (
    activate,
    deactivate,
    reconcile,
    shutdown,
    update_config,
)
from lca.layer0_infra.plugin.kernel._service import Service
from lca.layer0_infra.plugin.kernel._service_record import ServiceRecord
from lca.layer0_infra.plugin.kernel._spec import PluginSpec
from lca.layer0_infra.plugin.kernel._types import (
    Cleanup,
    DependencyUnavailable,
    Effect,
    Listener,
    PluginConfig,
    PluginError,
    PluginState,
    is_bailed,
)

__all__ = [
    "Cleanup",
    "DependencyUnavailable",
    "DisposableList",
    "Effect",
    "EffectMeta",
    "EventBus",
    "Listener",
    "PluginConfig",
    "PluginContext",
    "PluginError",
    "PluginHandle",
    "PluginHost",
    "PluginSpec",
    "PluginState",
    "Service",
    "ServiceRecord",
    "activate",
    "deactivate",
    "is_bailed",
    "reconcile",
    "shutdown",
    "update_config",
]
