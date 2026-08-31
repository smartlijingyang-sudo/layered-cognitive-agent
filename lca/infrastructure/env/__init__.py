"""lca/infrastructure/env — BOOTSTRAP whitelist + layered env filter (K7).

This package implements ADR-0115 §决定 1 K7 + ADR-0117 §决定 4 — the
``.env`` bootstrap safety net that prevents ``.env`` from injecting new
ambient keys (surprise new bootstrap names) or overriding security-critical
configuration (forbidden list). It is consumed by the kernel facade
:func:`lca_kernel.env.load_layered_env`.

Architecture
------------

The package is split across two modules so the constants stay pure and the
filter stays IO-free:

- :mod:`lca.infrastructure.env.bootstrap` — three frozenset / tuple
  constants; no ``os`` / ``sys`` / ``dotenv`` import (verified by PR-1 gate).
- :mod:`lca.infrastructure.env.layered` — :func:`filter_env_keys` pure
  function; takes two :class:`collections.abc.Mapping` inputs and returns
  two disjoint frozensets.

The kernel facade ``lca-kernel/env.py`` is the only place where ``.env`` is
actually read and ``os.environ`` is snapshotted; it then delegates the
filtering decision to :func:`filter_env_keys`.

Public API
----------

- :data:`BOOTSTRAP_NAMES`
- :data:`BOOTSTRAP_PREFIXES`
- :data:`BOOTSTRAP_FORBIDDEN`
- :func:`filter_env_keys`
"""

from lca.infrastructure.env.bootstrap import (
    BOOTSTRAP_FORBIDDEN,
    BOOTSTRAP_NAMES,
    BOOTSTRAP_PREFIXES,
)
from lca.infrastructure.env.layered import filter_env_keys

__all__ = [
    "BOOTSTRAP_FORBIDDEN",
    "BOOTSTRAP_NAMES",
    "BOOTSTRAP_PREFIXES",
    "filter_env_keys",
]
