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


def test_creator_action_vocabulary_is_closed() -> None:
    assert ALLOWED_ACTIONS == ("inspect", "author", "validate", "promote")
    source = _python_source()
    assert all(
        token not in source
        for token in ("dispatch_legacy_action", "actions_mount", "actions_simple")
    )
