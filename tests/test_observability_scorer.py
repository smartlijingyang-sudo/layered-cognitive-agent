"""FactScorer 注册测试（ADR-0063 PR-9/PR-10）。"""

from __future__ import annotations


def test_seam_provides_registry() -> None:
    from lca.plugins import seam_fact_scorer as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-fact-scorer-seam"


def test_langfuse_scorer_registered() -> None:
    from lca.plugins import providers  # noqa: F401
    from lca.plugins.providers import fact_scorer_langfuse as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-langfuse-eval-scorer"
