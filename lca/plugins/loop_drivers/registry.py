"""Run-loop driver registry + factory — Tier-3 plugin.

Hosts the driver registry on the ctx. The ``/runs`` HTTP carrier
(``gateway/runs/execute.py``) is a thin caller: it reads the active
driver from ``ctx.require("run_loop_driver_registry")`` and delegates to
``driver.execute(ctx, ...)``.

Profiles swap drivers by enabling/disabling loop plugins. No
module-level singleton.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class RunLoopDriverRegistry:
    """Target → driver registry. Loop plugins fill it at boot."""

    def __init__(self, default: str | None = None) -> None:
        self._drivers: dict[str, object] = {}
        self._materialized: dict[str, object] = {}
        self._default = default

    def register(self, target: str, driver: object) -> None:
        """Register a driver (or a zero-arg factory returning one) for ``target``.

        Duplicate registration fails (ADR-0062 §3).
        """
        key = target.strip().lower()
        if key in self._drivers:
            raise KeyError(f"run_loop_driver_registry: {key!r} already registered")
        self._drivers[key] = driver

    def contains(self, target: str) -> bool:
        """True iff ``target`` names a registered loop driver."""
        return (target or "").strip().lower() in self._drivers

    def resolve(self, target: str) -> object:
        key = target.strip().lower() if target else ""
        if not key:
            key = (self._default or "").strip().lower()
        cached = self._materialized.get(key)
        if cached is not None:
            return cached
        try:
            entry = self._drivers[key]
        except KeyError as exc:
            raise _UnknownExecutionTargetError(target or self._default or "") from exc
        if callable(entry) and (not _looks_like_driver(entry)):
            entry = entry()
        self._materialized[key] = entry
        return entry

    def targets(self) -> tuple[str, ...]:
        return tuple(sorted(self._drivers))


class _UnknownExecutionTargetError(KeyError):
    """Loop plugin missing for the requested execution_target.

    Subclasses ``KeyError`` so plugin-tree omission handlers treat it as a
    missing seam (no driver registered for that key).
    """

    def __init__(self, target: str) -> None:
        super().__init__(target or "")
        self.target = target

    def __str__(self) -> str:
        return (
            f"no run_loop_driver registered for execution_target={self.target!r}; "
            f"enable the corresponding loop plugin in your bundle"
        )


def _looks_like_driver(obj: object) -> bool:
    """Heuristic: a driver exposes ``async execute(...)``."""
    return callable(getattr(obj, "execute", None))


@plugin(
    id="lca-run-loop-driver-registry",
    provides=["run_loop_driver_registry"],
    requires=[],
    implements=[],
    layer="L1",
    effects="none",
    description="Empty run-loop driver registry; loop plugins fill it in.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_empty_execution_target_uses_profile_default",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-run-loop-driver-registry.checked",
                "lca-run-loop-driver-registry.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("run_loop_driver_registry",),
        emits=("run_loop_driver_registry.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: dict[str, Any]) -> None:
    """Provide an empty driver registry; loop plugins fill it in.

    Config shape::

        default: cognitive   # fallback target when request omits one
    """
    default = None
    if isinstance(config, dict):
        default = config.get("default")
    ctx.provide("run_loop_driver_registry", RunLoopDriverRegistry(default=default))
