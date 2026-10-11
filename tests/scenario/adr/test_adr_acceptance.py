"""Executable regression guards for the ADR-0066/0068/0069 acceptance surface.

The sign-off document is only trustworthy when its commands execute exactly as
published. These tests keep the user-facing CLI contracts and every referenced
pytest path synchronized with the repository.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from lca.infrastructure.cli.cli.cli import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ACCEPTANCE_CRITERIA = (
    REPOSITORY_ROOT / "history/2026-08/adr-0074-plugin-remediation/acceptance-criteria.md"
)
TEST_PATH_PATTERN = re.compile(r"tests/[A-Za-z0-9_./-]+\.py")
RUNNER = CliRunner()

# Paths renamed by the 2026-09-06 test-layout split (4a6b5e04a); the historical
# sign-off matrix keeps the old spellings, so resolve them here.
RENAMED_TEST_PATHS = {
    "tests/test_adr_acceptance.py": "tests/scenario/adr/test_adr_acceptance.py",
    "tests/test_capability_monotonicity.py": "tests/scenario/capability/test_capability_monotonicity.py",
    "tests/test_check_adr_supervision.py": "tests/scenario/check/test_check_adr_supervision.py",
    "tests/test_cordis_creator_e2e.py": "tests/scenario/cordis/test_cordis_creator_e2e.py",
}
# Intentionally retired with their features; the historical matrix is a 2026-08
# snapshot and stays untouched, so the guard tolerates them here.
RETIRED_TEST_PATHS = {
    "tests/declarative/test_runtime_driver.py",  # 2b8a92b20: lca/framework/declarative deleted
    "tests/harness/test_harness_spine_e2e.py",  # f8b7f0896: DSH unification retired the old plane
    "tests/harness/test_plugin_optional_fields.py",  # a6ec2d135: ContributionRole validation cleanup
}


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

    def _resolve(path: str) -> Path | None:
        if path in RETIRED_TEST_PATHS:
            return None
        return REPOSITORY_ROOT / RENAMED_TEST_PATHS.get(path, path)

    missing = [
        path
        for path in referenced_paths
        if (resolved := _resolve(path)) is not None and not resolved.is_file()
    ]

    assert referenced_paths, "ADR acceptance criteria must publish executable pytest evidence"
    assert not missing, f"acceptance criteria reference missing pytest files: {missing}"
