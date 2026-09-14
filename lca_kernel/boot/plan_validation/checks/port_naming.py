"""Port naming convention check.

Reject any node port whose name drifts from the canonical
``lowercase_snake_case`` shape, or that picks up a phase-alias
suffix (``_payload`` / ``_outcome`` / ``_artifact``).

Why this matters
----------------

Port names are the SSOT for cross-node data flow. Aliases like
``perceive_observation`` or ``act_decision`` couple the port to
a phase implementation detail, so when a phase rename lands the
alias silently keeps the old reference and downstream nodes miss
the value at dispatch time. The mismatch is invisible to the
lifter (port names are opaque strings) and only blows up deep
in the executor.

Catching the drift at boot means every operator sees the same
naming rule across all plans, and the typed-port contract stays
the single source of truth.
"""
from __future__ import annotations

import re

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck

PORT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ALIAS_SUFFIXES = ("_payload", "_outcome", "_artifact")


class PortNamingConventionCheck(PlanCheck):
    """Plan-level port naming must follow ``lowercase_snake_case``.

    Every node's :attr:`~lca.contracts.protocols.graph.node_io.NodeIOSchema.inputs`
    and :attr:`~lca.contracts.protocols.graph.node_io.NodeIOSchema.outputs`
    port name must match ``^[a-z][a-z0-9_]*$`` and must not end with
    a phase-alias suffix (``_payload`` / ``_outcome`` / ``_artifact``).
    The first violation fails the check so the operator sees the
    full list of bad ports in one boot pass.
    """

    check_id = "port_naming_convention"
    label = "Port names follow snake_case convention"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        bad: list[tuple[str, str, str]] = []
        for node in plan.nodes:
            for port_spec in (*node.io_schema.inputs, *node.io_schema.outputs):
                name = port_spec.name
                if not PORT_NAME_RE.match(name):
                    bad.append((node.id, name, "invalid_format"))
                elif name.endswith(ALIAS_SUFFIXES):
                    bad.append((node.id, name, "phase_alias_suffix"))
        if not bad:
            return None
        names_list = ", ".join(f"{nid}.{n}" for nid, n, _ in bad)
        return PlanLiftError(
            f"plan {plan_id!r}: ports violate naming convention: "
            f"{names_list}. Use lowercase snake_case; avoid phase "
            f"aliases (e.g. _payload, _outcome).",
            plan_id=plan_id,
        )


__all__ = ["PortNamingConventionCheck"]
