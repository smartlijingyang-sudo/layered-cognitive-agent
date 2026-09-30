"""String-predicate DSL validation for boot-time plan checks.

The lifter's :func:`~lca.framework.graph.lifter._coerce_when` maps
the strings below to ``None`` — the predicates evaluate to "always
true" at runtime, but any other string is rejected at lift time (D4
typed-port cutover). The legacy string-DSL edge conditions silently
fired every edge regardless of the upstream decision; we fail loud at
boot so a misroute never reaches runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.graph.errors import PlanLiftError

# Strings that the lifter's :func:`_coerce_when` maps to ``None`` —
# the predicates evaluate to "always true" at runtime, but any other
# string is rejected at lift time (D4 typed-port cutover). The legacy
# string-DSL edge conditions silently fired every edge regardless of
# the upstream decision; we fail loud at boot so a misroute never
# reaches runtime.
_STRING_WHEN_ALIASES = frozenset({"true", "false", ""})


def _check_string_predicate(
    spec: Mapping[str, Any],
    *,
    plan_id: str,
) -> PlanLiftError | None:
    """Build a :class:`PlanLiftError` for a string-predicate edge, or None."""
    for raw in spec.get("edges", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        when = raw.get("when")
        if isinstance(when, str) and when.strip().lower() not in _STRING_WHEN_ALIASES:
            edge_id = f"{raw.get('from', '?')}->{raw.get('to', '?')}"
            return PlanLiftError(
                f"plan {plan_id!r}: edge {edge_id!r}: string when: {when!r} is no longer supported; "
                "use a typed Predicate dict",
                plan_id=plan_id,
                edge_id=edge_id,
            )
    return None


__all__ = ["_STRING_WHEN_ALIASES", "_check_string_predicate"]
