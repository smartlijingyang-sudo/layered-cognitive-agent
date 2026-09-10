"""M4 — Lifecycle schema contract tests (PlanCompileComplete/Failed/SubgraphResolve/BundleLoad)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.observability.observation import (
    BundleLoad,
    PlanCompileComplete,
    PlanCompileFailed,
    SubgraphResolve,
)


def test_plan_compile_complete_basic() -> None:
    c = PlanCompileComplete(
        run_id="r",
        plan_ref="p",
        profile_path="x.yaml",
        compiled_at="t",
    )
    assert c.plan_ref == "p"


def test_plan_compile_failed_carries_traceback() -> None:
    f = PlanCompileFailed(
        run_id="r",
        profile_path="x.yaml",
        exception_class="ValidationError",
        exception_message="bad",
        traceback_text="Traceback ...",
        failed_at="t",
    )
    assert f.exception_class == "ValidationError"
    assert "Traceback" in f.traceback_text


def test_subgraph_resolve_status_values() -> None:
    s_ok = SubgraphResolve(
        run_id="r",
        plan_ref="p",
        owner_node_id="think.main",
        entry_node="think.shortcut",
        status="resolved",
        sub_blueprint_digest="sha256:...",
        resolved_at="t",
    )
    s_fail = SubgraphResolve(
        run_id="r",
        plan_ref="p",
        owner_node_id="think.main",
        entry_node="think.shortcut",
        status="failed",
        failure_reason="plugin missing",
        resolved_at="t",
    )
    assert s_ok.status == "resolved"
    assert s_fail.failure_reason == "plugin missing"


def test_bundle_load_plugin_id_optional() -> None:
    b = BundleLoad(
        run_id="r",
        bundle_id="b1",
        plugin_id=None,
        status="loaded",
        version="v1",
        loaded_at="t",
    )
    assert b.plugin_id is None


def test_plan_compile_failed_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        PlanCompileFailed(
            run_id="r",
            profile_path="x",
            exception_class="E",
            exception_message="m",
            traceback_text="t",
            failed_at="t",
            unknown="x",  # type: ignore[call-arg]
        )
