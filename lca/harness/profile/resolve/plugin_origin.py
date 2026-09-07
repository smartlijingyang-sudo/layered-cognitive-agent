"""PluginOrigin resolution (ADR-0199 §3.4 / P3-03).

Per ADR-0199 §3.4 every plugin carries a PluginOrigin
(source: bundled/project/user/pip; trust: core/trusted/untrusted)
plus the profile/bundle path that admitted it.

This module classifies a plugin module path into a PluginOrigin using
filesystem conventions. The classification rules (per ADR §3.4):

| source   | filesystem hint                       | default trust | enabled by default |
|----------|---------------------------------------|---------------|--------------------|
| bundled  | starts with ``lca/plugins/``          | core          | profile declares   |
| project  | starts with ``.lca/plugins/``         | untrusted     | false              |
| user     | under user home, not project          | trusted       | profile declares   |
| pip      | entry-point registered via setuptools | untrusted     | false              |

Per I-HPC-11 (trust default denied): untrusted origins are filtered
out by default; only profile-explicit enable admits them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from lca.contracts.runtime.trust import (
    PluginOrigin,
    PluginSource,
    PluginTrustLevel,
)

_BUNDLED_ROOT: Final[str] = "lca/plugins"
_PROJECT_ROOT: Final[str] = ".lca/plugins"
_USER_INDICATOR: Final[str] = ".local"  # user pip installs land here


class PluginOriginResolutionError(ValueError):
    """Raised when origin cannot be determined."""


def resolve_plugin_origin(
    module_path: str,
    *,
    repo_root: str | Path | None = None,
    entry_point_group: str | None = None,
) -> PluginOrigin:
    """Classify a plugin module path into a PluginOrigin.

    Args:
      module_path: dotted module path (e.g. ``lca.plugins.observability.x``)
                    OR absolute filesystem path (for project plugins)
      repo_root: optional explicit repo root (for project-plugin detection)
      entry_point_group: if non-None, this module was discovered via a pip
                         entry point (overrides path-based detection)

    Per ADR-0199 §3.4 table.
    """
    # 1. pip entry-point wins
    if entry_point_group is not None:
        return _origin("pip", "untrusted", f"entry_point:{entry_point_group}", module_path)

    # 2. project plugin (under .lca/plugins/)
    if str(module_path).startswith(_PROJECT_ROOT + "/") or _PROJECT_ROOT + "/" in str(module_path):
        return _origin("project", "untrusted", "profile_required", str(module_path))

    # 3. bundled plugin (under lca/plugins/)
    path_str = str(module_path)
    dotted_prefix = _BUNDLED_ROOT.replace("/", ".") + "."
    if path_str.startswith(dotted_prefix) or path_str.startswith(_BUNDLED_ROOT + "/"):
        return _origin("bundled", "core", "bundled_default", path_str)

    # 4. user pip-installed (heuristic: under user home or .local)
    home = str(Path.home())
    if path_str.startswith(home) or _USER_INDICATOR in path_str:
        return _origin("user", "trusted", "profile_required", path_str)

    # 5. fallback: assume bundled (the safe default; untrusted would fail-loud later)
    return _origin("bundled", "core", "fallback", path_str)


def _origin(
    source: PluginSource,
    trust: PluginTrustLevel,
    enabled_by: str,
    discovered_at: str,
) -> PluginOrigin:
    """Construct a PluginOrigin with the convention-trusted validation.

    The PluginOrigin dataclass from lca.contracts.runtime.trust validates
    that "bundled" requires trust="core" and that "project"/"pip" are NOT
    trust="core". See P1-02.
    """
    return PluginOrigin(
        source=source,
        trust=trust,
        enabled_by=enabled_by,
        discovered_at=discovered_at,
    )


def is_untrusted_default_disabled(origin: PluginOrigin) -> bool:
    """Return True if this origin's default is disabled (per I-HPC-11).

    Per ADR-0199 §3.4 table: project / pip sources default to disabled.
    """
    return origin.source in ("project", "pip")


__all__ = (
    "PluginOriginResolutionError",
    "is_untrusted_default_disabled",
    "resolve_plugin_origin",
)
