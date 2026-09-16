"""``observability.health.fold`` Cordis seam (PR-1 / Task 1.4).

Declares the ``observability.health.fold`` capability surface so
plugins can request the fold function without importing
``lca.plugins.observability.health.run_health_fold`` directly. The
seam is intentionally thin: it does not own the deriver registry
(the ``lca.health_derivers`` entry-point group does) and does not
load any specific deriver at boot. The fold is pure, so the seam
just exposes a callable that takes a spine path and returns a
``RunHealthReport``.

The actual Cordis registration (seam class + ``@plugin(...)``
decorator) is intentionally minimal here — full wiring happens in
a follow-up PR once the consuming plugins stabilise. The skeleton
exists so the bundle YAML can name the seam entry without
inventing a placeholder module path at import time.
"""

from __future__ import annotations


class HealthFoldSeam:
    """Seam exposing the ``fold_run_health`` callable.

    The seam does not register specific derivers; the fold
    function in ``run_health_fold.py`` discovers derivers via
    ``importlib.metadata.entry_points`` at import time. The seam
    just provides a stable import surface so plugins can
    ``require=["observability.health.fold"]`` and receive the
    fold callable at boot.
    """

    def __init__(self) -> None:
        from lca.plugins.observability.health.run_health_fold import (
            fold_run_health,
        )

        self._fold = fold_run_health

    def fold(self, spine_path):  # type: ignore[no-untyped-def]
        """Return the underlying ``fold_run_health`` callable result."""
        return self._fold(spine_path)


__all__ = ["HealthFoldSeam"]
