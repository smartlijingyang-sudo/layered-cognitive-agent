"""``BundleSubgraphResolver`` compiles fixture subgraph bundles."""

from __future__ import annotations

from lca.harness.declarative.compile.subgraph_resolver import BundleSubgraphResolver


def test_resolver_compiles_think_subgraph() -> None:
    from lca.harness.declarative.compile import subgraph_resolver as resolver_module

    resolver_module._compile_subgraph_profile.cache_clear()
    resolver = BundleSubgraphResolver()
    plan = resolver.resolve("bundles/think-subgraph.yaml")
    assert plan is not None
    assert plan.phase_graph is not None
    assert plan.phase_graph.entry == "think.subgraph.shortcut"
    node_ids = {node.id for node in plan.phase_graph.nodes}
    assert node_ids == {
        "think.subgraph.shortcut",
        "think.subgraph.route",
        "think.subgraph.reason",
        "think.subgraph.classify",
        "think.subgraph.gate",
    }


def test_resolver_compiles_reflect_subgraph() -> None:
    resolver = BundleSubgraphResolver()
    plan = resolver.resolve("bundles/reflect-subgraph.yaml")
    assert plan is not None
    assert plan.phase_graph is not None
    node_ids = {node.id for node in plan.phase_graph.nodes}
    assert {"reflect.inner_score", "reflect.inner_summarize"} <= node_ids


def test_resolver_returns_none_for_unknown_plan_ref() -> None:
    resolver = BundleSubgraphResolver()
    assert resolver.resolve("bundles/does-not-exist.yaml") is None
