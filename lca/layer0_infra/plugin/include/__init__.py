"""Include sub-package — YAML profile composition.

Depends on: ``loader/`` (PluginEntry)
Depended by: integration layer (``capability_boot.py``, gateway)

Public API:
    from lca.layer0_infra.plugin.include import (
        ProfileLoader, ProfileError,
        expand_profile, compose_bundles,
    )
"""

from lca.layer0_infra.plugin.include._profile import (
    ProfileError,
    ProfileLoader,
    compose_bundles,
    expand_profile,
)

__all__ = [
    "ProfileError",
    "ProfileLoader",
    "compose_bundles",
    "expand_profile",
]
