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


class SeamCompletenessError(LoaderError):
    """Seam triangle (Definition/Provider/Consumer) is incomplete."""


class Loader:
    """Topological plugin loader."""

    def __init__(self, *, check_seam_completeness: bool = False) -> None:
        self._check_seam = check_seam_completeness

    async def load(self, entries: list[PluginEntry]) -> BootedTree:
        """Load and activate plugins. Return BootedTree on success."""
        active = [e for e in entries if not e.disabled]
        self._validate_unique_ids(active)

        host = PluginHost()

        # Register all handles
        for entry in active:
            # Preserve original module for manifest reading
            entry._original_module = entry.module
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

        # Seam completeness check (if enabled)
        if self._check_seam:
            self._validate_seam_completeness(active)

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

    # ── Seam completeness ────────────────────────────────

    @staticmethod
    def _validate_seam_completeness(entries: list[PluginEntry]) -> None:
        """Validate seam triangle completeness from PluginManifest declarations.

        Reads the ``manifest`` attribute from each entry's original module.
        Only entries with a ``PluginManifest`` participate in this check.

        Rules:
        - Each DEFINITION must have at least one PROVIDER for its seam_key.
        - PROVIDER/CONSUMER seam_keys must reference a known DEFINITION.
        - DEFINITIONs with no CONSUMER are warned (not errored).
        """
        from lca.contracts.harness.plugin import PluginKind, PluginManifest

        definitions: dict[str, str] = {}  # seam_key → entry_id
        providers: dict[str, list[str]] = {}  # seam_key → [entry_ids]
        consumers: dict[str, list[str]] = {}  # seam_key → [entry_ids]

        for entry in entries:
            mod = entry.module
            # The original module (before _build_spec replaces it) may have manifest
            manifest: PluginManifest | None = getattr(mod, "manifest", None)
            if manifest is None:
                # Also check the original module stored on the entry
                original = getattr(entry, "_original_module", None)
                if original is not None:
                    manifest = getattr(original, "manifest", None)
            if not isinstance(manifest, PluginManifest):
                continue

            for ep in manifest.extension_points:
                definitions[ep.seam_key] = entry.id

            if manifest.kind == PluginKind.DEFINITION and manifest.seam_key:
                definitions[manifest.seam_key] = entry.id
            elif manifest.kind == PluginKind.PROVIDER:
                if manifest.seam_key:
                    providers.setdefault(manifest.seam_key, []).append(entry.id)
                for key in manifest.provides:
                    providers.setdefault(key, []).append(entry.id)
            elif manifest.kind == PluginKind.SERVICE:
                for key in manifest.provides:
                    providers.setdefault(key, []).append(entry.id)
            elif manifest.kind == PluginKind.CONSUMER and manifest.seam_key:
                consumers.setdefault(manifest.seam_key, []).append(entry.id)

        errors: list[str] = []

        # Every DEFINITION must have at least one PROVIDER
        for seam_key, defn_id in definitions.items():
            if seam_key not in providers:
                errors.append(f"Seam '{seam_key}' defined by {defn_id} has no provider")

        # Every PROVIDER must reference a known DEFINITION
        for seam_key, provider_ids in providers.items():
            if seam_key not in definitions:
                errors.append(f"Provider for unknown seam '{seam_key}': {provider_ids}")

        if errors:
            raise SeamCompletenessError(f"seam completeness check failed: {'; '.join(errors)}")

        # Warn about definitions without consumers (not errors)
        import structlog

        log = structlog.get_logger("lca.plugin")
        for seam_key in definitions:
            if seam_key not in consumers:
                log.warning("seam_no_consumer", seam_key=seam_key)

    @staticmethod
    def _check_seam_completeness(handles: list[Any]) -> None:
        """Validate seam triangle completeness from PluginHandle manifests.

        Takes a list of handles with ``manifest`` attribute (PluginManifest).
        Used for direct handle-based validation during reconcile.

        Rules:
        - Each DEFINITION must have at least one PROVIDER for its seam_key.
        - PROVIDER must reference a known DEFINITION.
        - DEFINITIONs with no CONSUMER are warned (not errored).

        Raises:
            SeamCompletenessError: If validation fails.
        """
        from lca.contracts.harness.plugin import PluginKind

        definitions: dict[str, Any] = {}  # seam_key → handle
        providers: dict[str, list[Any]] = {}  # seam_key → [handles]
        consumers: dict[str, list[Any]] = {}  # seam_key → [handles]

        for h in handles:
            m = h.manifest
            if m.kind == PluginKind.DEFINITION and m.seam_key:
                definitions[m.seam_key] = h
            elif m.kind == PluginKind.PROVIDER and m.seam_key:
                providers.setdefault(m.seam_key, []).append(h)
            elif m.kind == PluginKind.CONSUMER and m.seam_key:
                consumers.setdefault(m.seam_key, []).append(h)

        errors: list[str] = []

        # Every DEFINITION must have at least one PROVIDER
        for key, defn in definitions.items():
            if key not in providers:
                errors.append(f"Seam '{key}' defined by {defn.entry_id} has no provider")

        # Every PROVIDER must reference a known DEFINITION
        for key in providers:
            if key not in definitions:
                ids = [h.entry_id for h in providers[key]]
                errors.append(f"Provider for unknown seam '{key}': {ids}")

        if errors:
            raise SeamCompletenessError(
                f"seam completeness check failed: {'; '.join(errors)}"
            )

        # Warn about definitions without consumers (not errors)
        import structlog

        log = structlog.get_logger("lca.plugin")
        for seam_key, defn in definitions.items():
            if seam_key not in consumers:
                log.warning(
                    "seam_no_consumer",
                    seam_key=seam_key,
                    definition=defn.entry_id,
                )

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
