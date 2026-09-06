"""Session append public API (ADR-0195 P1-03).

Production fact append goes through :class:`Session` and its :meth:`~Session.append`.
Implementation remains in ``lca.plugins.session.runtime`` until Wave P4 lift.
"""

from __future__ import annotations

from lca.plugins.session.runtime.session import Session

__all__ = ["Session"]
