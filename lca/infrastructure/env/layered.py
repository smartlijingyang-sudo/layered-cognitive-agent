"""Layered env filter — pure function, no IO side effects.

Implements the deepseek BOOTSTRAP model adapted to Python + LCA (ADR-0117
§决定 4). The kernel facade :func:`lca_kernel.env.load_layered_env` reads
``.env`` from disk and delegates filtering here; this module stays IO-free
so it can be unit-tested without filesystem fixtures.

Rules (抄 deepseek app-boot/src/index.ts:loadLayeredEnv):

1. ``.env`` may *override* a key in :data:`BOOTSTRAP_NAMES` only when the key
   is already present in ``ambient`` (no surprise new values for bootstrap
   names — the process inherits, the file confirms).
2. ``.env`` may *introduce* a key matching any :data:`BOOTSTRAP_PREFIXES`
   prefix even when it is not yet in ``ambient`` (LCA configuration normally
   is opt-in per deployment). The prefix path also accepts overriding an
   existing ambient value.
3. :data:`BOOTSTRAP_FORBIDDEN` entries are always rejected — they must
   come from argv / profile / secret resolver, never from ``.env``.
4. Any other key is rejected. Callers can opt into permissive mode via
   ``allow_unknown=True`` (used by tests / one-off debug profiles), but the
   production facade :func:`lca_kernel.env.load_layered_env` defaults to
   fail-loud.

The function is intentionally side-effect-free and operates on
:class:`collections.abc.Mapping` inputs only; the kernel layer handles
``.env`` parsing and the actual ``os.environ`` snapshotting.
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.infrastructure.env.bootstrap import (
    BOOTSTRAP_FORBIDDEN,
    BOOTSTRAP_NAMES,
    BOOTSTRAP_PREFIXES,
)


def filter_env_keys(
    raw_env: Mapping[str, str],
    ambient: Mapping[str, str],
) -> tuple[frozenset[str], frozenset[str]]:
    """Partition ``raw_env`` into allowed/blocked keys per the deepseek model.

    Parameters
    ----------
    raw_env:
        Parsed ``.env`` entries (key → value). Order does not matter.
    ambient:
        The ambient environment (``os.environ`` snapshot at boot). Used to
        decide whether a BOOTSTRAP_NAMES key may be overridden.

    Returns
    -------
    (allowed_keys, blocked_keys)
        Two disjoint frozensets partitioning ``raw_env.keys()``.

    Rules
    -----
    1. :data:`BOOTSTRAP_FORBIDDEN` entries → blocked.
    2. :data:`BOOTSTRAP_NAMES` entry that exists in ``ambient`` → allowed.
    3. :data:`BOOTSTRAP_NAMES` entry missing from ``ambient`` → blocked
       (no surprise new bootstrap values).
    4. Any key matching a :data:`BOOTSTRAP_PREFIXES` prefix → allowed
       (introducing new keys for an LCA-managed prefix is fine).
    5. Anything else → blocked.

    The blocked set is the diagnosis surface for :func:`lca_kernel.env.load_layered_env`
    when ``allow_unknown=False``: the kernel raises ``KernelError`` listing
    every blocked key so misconfigured ``.env`` files fail loud at boot.
    """
    allowed: set[str] = set()
    blocked: set[str] = set()
    for key in raw_env:
        if key in BOOTSTRAP_FORBIDDEN:
            blocked.add(key)
            continue
        if key in BOOTSTRAP_NAMES:
            if key in ambient:
                allowed.add(key)
            else:
                blocked.add(key)
            continue
        if any(key.startswith(prefix) for prefix in BOOTSTRAP_PREFIXES):
            # Prefix match: always allowed (both ambient-present override
            # and ambient-absent introduction are legitimate configuration).
            allowed.add(key)
            continue
        blocked.add(key)
    return frozenset(allowed), frozenset(blocked)


__all__ = ["filter_env_keys"]
