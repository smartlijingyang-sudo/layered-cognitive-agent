"""Profile snapshot providers —— ADR-0096 MVA-3.

Plain classes registered into the ``profile_snapshots`` registry at boot.
No ``@plugin`` decorator: the seam owns capability provision.
"""

from lca.plugins.providers.profile_snapshot.run_boot import RunBootSnapshot

__all__ = ["RunBootSnapshot"]
