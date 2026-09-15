"""Regression test for retired ``think.classify`` dead node.

Background: ``bundles/think.yaml`` previously declared ``think.classify``
as a node, but commit ``2ee56fdc8`` rewired ``think.reason`` →
``think.history.assemble`` → ``think.llm.dispatch`` → ``think.decision.parse``
→ ``think.gate`` and removed the only edges that reached
``think.classify``. The :class:`ReachabilityCheck` at plan-lift time
raised ``PlanLiftError`` and blocked kernel boot. This test pins the
post-retire state: every node in the think subgraph is reachable from
its entry, so the kernel can boot ``profiles/web-standard.yaml`` without
monkey-patching the validator.

See ``docs/notes/implemented/primitive/2026-09-15-think-classify-retire.md``.
"""

from __future__ import annotations

import yaml

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca_kernel.boot.plan_validation.checks.reachability import (
    ReachabilityCheck,
)


def test_think_subgraph_reachability_passes() -> None:
    """The post-retire think subgraph has no unreachable nodes from
    ``think.shortcut``.

    Pre-retire this raised
    ``PlanLiftError("...nodes ['think.classify'] are unreachable...")``
    and the integration test had to monkey-patch
    ``validate_profile_plans`` to bypass the invariant.
    """
    with open("bundles/think.yaml", encoding="utf-8") as fh:
        bundle = yaml.safe_load(fh)
    nodes = tuple(
        PlanNode(
            id=n["id"],
            binding=BindingKind.NODE_EXECUTOR,
            entry=(n["id"] == "think.shortcut"),
            terminal=n.get("terminal", False),
        )
        for n in bundle["nodes"]
    )
    edges = tuple(
        PlanEdge(source=e["from"], target=e["to"]) for e in bundle.get("edges", [])
    )
    plan = Plan(id=bundle["id"], nodes=nodes, edges=edges)

    err = ReachabilityCheck().run(plan, plan_id="think.subgraph")
    assert err is None, f"unexpected reachability error: {err}"


def test_think_subgraph_bundle_has_no_classify_node() -> None:
    """``think.classify`` must not be re-introduced without restoring
    its in-edges; it was retired because ``decision.parse`` covers the
    same responsibility (see 2026-09-15-think-classify-retire note).
    """
    with open("bundles/think.yaml", encoding="utf-8") as fh:
        bundle = yaml.safe_load(fh)
    node_ids = [n["id"] for n in bundle["nodes"]]
    assert "think.classify" not in node_ids

    expected = {"think.shortcut", "think.route", "think.reason", "think.gate"}
    assert expected.issubset(set(node_ids))
