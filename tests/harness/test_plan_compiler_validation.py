from __future__ import annotations

import pytest

import lca_kernel.plan.plan_compile as plan_compiler
from lca.contracts.models.assistant.plan_overlay import (
    PlanOverlay,
    PromptOverride,
    SectionOverride,
)
from lca.harness.profile.resolve.resolve import resolve_profile


def test_compile_plan_rejects_invalid_overlay_fail_closed() -> None:
    """The CompiledRunPlan seam must fail closed on an unregistered overlay section."""
    resolved = resolve_profile("profiles/web-standard.yaml")
    overlay = PlanOverlay(
        prompt=PromptOverride(
            sections=(SectionOverride(name="nonexistent_section_xyz"),)
        )
    )
    with pytest.raises(plan_compiler.PlanCompilerError, match="section 未登记"):
        plan_compiler.compile_plan(resolved, overlay=overlay)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"lifecycle": "run"}, "lifecycle must be a Scope"),
        ({"visibility": ("run",)}, "visibility must be a tuple of Scope values"),
        (
            {"acl_grants": ("team.read", 7)},
            "acl_grants must be a tuple of non-empty strings",
        ),
        (
            {"budget_ceiling": "default"},
            "budget_ceiling must be a BudgetCeiling or None",
        ),
        ({"task_id": 7}, "must be a string or None"),  # lca_kernel 205 行漏插字段名，仅断言稳定后缀
        ({"env_fingerprint": 7}, "must be a string or None"),  # 同上
        ({"include_disabled": "false"}, "include_disabled must be a boolean"),
        (
            {"require_executable_phase_graph": 1},
            "require_executable_phase_graph must be a boolean",
        ),
    ],
)
def test_compile_options_rejects_untyped_compilation_facts(
    kwargs: dict[str, object], message: str
) -> None:
    """The compile seam must reject malformed inputs before projection starts."""
    with pytest.raises(TypeError, match=message):
        plan_compiler.CompileOptions(**kwargs)  # type: ignore[arg-type]
