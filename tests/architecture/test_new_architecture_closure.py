"""Architecture guards for the final plan-driven, four-state, four-face cutover."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from lca.contracts.harness.artifact import CapabilityArtifact
from lca.plugins.tools.cordis_control.tool import ALLOWED_ACTIONS

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = (ROOT / "lca", ROOT / "gateway")


def _python_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for root in PRODUCTION_ROOTS for path in root.rglob("*.py")
    )


def test_spawn_and_compiler_have_no_legacy_plan_fallback() -> None:
    source = _python_source()
    forbidden = (
        "LCA_PLAN_COMPAT",
        "use_legacy_spawn",
        "is_bind_plan_available",
        "legacy_sub_composers",
    )
    assert all(token not in source for token in forbidden)


def test_artifact_contract_is_four_state_only() -> None:
    assert {field.name for field in fields(CapabilityArtifact)} == {
        "logical_id",
        "revision_digest",
        "state",
        "scope",
        "grants",
        "metadata",
        "version",
    }
    source = _python_source()
    assert all(
        token not in source
        for token in ("legacy_state", "migrate_legacy_state", "LEGACY_TO_NEW_STATE")
    )


def test_team_composer_uses_the_agent_assembly_seam() -> None:
    source = (ROOT / "lca" / "plugins" / "composer" / "team_composer.py").read_text(
        encoding="utf-8"
    )
    assert "lca.application.spawn" not in source
    assert "lca.application.team_wiring" not in source
    assert "self._agent_assembler.assemble_member" in source
    assert "self._agent_assembler.assemble_lead" in source


def test_creator_action_vocabulary_is_closed() -> None:
    assert ALLOWED_ACTIONS == ("inspect", "author", "validate", "promote")
    source = _python_source()
    assert all(
        token not in source
        for token in ("dispatch_legacy_action", "actions_mount", "actions_simple")
    )


def test_production_sources_do_not_reference_removed_runtime_modules() -> None:
    """Task 8 Step 1: Verify no production code imports removed legacy modules.

    ADR-0074/0075 declarative cutover removed:
    - lca.runtime.control_policies (Task 5 Part 2)
    - lca.harness.command.dual_write (Task 6)
    """
    source = _python_source()
    forbidden = (
        "from lca.runtime.control_policies",
        "from lca.runtime import control_policies",
        "import lca.runtime.control_policies",
        "from lca.harness.command.dual_write",
        "from lca.harness.command import dual_write",
        "import lca.harness.command.dual_write",
    )
    assert all(token not in source for token in forbidden), (
        f"Production code still references removed modules: {[t for t in forbidden if t in source]}"
    )
