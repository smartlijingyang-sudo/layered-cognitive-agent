"""Tests for observability compile graph (ADR-0198)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.compile.compiler import ObservabilityCompiler, reset_compiled_plan_cache

_CONFIG = Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"


@pytest.fixture(autouse=True)
def _clear_plan_cache() -> None:
    reset_compiled_plan_cache()
    yield
    reset_compiled_plan_cache()


def test_default_compile_plan_ok() -> None:
    plan = ObservabilityCompiler.compile(_CONFIG)
    errors = [d for d in plan.diagnostics if d.severity == "error"]
    assert plan.ok, [f"{d.code}: {d.message}" for d in errors]
    assert len(plan.closure_events) >= 10
    assert "journal.step_tree" in {p.projection_id for p in plan.projections}
    rules = plan.bindings_by_projection.get("journal.step_tree", ())
    assert any(r.rule_id == "tool_call_evidence" for r in rules)
    assert any(r.rule_id == "tool_call_span_start" for r in rules)


def test_merge_for_ep_from_bindings() -> None:
    plan = ObservabilityCompiler.compile(_CONFIG)
    assert plan.merge_for_ep("step.tool_call.record") == "replace_richer"
    assert plan.merge_for_ep("body.tool.execute.start") == "fill_empty_only"


def test_duplicate_closure_ep_fails(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    (cfg / "compile").mkdir(parents=True)
    (cfg / "observability").mkdir(parents=True)
    (cfg / "projections" / "bindings").mkdir(parents=True)
    (cfg / "outputs").mkdir(parents=True)
    (cfg / "compile/global_policies.yaml").write_text(
        "schema: lca.observability.compile/1\nlayer_merge_policies: []\n"
    )
    (cfg / "observability/closure_catalog.yaml").write_text(
        """
schema: lca.observability.closure/1
events:
  - execution_point: step.tool_call.record
    layer: L3_evidence
    durable: true
    producer_seam: loop.cursor
    consumers: [persistence.spine]
  - execution_point: step.tool_call.record
    layer: L3_evidence
    durable: true
    producer_seam: loop.cursor
    consumers: [persistence.spine]
"""
    )
    (cfg / "projections/registry.yaml").write_text(
        """
schema: lca.observability.projection/1
projections: []
"""
    )
    (cfg / "outputs/run_artifacts.yaml").write_text(
        """
schema: lca.observability.outputs/1
artifacts:
  - id: spine
    path_pattern: "{run_dir}/{run_id}.spine.jsonl"
    format: ndjson
    schema: lca.spine.record/1
    source_projection: persistence.spine
    durable_ssot: true
"""
    )
    plan = ObservabilityCompiler.compile(cfg)
    assert not plan.ok
    assert any(d.code == "closure.duplicate_ep" for d in plan.diagnostics)
