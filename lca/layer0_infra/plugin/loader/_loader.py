"""Loader — topological plugin loading with failure semantics.

Responsibilities:
- Take resolved ``list[PluginEntry]`` (modules already imported)
- Validate shapes (name/inject/apply/provides/Config)
- Detect duplicate ids, duplicate provides, cycles
- Drive ``reconcile()`` until all activatable plugins are ACTIVE
- Return ``BootedTree`` with host + entries + disposers

NO YAML parsing. NO module importing. Those belong to ``include/``.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from lca.layer0_infra.plugin.kernel import (
    PluginConfig,
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
    reconcile,
)
from lca.layer0_infra.plugin.loader._entry import BootedTree, PluginEntry


class LoaderError(RuntimeError):
    """Loading failure: config, shape, cycle, or unmet dependency."""


class Loader:
    """Topological plugin loader."""

    async def load(self, entries: list[PluginEntry]) -> BootedTree:
        """Load and activate plugins. Return BootedTree on success."""
        active = [e for e in entries if not e.disabled]
        self._validate_unique_ids(active)

        host = PluginHost()

        # Register all handles
        for entry in active:
            spec = self._build_spec(entry)
            injected = self._resolve_inject(entry, spec)
            # Pre-validate config so failures are LoaderError, not lifecycle FAILED
            if spec.validate is not None:
                spec.validate(entry.config)
            handle = PluginHandle(
                entry_id=entry.id,
                spec=spec,
                config=entry.config,
                injected=injected,
            )
            entry.module = spec  # keep resolved spec for diagnostics
            host.register_handle(handle)

        # Validate provides uniqueness
        self._validate_provides(active, host)

        # Drive convergence
        await reconcile(host)

        # Check for unsatisfied plugins
        self._check_failures(host, active)

        # Build disposer list (one per activated plugin)
        disposers: list[tuple[str, Any]] = []
        for entry in active:
            handle = host.handles.get(entry.id)
            if handle is not None and handle.state is PluginState.ACTIVE:
                disposers.append((entry.id, lambda h=handle: None))

        return BootedTree(host=host, entries=active, _disposers=disposers)

    # ── Validation ────────────────────────────────────────

    @staticmethod
    def _validate_unique_ids(entries: list[PluginEntry]) -> None:
        seen: set[str] = set()
        for entry in entries:
            if entry.id in seen:
                raise LoaderError(f"duplicate plugin id: {entry.id!r}")
            seen.add(entry.id)

    @staticmethod
    def _validate_provides(entries: list[PluginEntry], host: PluginHost) -> None:
        provides_map: dict[str, str] = {}
        for entry in entries:
            spec = _get_spec(entry)
            if spec.provides is not None:
                key = spec.provides
                if key in provides_map:
                    raise LoaderError(
                        f"plugin {entry.id!r} and {provides_map[key]!r} both provide {key!r}"
                    )
                provides_map[key] = entry.id

    @staticmethod
    def _check_failures(host: PluginHost, entries: list[PluginEntry]) -> None:
        """After reconcile: detect unmet deps and cycles."""
        provides_map: dict[str, str] = {}
        for entry in entries:
            spec = _get_spec(entry)
            if spec.provides is not None:
                provides_map[spec.provides] = entry.id

        missing: list[str] = []
        cycle_ids: list[str] = []
        for entry in entries:
            handle = host.handles.get(entry.id)
            if handle is None:
                continue
            if handle.state is PluginState.ACTIVE:
                continue
            if handle.state is PluginState.FAILED:
                # Already reported during activate(); skip
                continue
            spec = _get_spec(entry)
            unmet = [k for k in handle.dependencies if k not in provides_map]
            if unmet:
                missing.append(f"{entry.id} missing {unmet}")
            else:
                cycle_ids.append(entry.id)

        if missing:
            raise LoaderError(f"unmet plugin inject: {'; '.join(missing)}")
        if cycle_ids:
            raise LoaderError(f"plugin cycle detected: {cycle_ids}")

    # ── Spec building ─────────────────────────────────────

    @staticmethod
    def _build_spec(entry: PluginEntry) -> PluginSpec:
        """Build PluginSpec from entry's module."""
        mod = entry.module
        if isinstance(mod, PluginSpec):
            return mod
        # Module shape: read attributes
        for attr in ("name", "apply"):
            if not hasattr(mod, attr):
                raise LoaderError(f"plugin {entry.id!r} module missing {attr!r}")
        name = getattr(mod, "name", entry.id)
        inject_raw = getattr(mod, "inject", ())
        inject = tuple(inject_raw.keys()) if isinstance(inject_raw, dict) else tuple(inject_raw)
        provides = getattr(mod, "provides", None)
        config_cls = getattr(mod, "Config", PluginConfig)
        apply_fn = mod.apply
        is_class = isinstance(mod, type)

        def validate(raw: Any) -> Any:
            if isinstance(raw, config_cls):
                return raw
            try:
                return config_cls(**(raw or {}))
            except ValidationError as exc:
                raise LoaderError(
                    f"plugin {entry.id!r} config validation failed: {exc.errors()}"
                ) from exc

        return PluginSpec(
            name=name,
            apply=apply_fn,
            inject=inject,
            provides=provides,
            validate=validate,
            is_class=is_class,
        )

    @staticmethod
    def _resolve_inject(entry: PluginEntry, spec: PluginSpec) -> tuple[str, ...]:
        """Resolve inject: entry override > spec inject."""
        if entry.inject is not None:
            return (
                tuple(entry.inject.keys())
                if isinstance(entry.inject, dict)
                else tuple(entry.inject)
            )
        return spec.inject


def _get_spec(entry: PluginEntry) -> PluginSpec:
    """Get the PluginSpec from an entry (stored in module after build)."""
    mod = entry.module
    if isinstance(mod, PluginSpec):
        return mod
    # Fallback: build on the fly
    return Loader._build_spec(entry)
