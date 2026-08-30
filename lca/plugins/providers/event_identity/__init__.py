"""Event identity providers —— ADR-0096 MVA-2 + ADR-0097.

Plain classes registered into the ``event_identities`` registry at boot.
No ``@plugin`` decorator: the seam owns capability provision.
"""

from lca.plugins.providers.event_identity.stable_ulid import StableUlidIdentity

__all__ = ["StableUlidIdentity"]
