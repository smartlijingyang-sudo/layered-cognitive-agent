"""Node-id naming check.

Reject node ids that violate the phase namespace convention so the
``phase.<name>.<step>`` / ``concept.<name>.<step>`` / ``control.<name>``
/ ``body.<name>`` / ``tool.<name>`` / ``gate.<name>`` /
``outer.<name>`` / ``lca.<name>`` vocabulary stays a stable SSOT.

Why this matters
----------------

Node ids appear in profile YAML, runtime traces, audit messages,
and capability diagnostics. When they drift to opaque handles
(``node1`` / ``step_a``) or to phase-alias tails
(``perceive_payload_fold`` / ``act_outcome_emit``), the namespace
loses its self-describing property:

- operators can no longer grep ``phase.perceive`` to find every
  perceive step;
- profile diffs and audit messages become unparseable;
- the same id may collide with a real namespace prefix and
  silently shadow a typed-port lookup.

This check catches both classes of drift at boot: a node id must
either be a dotted ``<ns>.<...>.<step>`` lowercase identifier
(one or more dot-separated segments, each starting with a letter
and containing only ``[a-z0-9_]``) or a single-segment
``[a-z][a-z0-9_]*`` identifier (plan-level simple plans that
don't live under a namespace yet), and it must not carry a
phase-alias token at the tail (``_payload`` / ``_outcome`` /
``_artifact``) or mid-id (``_payload_`` / ``_outcome_`` /
``_artifact_``).
"""

from __future__ import annotations

import re

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck

NODE_ID_RE = re.compile(
    r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
    r"|^[a-z][a-z0-9_]*$"
)
ALIAS_SUFFIXES = ("_payload", "_outcome", "_artifact")
ALIAS_INFIXES = ("_payload_", "_outcome_", "_artifact_")


class NodeIdNamingCheck(PlanCheck):
    """Node ids must follow the phase namespace convention.

    Acceptable shapes:

    - ``phase.<name>.<step>`` (e.g. ``phase.perceive.observe``)
    - ``concept.<name>.<step>`` (e.g. ``concept.decision.classify``)
    - ``control.<name>`` (e.g. ``control.perceive.context``)
    - ``body.<name>`` / ``tool.<name>`` / ``gate.<name>``
    - ``outer.<name>`` / ``lca.<name>``
    - single-segment ``[a-z][a-z0-9_]*`` (plan-level simple plans)

    Rejected: opaque handles (``node1``, ``step_a``), mixed-case
    (``BadName``), kebab-case (``step-a``), empty ids, and ids
    carrying a phase-alias suffix at the tail (``_payload`` /
    ``_outcome`` / ``_artifact``) or mid-id (``_payload_`` /
    ``_outcome_`` / ``_artifact_``).
    """

    check_id = "node_id_naming"
    label = "Node ids follow phase namespace convention"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        bad: list[tuple[str, str]] = []
        for n in plan.nodes:
            node_id = n.id
            if not NODE_ID_RE.match(node_id):
                bad.append((node_id, "invalid_format"))
                continue
            if node_id.endswith(ALIAS_SUFFIXES):
                bad.append((node_id, "phase_alias_suffix"))
            elif any(token in node_id for token in ALIAS_INFIXES):
                bad.append((node_id, "phase_alias_infix"))
        if bad:
            bad_list = ", ".join(f"{nid} ({reason})" for nid, reason in bad)
            return PlanLiftError(
                f"plan {plan_id!r}: node ids violate naming convention: "
                f"{bad_list}. Use lowercase dotted namespacing like "
                f"phase.perceive.observe / concept.decision.parse.response / "
                f"tool.fork.dispatch. Avoid phase aliases (_payload, "
                f"_outcome, _artifact).",
                plan_id=plan_id,
            )
        return None


__all__ = ["NodeIdNamingCheck"]
