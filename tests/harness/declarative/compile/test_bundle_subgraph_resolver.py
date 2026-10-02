"""``BundleSubgraphResolver`` compiles fixture subgraph bundles."""

from __future__ import annotations

from lca.harness.declarative.compile.subgraph_resolver import BundleSubgraphResolver

# NOTE (round-0349): test_resolver_compiles_think_subgraph retired --
# bundles/think-subgraph.yaml (and its fixture profile) were deliberately
# removed by 5f73cb237 ("chore(think): remove temporary _shared.py and
# subgraph_host container"); the bundle no longer resolves, so the test's
# subject is gone.
#
# NOTE (round-0349b): test_resolver_compiles_reflect_subgraph retired too --
# 63a68a4da (ADR-0221 cutover) deleted the whole lca/plugins/loop/phase/
# tree, so bundles/reflect-subgraph.yaml's $module
# (lca.plugins.loop.phase.reflect.standard.plugin) no longer exists and the
# bundle cannot compile (ModuleNotFoundError). Same orphan class: the
# test's subject is gone. This module is intentionally left with no tests;
# the resolver itself (BundleSubgraphResolver) is still covered elsewhere.


def test_resolver_returns_none_for_unknown_plan_ref() -> None:
    resolver = BundleSubgraphResolver()
    assert resolver.resolve("bundles/does-not-exist.yaml") is None
