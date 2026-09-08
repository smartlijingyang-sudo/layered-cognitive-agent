"""LCA plugin loader for the agent_lab hook registry.

PR-A.3 — switch the agent_lab runner/compiler plugin-resolution path
from ``agent_lab.plugins.base.{discover,resolve_plugin,register_*}``
to ``lca.plugins.lab.*`` @plugin carriers.

Why this module exists
----------------------
After PR-A.1 the hook handler behaviour is still hosted by
``agent_lab.plugins.events.EventSinkPlugin`` (and friends) — these are
``GraphPlugin`` subclasses. After PR-A.1 there is also an LCA @plugin
carrier at ``lca.plugins.lab.events.plugin`` whose ``setup()`` builds
one ``EventSinkPlugin`` instance and stashes it on the module-level
``_LAB_HOOKS`` dict (one slot per @plugin id, e.g. ``"lab.hook.events"``).

This loader is the **single seam** between LCA's @plugin world and
the lab hook fanout world:

  load_all()                 — import every ``lca.plugins.lab.*``
                                ``@plugin`` module so each setup()
                                populates its slot in _LAB_HOOKS.
                                Idempotent.
  get_instance(slot_id)      — return the live handler instance for a
                                slot id (or None).
  resolve_plugin(ref)        — map an InfoEdgeSpec PluginRef to the
                                handler instance via the spec ref id.
                                Falls back to a warn-and-skip rather
                                than silently auto-instantiating an
                                unconfigured handler.
  list_ids()                 — the closed set of populated slot ids
                                (used by tests + audit).

The loader is process-local: there is no Cordis Context or module
discovery step. ``load_all()`` is called explicitly at the entry
points (infoedge RunLoopDriver.execute, ``python -m agent_lab.run``,
and tests) so the loading order matches the @plugin graph.

Cross-references
----------------
* ADR-0209 §1.1 (unique plugin entry) / §1.7 (deletion list).
* spec §B.1 PR-A.3 ("engine contract change: graph/compile.py +
  runtime/runner.py use the LCA plugin closure; the GraphPlugin
  registration surface is removed").
* Note ``2026-09-08-agent-lab-absorb-end-state`` (final-stage
  dual-mount absorbs the run_loop_driver into the production tree;
  this loader is consumed by both the prototype and the production
  paths until that final absorb lands).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

_log = logging.getLogger(__name__)

# Single source of truth for the lab hook fan-out.
# Populated by ``load_all()`` calling each ``lca.plugins.lab.*.setup()``.
_LAB_HOOKS: dict[str, Any] = {}

# Lazy-load guard — load_all() is idempotent but cheap to skip.
_LOADED: bool = False

# The set of ``lca.plugins.lab`` subpackages that own @plugin carriers.
# PR-A.3 ships only the hook handlers; PR-B adds act.* workers + providers;
# PR-D will add the remaining 92 nodes.
# Each entry is the full module path (package + .plugin submodule).
_HOOK_PACKAGES: tuple[str, ...] = (
    # PR-A.3 — hook handlers
    "lca.plugins.lab.events.plugin",
    "lca.plugins.lab.observers.plugin",
    "lca.plugins.lab.parsers.plugin",
    "lca.plugins.lab.semantic_router.plugin",
    "lca.plugins.lab.control_slots.plugin",
    "lca.plugins.lab.observation.plugin",
    "lca.plugins.lab.memory_extract.plugin",
    "lca.plugins.lab.tool_guard.plugin",
    "lca.plugins.lab.session_log_emitter.plugin",
    # PR-B — act phase worker nodes (4 + body_provider)
    "lca.plugins.lab.act.shape.plugin",
    "lca.plugins.lab.act.authorize.plugin",
    "lca.plugins.lab.act.execute.plugin",
    "lca.plugins.lab.act.observe.plugin",
    "lca.plugins.lab.act.body_provider.plugin",
    "lca.plugins.lab.tools.provider.plugin",
    "lca.plugins.lab.transport.provider.plugin",
)


def load_all() -> None:
    """Import every LCA lab @plugin carrier and let it populate _LAB_HOOKS.

    Idempotent: subsequent calls are no-ops. Failures are logged at WARNING
    level and do not raise — a missing plugin is treated the same way as
    the previous ``resolve_plugin`` path did (warn-and-skip).
    """
    global _LOADED
    if _LOADED:
        return
    for module_name in _HOOK_PACKAGES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - import failures
            _log.warning("lab hook loader: %s import failed: %s", module_name, exc)
    _LOADED = True


def reset_for_tests() -> None:
    """Test-only — clear the loader state so each test starts clean."""
    global _LOADED
    import sys
    
    # Remove the hook packages from sys.modules so they get re-imported
    for module_name in _HOOK_PACKAGES:
        if module_name in sys.modules:
            del sys.modules[module_name]
    
    _LAB_HOOKS.clear()
    _LOADED = False


def get_instance(slot_id: str) -> Any | None:
    """Return the live handler instance for ``slot_id`` or None."""
    return _LAB_HOOKS.get(slot_id)


def list_ids() -> tuple[str, ...]:
    """Return the closed set of currently populated slot ids."""
    return tuple(sorted(_LAB_HOOKS.keys()))


def resolve_plugin(ref: Any) -> Any | None:
    """Map a PluginRef (or any object with .id / .kind) to a handler.

    Resolution order:
      1. instance registry by ``ref.id`` (the LCA @plugin slot id)
      2. miss → warn and return None (do not silently auto-instantiate)

    Compared to the previous ``agent_lab.plugins.resolve_plugin`` this
    intentionally drops the ``register_plugin`` + ``register_instance``
    fallback chain: there is exactly one entry point (LCA @plugin
    setup()) and one registry (``_LAB_HOOKS``). Spec-level plugin
    references must use a slot id registered by an @plugin.
    """
    rid = getattr(ref, "id", None)
    if rid and rid in _LAB_HOOKS:
        return _LAB_HOOKS[rid]
    kind = getattr(ref, "kind", None)
    _log.warning(
        "lab loader: cannot resolve plugin ref id=%r kind=%r (available=%s)",
        rid,
        kind,
        list_ids(),
    )
    return None


def known_subpackages() -> tuple[str, ...]:
    """Diagnostic — the loader's package allow-list (PR-A.3 only carries
    the 9 hook carrier packages; PR-B/PR-D extend this tuple)."""
    return _HOOK_PACKAGES


def registered_lca_packages() -> tuple[str, ...]:
    """Diagnostic — every ``lca.plugins.lab.*`` package (or nested package)
    that exists on disk under the LCA plugin namespace. Used by tests
    to detect drift between the loader allow-list and the filesystem layout.
    """
    import lca.plugins.lab as _pkg
    import pathlib

    found: set[str] = set()

    def _walk(pkg_path, prefix):
        for entry in pkg_path.iterdir():
            if entry.name.startswith("_") or not entry.is_dir():
                continue
            if (entry / "__init__.py").exists():
                found.add(f"{prefix}.{entry.name}")
                _walk(entry, f"{prefix}.{entry.name}")

    _walk(pathlib.Path(_pkg.__path__[0]), "lca.plugins.lab")
    return tuple(sorted(found))


__all__ = [
    "get_instance",
    "known_subpackages",
    "list_ids",
    "load_all",
    "registered_lca_packages",
    "resolve_plugin",
    "reset_for_tests",
]