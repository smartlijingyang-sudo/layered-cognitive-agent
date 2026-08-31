"""RunModeRegistry seam plugin — Tier-1 (ADR-0076 §六).

Defines the ``run_mode_registry`` capability that maps an OpenAI model id
(``"solo"``, ``"team"``, ``"cordis-creator"``, future ``"research"`` /
``"code"`` variants) to a mode adapter — the runtime object graph that
turns a request into an ``Agent`` or ``Team``.

The previous ``gateway/modes.py:resolve_lca_mode()`` performed string
``if/elif`` dispatch on the model id; the substitution test
(``tests/architecture/test_substitution_gates.py``) flagged this as a
violation of ADR-0076 §二.  This seam replaces that branch with a
registry lookup: each mode is a ``ModeAdapter`` plugin, and the gateway
calls :meth:`RunModeRegistry.resolve` instead of comparing strings.

Public surface:

- :class:`ModeAdapter` — Protocol declaring the per-mode contract
  (``key``, ``role``, ``matches(model)``, ``build(request)``).
- :class:`RunModeRegistry` — registry that mode-adapter plugins fill at
  boot and the gateway consults at request time.

The Tier-1 plugin registers an empty registry on the ctx; the default
adapters (``solo`` / ``team`` / ``cordis-creator``) are provided by the
Gateway-owned :mod:`gateway.plugins.default_modes` L4 composition plugin.
Production profiles replace individual adapters by enabling alternative carrier
mode plugins; the registry seam and generic assembler never see the change.

The :class:`ModeAdapter` Protocol keeps ``build`` loosely typed because
the seam lives in :mod:`lca.plugins` (no ``gateway`` import allowed);
concrete carrier adapters and alternative production plugins cast their
own assembly inputs to the runtime types.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import RUN_MODE_REGISTRY
from lca.contracts.protocols.session.run_mode import (
    ModeAdapter,
    RegisteredMode,
    RunModeRegistryProtocol,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class RunModeRegistry(RunModeRegistryProtocol):
    """Model id → :class:`ModeAdapter` registry.

    Mode-adapter plugins fill this at boot via :meth:`register`.  The
    gateway resolves a request's model id to the owning adapter through
    :meth:`resolve`, which iterates registered adapters in registration
    order and returns the first whose :meth:`ModeAdapter.matches` returns
    True.  When no adapter matches, :meth:`resolve` falls back to
    :meth:`set_default` (or the adapter registered under
    :data:`DEFAULT_MODE_KEY`).
    """

    DEFAULT_MODE_KEY: str = "solo"

    def __init__(self) -> None:
        self._adapters: dict[str, ModeAdapter] = {}
        self._order: list[str] = []
        self._default_key: str | None = None

    def register(self, adapter: ModeAdapter) -> None:
        """Register ``adapter`` under its :attr:`ModeAdapter.key`.

        Duplicate keys raise :class:`KeyError` so profile boot fails
        closed (ADR-0062 §3).
        """

        key = adapter.key
        if key in self._adapters:
            raise KeyError(f"run_mode_registry: mode {key!r} already registered")
        self._adapters[key] = adapter
        self._order.append(key)

    def set_default(self, key: str) -> None:
        """Configure the fallback adapter key for unmatched model ids."""

        if key not in self._adapters:
            raise KeyError(
                f"run_mode_registry: cannot set default to {key!r}; register the adapter first"
            )
        self._default_key = key

    def resolve(self, model: str) -> ModeAdapter:
        """Map ``model`` to a :class:`ModeAdapter`.

        Whitespace is stripped and lower-cased before matching.  When no
        adapter matches, the configured default is returned; if no
        default was configured, the adapter registered under
        :data:`DEFAULT_MODE_KEY` is returned.
        """

        candidate = (model or "").strip().lower()
        for key in self._order:
            adapter = self._adapters[key]
            if adapter.matches(candidate):
                return adapter
        fallback_key = self._default_key or self.DEFAULT_MODE_KEY
        if fallback_key not in self._adapters:
            raise LookupError(
                f"run_mode_registry: no adapter matched {model!r} and no default is registered"
            )
        return self._adapters[fallback_key]

    def registered(self) -> tuple[RegisteredMode, ...]:
        """Snapshot of all registered modes, in registration order."""

        return tuple(
            RegisteredMode(key=key, role=self._adapters[key].role, adapter=self._adapters[key])
            for key in self._order
        )

    def __contains__(self, key: str) -> bool:
        return key in self._adapters


@plugin(
    id="lca-run-mode-registry-seam",
    provides=[RUN_MODE_REGISTRY.key],
    requires=[],
    implements=[RunModeRegistryProtocol],
    layer="L1",
    effects="none",
    description="Provide the run_mode_registry capability for ADR-0076 §六.",
    test_suite="tests/architecture/test_run_mode_registry.py::test_seam_provides_empty_registry",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-run-mode-registry-seam.checked', 'lca-run-mode-registry-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Mount an empty :class:`RunModeRegistry` on the ctx.

    Default mode adapters (solo / team / cordis-creator) are filled by
    the Gateway-owned ``gateway.plugins.default_modes`` composition plugin,
    whose manifest requires this seam.
    """

    del config
    ctx.provide(RUN_MODE_REGISTRY.key, RunModeRegistry())


__all__ = [
    "Config",
    "ModeAdapter",
    "RegisteredMode",
    "RunModeRegistry",
    "setup",
]
