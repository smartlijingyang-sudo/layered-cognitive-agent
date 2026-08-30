from __future__ import annotations

from dataclasses import replace

import pytest

import lca.harness.profile.plan_compiler as plan_compiler
from lca.contracts.protocols.declarative.declarative_common import DeclarativeValidationError
from lca.contracts.protocols.declarative.declarative_graph import ValidationIssue, ValidationReport
from lca.harness.declarative.compile.compiler import compile_declarative_projection
from lca.harness.profile.resolve import resolve_profile


def test_compile_plan_rejects_invalid_projection_without_phase_bindings(monkeypatch) -> None:
    """The CompiledRunPlan seam must fail closed even for an empty graph."""
    resolved = resolve_profile("profiles/web-standard.yaml")
    projection = compile_declarative_projection(resolved)
    invalid = replace(
        projection,
        phase_bindings=(),
        validation_report=ValidationReport(
            (ValidationIssue("PS-099", "invalid projection", "test"),)
        ),
    )
    monkeypatch.setattr(
        plan_compiler, "compile_declarative_projection", lambda *args, **kwargs: invalid
    )

    with pytest.raises(DeclarativeValidationError, match="invalid projection"):
        plan_compiler.compile_plan(resolved)


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
        ({"task_id": 7}, "task_id must be a string or None"),
        ({"env_fingerprint": 7}, "env_fingerprint must be a string or None"),
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
