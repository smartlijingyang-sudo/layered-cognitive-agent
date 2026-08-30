"""Executable regression guards for the ADR-0066/0068/0069 acceptance surface.

The sign-off document is only trustworthy when its commands execute exactly as
published. These tests keep the user-facing CLI contracts and every referenced
pytest path synchronized with the repository.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from lca.infrastructure.ops.cli import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_CRITERIA = (
    REPOSITORY_ROOT / "history/2026-08/adr-0074-plugin-remediation/acceptance-criteria.md"
)
TEST_PATH_PATTERN = re.compile(r"tests/[A-Za-z0-9_./-]+\.py")
RUNNER = CliRunner()


def test_creator_help_exposes_the_closed_four_face_vocabulary() -> None:
    """The V7 sign-off command must describe the only allowed Creator faces."""
    result = RUNNER.invoke(app, ["creator", "--help"])

    assert result.exit_code == 0, result.output
    assert "inspect / author / validate / promote" in result.output
    assert "stage / retire / publish" in result.output


def test_plan_list_templates_accepts_the_documented_positional_command() -> None:
    """The V12 sign-off command must work exactly as documented."""
    result = RUNNER.invoke(app, ["plan", "list-templates"])

    assert result.exit_code == 0, result.output
    assert "PlanTemplate count: 12" in result.output


def test_plan_sub_option_remains_a_compatible_alias() -> None:
    """Existing automation using the original option spelling remains supported."""
    result = RUNNER.invoke(app, ["plan", "--sub", "list-templates"])

    assert result.exit_code == 0, result.output
    assert "PlanTemplate count: 12" in result.output


def test_acceptance_criteria_references_existing_pytest_files() -> None:
    """Every pytest path published in the sign-off matrix must exist in-tree."""
    content = ACCEPTANCE_CRITERIA.read_text(encoding="utf-8")
    referenced_paths = sorted(set(TEST_PATH_PATTERN.findall(content)))
    missing = [path for path in referenced_paths if not (REPOSITORY_ROOT / path).is_file()]

    assert referenced_paths, "ADR acceptance criteria must publish executable pytest evidence"
    assert not missing, f"acceptance criteria reference missing pytest files: {missing}"
