"""PR-7 — Dual lineage retirement regression guards.

Verifies that the three bundles retired by ADR-0236 are gone, and that
``profiles/benchmark.yaml`` + ``profiles/cordis-creator.yaml`` no
longer reference the dual-lineage identifiers. The production control
spine is ``bundles/outer/phase_main.yaml`` only.
"""

from pathlib import Path


def test_no_agent_run_phase_bundle():
    """PR-7: agent.run.phase bundle 已删(G-8 + dual lineage debt 收口)"""
    assert not Path("bundles/agent/run_phase.yaml").exists()


def test_no_declarative_phase_graph_bundle():
    """PR-7: declarative-phase-graph bundle 已删(outer YAML 自含 edges)"""
    assert not Path("bundles/declarative-phase-graph.yaml").exists()


def test_no_declarative_recovery_bundle():
    """PR-7: declarative-recovery bundle 已删(recovery 边进 outer YAML)"""
    assert not Path("bundles/declarative-recovery.yaml").exists()


def test_profiles_use_region_tag_path():
    """PR-7: benchmark.yaml + cordis-creator.yaml 不再引用 declarative-*"""
    for profile in ("benchmark.yaml", "cordis-creator.yaml"):
        content = Path(f"profiles/{profile}").read_text()
        assert "declarative-phase-graph" not in content
        assert "declarative-recovery" not in content
        assert "agent.run.phase" not in content
