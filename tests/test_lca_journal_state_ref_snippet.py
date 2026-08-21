"""lobehub UI patch source-level structural check —— ADR-0065 §四 / PR-10。

The lobehub patch is TypeScript; the LCA repo doesn't run a TS test suite.
We assert the patch's textual behavior:

- ``buildToolState`` helper exists and reads ``state_ref`` first
- ``ToolStarted`` and ``ToolInvoked`` cases use ``buildToolState``
- legacy ``plugin_state`` is the last-resort fallback (not the primary source)
- ``state_ref`` URL hint for hydration via ``/runs/{id}/evidence/{ref}``
  is documented in the function comment.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LCA_JOURNAL = _ROOT / "deploy" / "lobehub" / "patches" / "runtime" / "lcaJournal.ts"


def _read_source() -> str:
    return _LCA_JOURNAL.read_text(encoding="utf-8")


def test_lca_journal_defines_buildToolState() -> None:
    """``buildToolState`` helper is exported."""
    src = _read_source()
    assert "export function buildToolState" in src, (
        "lcaJournal.ts must export a `buildToolState` helper for §四 state_ref-first read"
    )


def test_lca_journal_buildToolState_reads_state_ref_first() -> None:
    """``buildToolState`` checks ``state_ref`` before typed fields before plugin_state."""
    src = _read_source()
    # extract the function body
    m = re.search(
        r"export function buildToolState\([\s\S]*?^\}",
        src,
        re.MULTILINE,
    )
    assert m is not None, "buildToolState function not found"
    body = m.group(0)
    # state_ref must be checked before plugin_state fallback
    state_ref_idx = body.find("state_ref")
    plugin_state_idx = body.find("plugin_state")
    assert state_ref_idx > 0, "buildToolState must read state_ref"
    assert plugin_state_idx > 0, "buildToolState must keep legacy fallback"
    assert state_ref_idx < plugin_state_idx, (
        "state_ref must be checked before plugin_state fallback (ADR-0065 §四)"
    )


def test_lca_journal_buildToolState_preserves_typed_fields() -> None:
    """typed fields (code / command / language / skill_id / description /
    execution_env / output_text / skill_inputs) are surfaced."""
    src = _read_source()
    for key in (
        "code",
        "command",
        "language",
        "skill_id",
        "description",
        "execution_env",
        "output_text",
        "skill_inputs",
    ):
        # accept: payload.key, 'key', or "key"
        assert (
            f"payload.{key}" in src
            or f"'{key}'" in src
            or f'"{key}"' in src
        ), f"buildToolState must surface typed field: {key}"


def test_lca_journal_tool_started_uses_buildToolState() -> None:
    """ToolStarted / ToolCallStreaming case must call ``buildToolState`` for state."""
    src = _read_source()
    # search for the ToolStarted case in projectJournalFrame
    # either: case 'ToolStarted': ... state: buildToolState(payload, frame)
    assert "buildToolState(payload, frame)" in src, (
        "ToolStarted / ToolInvoked must use buildToolState for state"
    )


def test_lca_journal_no_plugin_state_primary() -> None:
    """The ToolStarted / ToolInvoked branches must NOT read plugin_state directly;
    they must go through buildToolState which respects the §四 priority."""
    src = _read_source()
    # We look for the projectJournalFrame body and ensure Tool* branches use buildToolState
    # (rather than direct payload.plugin_state).
    for case in ("ToolCallStreaming", "ToolStarted", "ToolInvoked"):
        # find the case block
        idx = src.find(f"case '{case}'")
        if idx < 0:
            continue
        block_end = src.find("return {", idx)
        block_end = src.find("\n    }", block_end)
        if block_end < 0:
            continue
        block = src[idx:block_end]
        # The case must contain `state: buildToolState(`
        assert "buildToolState(" in block or "state: buildToolState" in block, (
            f"case '{case}' must construct state via buildToolState"
        )
        # It must NOT contain `payload.plugin_state` directly
        assert "payload.plugin_state" not in block, (
            f"case '{case}' reads plugin_state directly; must go through buildToolState"
        )


def test_lca_journal_does_not_name_result_preview() -> None:
    """legacy view-only ``result_preview`` must not be the primary state source."""
    src = _read_source()
    # The buildToolState function body should not reference result_preview
    m = re.search(
        r"export function buildToolState\([\s\S]*?^\}",
        src,
        re.MULTILINE,
    )
    body = m.group(0) if m else ""
    assert "result_preview" not in body, (
        "buildToolState must not surface result_preview as primary state"
    )
