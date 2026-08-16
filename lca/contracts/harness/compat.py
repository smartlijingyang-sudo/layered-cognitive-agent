"""Legacy adapter — bridge from ``PluginSpec`` to ``PluginManifest``.

Allows existing plugin modules (using the old ``name/inject/apply/provides``
shape) to be loaded by the harness Loader without modification.

Spec reference: §2.2.1 backward-compat of ``docs/specs/harness-spine-spec.md``.
"""

from __future__ import annotations

from lca.contracts.harness.plugin import PluginKind, PluginManifest, ProviderMode
from lca.layer0_infra.plugin.kernel._spec import PluginSpec
from lca.layer0_infra.plugin.loader._entry import PluginEntry
from lca.layer0_infra.plugin.loader._loader import Loader


def manifest_from_spec(spec: PluginSpec, entry_id: str) -> PluginManifest:
    """Convert a legacy ``PluginSpec`` to a ``PluginManifest``.

    The legacy spec has no concept of kind, seam, or middleware —
    it maps to a single PROVIDER plugin at api_version ``lca-harness/0``.
    """
    provides = (spec.provides,) if spec.provides else ()
    return PluginManifest(
        id=entry_id,
        version="0.0.0-legacy",
        api_version="lca-harness/0",
        kind=PluginKind.PROVIDER,
        provides=provides,
        requires=spec.inject,
        provider_mode=ProviderMode.SINGLE,
    )


def manifest_from_entry(entry: PluginEntry) -> PluginManifest:
    """Build a ``PluginManifest`` from a resolved ``PluginEntry``.

    Uses ``Loader._build_spec()`` to extract the legacy spec from the module,
    then converts via ``manifest_from_spec()``.
    """
    spec = Loader._build_spec(entry)
    return manifest_from_spec(spec, entry.id)
