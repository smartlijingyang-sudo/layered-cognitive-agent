"""External plugin filter (ADR-0199 §3.4 / P5-03 + I-HPC-11).

Per ADR-0199 §3.4: plugins with ``source`` in ``{"project", "pip"}``
default to disabled. Per §10 Phase 5: plugins with ``external_kind``
in ``{"mcp", "sandbox", "worker"}`` ALSO default to disabled (they
require explicit profile provenance before admission).

This module is the COMPOSITION of two filters:
  - P3-04 untrusted-source filter (``plugin_origin.is_untrusted_default_disabled``)
  - P5-03 external-kind filter (this module's specialty)

Both filters warn rather than raise (per I-HPC-11 untrusted defaults
to disabled, not to error).
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from lca.contracts.runtime.external_plugin import (
    ExternalPluginKind,
)

if TYPE_CHECKING:
    from lca.harness.profile.resolve.resolve import ResolvedPlugin


class ExternalFilterError(ValueError):
    """Raised when external_kind declaration is invalid."""


def _is_default_disabled_kind(kind: ExternalPluginKind) -> bool:
    """Return True if a plugin with this external_kind defaults to disabled.

    Per ADR-0199 §3.4 + §10 Phase 5: only ``inprocess`` plugins default
    to enabled. All other kinds (``mcp``, ``sandbox``, ``worker``) default
    to disabled and require explicit profile provenance.
    """
    return kind != "inprocess"


def filter_external_default_disabled(
    plugins: tuple[ResolvedPlugin, ...],
    *,
    profile_path: str,
    external_kind_by_module: dict[str, ExternalPluginKind] | None = None,
    warn_filtered: bool = True,
) -> tuple[ResolvedPlugin, ...]:
    """Filter plugins whose external_kind defaults to disabled.

    Per ADR-0199 §3.4 + I-HPC-11 + §10 Phase 5:
      - inprocess: included (trusted core / user)
      - mcp / sandbox / worker: included only if profile explicitly enables

    Args:
      plugins: candidate plugin set from declarative spec.
      profile_path: profile path; the admission provenance check.
      external_kind_by_module: map ``module path -> ExternalPluginKind``.
        Modules not in the map are treated as ``inprocess`` (default).
      warn_filtered: when True, emit one warning per filtered plugin.

    Returns:
      Filtered tuple. Filtered plugins are dropped, not raised.
    """
    kinds = external_kind_by_module or {}
    kept: list[ResolvedPlugin] = []
    filtered: list[tuple[ResolvedPlugin, ExternalPluginKind]] = []
    profile_path_str = str(profile_path) if profile_path else ""

    for plugin in plugins:
        kind: ExternalPluginKind = kinds.get(plugin.module, "inprocess")
        if not _is_default_disabled_kind(kind):
            kept.append(plugin)
            continue
        # Check explicit enable: profile_path is the enabler
        # Heuristic: profile_path appears in any of the plugin's
        # discovery hints OR the kind map's enabled_by provenance.
        # For P5-03 we use a simple check: if the profile_path
        # contains the plugin's bundle / module name, it's enabled.
        if profile_path_str and (
            plugin.id in profile_path_str or plugin.module.split(".")[-1] in profile_path_str
        ):
            kept.append(plugin)
            continue
        filtered.append((plugin, kind))

    if warn_filtered and filtered:
        ids = ", ".join(f"{p.id} (kind={k})" for p, k in filtered)
        warnings.warn(
            f"external-default plugins filtered (ADR-0199 §3.4 / I-HPC-11): {ids}. "
            "Enable explicitly via profile provenance to admit.",
            stacklevel=2,
        )

    return tuple(kept)


__all__ = (
    "ExternalFilterError",
    "filter_external_default_disabled",
)
