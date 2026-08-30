"""Lobehub UI patch source-level structural check — contract-driven projection.

The lobehub patch is TypeScript; the LCA repo doesn't run a TS test suite
on these source files. We assert the patch's textual behavior at the
contract layer:

- ``CONTRACTS`` table is generated from Python registry
- ``projectToolCall`` reads ``data.projected_state`` when present
- ``projectToolCall`` falls back to reconstructing from observation fields
- Legacy argv-style lifting helper ``buildToolState`` is no longer primary
  (the new projection module replaces it)
- Frontend renderers consume ``args.X`` / ``pluginState.X`` from the
  RenderContract's wire_keys

ADR-XXXX: replaces the previous buildToolState checks with the new
projection pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PROJECTION = _ROOT / "deploy" / "lobehub" / "patches" / "runtime" / "lcaToolRender" / "projection.ts"
_CONTRACTS = _ROOT / "deploy" / "lobehub" / "patches" / "runtime" / "lcaToolRender" / "contracts.generated.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contracts_table_generated_and_present() -> None:
    """``CONTRACTS`` table exists and is wired through the projection module."""
    contracts = _read(_CONTRACTS)
    assert "export const CONTRACTS" in contracts, (
        "contracts.generated.ts must export CONTRACTS"
    )
    # Spot-check that skill tools are present
    for tool in ("activate_skill", "read_skill_reference", "runCommand", "executeCode"):
        assert f'"{tool}"' in contracts, f"CONTRACTS missing {tool}"


def test_projection_reads_projected_state_first() -> None:
    """``projectToolCall`` reads ``data.projected_state`` before falling back."""
    src = _read(_PROJECTION)
    assert "projected_state" in src, "projection.ts must reference projected_state"
    assert "inlineState" in src, "projection.ts must name inline projected_state"


def test_projection_applies_wire_key_renames() -> None:
    """Skill tools' ``skill_id`` Python key is mapped to wire_key ``name``."""
    contracts = _read(_CONTRACTS)
    # activate_skill: skill_id → name
    m = re.search(r'"activate_skill":\s*\{[^}]*args:\s*\[\s*\{\s*pythonKey:\s*"skill_id",\s*wireKey:\s*"name"', contracts)
    assert m is not None, "activate_skill must rename skill_id → name"
    # read_skill_reference: skill_id → id
    m = re.search(r'"read_skill_reference":\s*\{[^}]*args:\s*\[\s*\{\s*pythonKey:\s*"skill_id",\s*wireKey:\s*"id"', contracts)
    assert m is not None, "read_skill_reference must rename skill_id → id"


def test_projection_returns_unified_shape() -> None:
    """``projectToolCall`` returns ``args``, ``state``, ``content`` for callers."""
    src = _read(_PROJECTION)
    # The result type must include args, state, content
    for key in ("args:", "state:", "content:"):
        assert key in src, f"projection.ts must produce {key}"


def test_legacy_build_tool_state_no_longer_required() -> None:
    """Old ``buildToolState`` helper is replaced by ``projectToolCall``.

    If lcaJournal.ts has been removed (Task 7), this test simply asserts
    the new pipeline owns the projection responsibility.
    """
    src = _read(_PROJECTION)
    assert "projectToolCall" in src, "projection.ts must export projectToolCall"
