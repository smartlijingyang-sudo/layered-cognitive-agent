"""Binding/factory resolution check.

Reject nodes whose ``factory`` string is missing, malformed, or
otherwise looks unresolvable — i.e. cannot be mapped to a real
registered plugin at runtime.

Why this matters
----------------

The lifter's :func:`_binding_from_factory_or_binding` only validates
that *either* ``binding:`` or ``factory:`` is present; it does not
check that the factory string itself resolves to a registered
plugin. The dispatch happens lazily when the executor walks the
node, so a typo'd factory (e.g. a misspelled ``<area>.<role>.<step>``
handle) silently blows up inside the executor-strategy path
instead of failing at boot.

This check surfaces the problem at plan-validation time. It runs
purely on the lifted :class:`Plan` — it does not consult the
plugin registry, since the registry is a runtime construct and the
boot validator must remain registry-independent. The check enforces
the **shape** of a well-formed factory reference:

- non-empty
- matches ``^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$`` (≥ 2 dotted
  segments, lowercase snake_case per segment)
- not in the closed reserved set (``__init__``, ``__main__``,
  ``self``, … — Python / framework keywords that can never be
  factory names)

Scope
-----

Only bindings that dispatch to a leaf executor are inspected:

- :attr:`BindingKind.NODE_EXECUTOR` — dispatches via
  :class:`NodeExecutorStrategy` to a plugin factory.
- :attr:`BindingKind.TRANSFORM` — same leaf-executor path; a
  transform is a factory-produced callable that maps a port
  payload to another.
- :attr:`BindingKind.OBSERVE`,
  :attr:`BindingKind.PARALLEL`,
  :attr:`BindingKind.AGENT_CONSULT`,
  :attr:`BindingKind.AGENT_FANOUT`,
  :attr:`BindingKind.GATE_CHAIN` — these are also factory-dispatched
  in the current strategy registry, so they go through the same
  shape gate.

:attr:`BindingKind.TERMINATE` and :attr:`BindingKind.SUBGRAPH` are
out of scope: terminate is a built-in leaf with no factory, and
subgraph delegates dispatch through :class:`SubgraphStrategy`
(``subgraph_ref``) rather than a factory string.
"""

from __future__ import annotations

import re

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck

# Factory shape: ≥ 2 dotted lowercase-snake segments, no leading/trailing dot.
_FACTORY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# Closed reserved set — Python/framework keywords and module sentinels
# that can never be valid factory names. Kept short on purpose: every
# entry here is an actual false-positive trap, not a stylistic preference.
_RESERVED_FACTORIES: frozenset[str] = frozenset(
    {
        "__init__",
        "__main__",
        "self",
        "cls",
        "none",
        "null",
        "true",
        "false",
    }
)

# Bindings that require a resolvable factory string.
_FACTORY_REQUIRED: frozenset[BindingKind] = frozenset(
    {
        BindingKind.NODE_EXECUTOR,
        BindingKind.TRANSFORM,
        BindingKind.OBSERVE,
        BindingKind.PARALLEL,
        BindingKind.AGENT_CONSULT,
        BindingKind.AGENT_FANOUT,
        BindingKind.GATE_CHAIN,
    }
)


class BindingResolutionCheck(PlanCheck):
    """Each factory-dispatched node must carry a well-formed ``factory`` string.

    A malformed factory (``""``, whitespace, capital letters, trailing
    dot, single segment, or reserved keyword) indicates a typo or a
    plan-author mistake. The check rejects the plan at boot so the
    operator sees the failure next to the plan definition, instead of
    a runtime ``KeyError`` deep inside
    :class:`lca.framework.graph.strategies.NodeExecutorStrategy`.
    """

    check_id = "binding_resolution"
    label = "Binding/factory resolves to a registered plugin"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for node in plan.nodes:
            if node.binding not in _FACTORY_REQUIRED:
                continue
            factory = _read_factory(node)
            if factory is None:
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} binding "
                    f"{node.binding.value!r} requires a non-empty "
                    f"'factory' string in its config (the kernel "
                    f"dispatches this binding through a leaf "
                    f"executor that resolves the factory at "
                    f"runtime); got empty/missing.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
            if not isinstance(factory, str):
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} 'factory' "
                    f"must be a string, got {type(factory).__name__}.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
            if not _FACTORY_RE.match(factory):
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} 'factory' "
                    f"{factory!r} is malformed; expected lowercase "
                    f"dotted snake_case with ≥ 2 segments "
                    f"(e.g. '<area>.<role>.<step>').",
                    plan_id=plan_id,
                    node_id=node.id,
                )
            if factory in _RESERVED_FACTORIES:
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} 'factory' "
                    f"{factory!r} is reserved and cannot be a "
                    f"registered plugin.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
        return None


def _read_factory(node: object) -> str | None:
    """Pull ``factory`` out of a :class:`PlanNode.config` mapping.

    The lifter stores the full raw yaml node into ``config``; the
    factory string lives at ``config['factory']``. Returns ``None``
    when the config is empty / not a mapping / has no factory key.
    """
    config = getattr(node, "config", None)
    if not isinstance(config, dict):
        return None
    factory = config.get("factory")
    if not isinstance(factory, str) or not factory:
        return None
    return factory


__all__ = ["BindingResolutionCheck"]