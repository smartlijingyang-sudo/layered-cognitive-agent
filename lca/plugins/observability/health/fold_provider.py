"""``observability.health.fold`` Cordis provider (PR-1 / Task 1.4).

Binds the ``HealthFoldSeam`` callable into the registry under the
``standard`` key. The provider is intentionally a thin shim — it
just forwards to the seam so plugins requesting
``observability.health.fold['standard']`` receive the fold callable.

Full Cordis ``@plugin(...)`` registration is deferred to a follow-up
PR (the existing 8 deriver entry-points and the fold module are the
real source of truth; the Cordis integration is additive and
optional). The skeleton exists so the bundle YAML can name a
provider entry without inventing a placeholder module path.
"""

from __future__ import annotations

from lca.plugins.observability.health.seam_provider import HealthFoldSeam


class HealthFoldStandardProvider:
    """Standard provider for the ``observability.health.fold`` seam.

    Returns the ``HealthFoldSeam`` instance so consumers can call
    ``provider.seam.fold(spine_path)``. Adding a ``null`` provider
    later is a one-file change (mirrors the existing
    ``loop_cursor.null`` pattern).
    """

    def __init__(self) -> None:
        self.seam = HealthFoldSeam()


__all__ = ["HealthFoldStandardProvider"]
