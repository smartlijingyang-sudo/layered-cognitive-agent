"""Contract-layer exception hierarchy.

This module centralizes exceptions raised by ``lca/contracts`` modules when a
typed Contract (dataclass, enum, or closed-set literal) is violated at
construction time. It MUST stay dependency-free (no imports from
``lca.infrastructure``, ``lca.cognition``, ``lca.runtime``, ``lca_kernel``)
per ADR-0015 + AGENTS.md §2.1 layer rule — contracts layer is leaf.

Adopters:
- :class:`lca.contracts.models.core.execution.task_progress.TaskProgress`
  raises :class:`ContractViolation` from ``__post_init__`` when confidence is
  out of ``[0, 1]`` (ADR-0214 §3.1).
"""

from __future__ import annotations


class ContractViolation(ValueError):  # noqa: N818  (ADR-0214 §3.1 explicit name)
    """Raised when a typed Contract invariant is violated.

    Subclasses :class:`ValueError` because contract violations manifest as
    ill-formed values, not internal/runtime faults. Catching :class:`ValueError`
    also catches :class:`ContractViolation` — that is intentional; the more
    specific subclass exists for ``except`` clauses and diagnostic accuracy.
    """


__all__ = ["ContractViolation"]
