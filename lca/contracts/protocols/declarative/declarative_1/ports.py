"""Port name — typed alias for node-level data flow.

Per ADR-0219 §5: every port name written or read by a subgraph node must
appear in the node's IO schema. The graph framework treats port names as
opaque typed strings; it validates that every referenced port exists in
the node's IO schema at lift time. The framework does NOT encode a closed
set of business port names — that knowledge belongs to the agent/cognition
domain (see :mod:`lca.framework.graph.plan_sdk` for the SDK-level catalog).

``PortName`` is a :class:`~typing.NewType` alias for ``str`` so that
type-checkers can distinguish port names from arbitrary strings, while
Pydantic validation accepts any string value. The closed-set enforcement
moved from the type system to lift-time schema validation (Task 5 of the
typed port graph redesign).
"""

from __future__ import annotations

from typing import NewType

PortName = NewType("PortName", str)

__all__ = ["PortName"]
