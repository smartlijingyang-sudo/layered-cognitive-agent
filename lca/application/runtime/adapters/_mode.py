"""L0 RunIntent mode coercion.

``RunIntent.mode`` is ``Literal["solo", "team"]`` (ADR-0199 §2.2.1).
L0 adapters receive the value as a plain ``str`` (HTTP body, CLI argv)
and must narrow it to the literal before constructing the intent.

A plain ``cast`` would silence mypy while letting illegal values reach
L1; this helper performs the runtime check so the L0 boundary fails
closed. Lives in the adapters package because it is purely a wire-
adaptation concern — it never runs outside an adapter.
"""

from __future__ import annotations

from typing import TypeGuard

from lca.contracts.runtime.intent import RunMode

_ALLOWED_MODES: frozenset[RunMode] = frozenset({"solo", "team"})


def _is_run_mode(value: object) -> TypeGuard[RunMode]:
    return isinstance(value, str) and value in _ALLOWED_MODES


def coerce_mode(raw: object, *, field: str = "mode") -> RunMode:
    """Narrow an arbitrary wire value to ``RunMode``.

    Accepts the literal strings ``"solo"`` / ``"team"`` exactly.
    Rejects ``None``, ``bool``, non-strings, and any other string with
    a :class:`ValueError` that names the field, so the L1 facade never
    sees a value outside the contract's closed set.
    """
    if _is_run_mode(raw):
        return raw
    raise ValueError(f"RunIntent.{field} must be one of {sorted(_ALLOWED_MODES)}, got {raw!r}")


__all__ = ["coerce_mode"]
