"""Patch: regression tests for the tool-chip non-empty invariant.

User reported "调用卡片折叠里面是空的" — the collapsed tool card header
shows an empty chip when ``args.description`` is missing on the wire. The
backend fix lives in ``event_translator.wire_tool_call`` (commit 96c45a35f,
default description to ``api_name``). These front-end tests pin the
consumer-side contract: the chip rendering reads ``description || command``
and falls back to ``command`` when description is absent, so a missing
description never produces a blank chip for tools that supply a command.

The patch adds two test files:

- ``Inspectors.test.tsx`` — drives the custom-inspector code path
  (``getBuiltinInspector('lobe-cloud-sandbox', 'runCommand')``) and pins
  the chip-text fallback chain.
- ``ToolTitle.test.tsx`` — drives the default-inspector code path and
  pins graceful render when ``args`` and ``partialArgs`` are both empty.

delete-when: never. The chip-population invariant is permanent; if the
backend fallback regresses, these tests catch it on the front-end side
because the chip will go blank for tools that omit description.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent

_INSPECTORS_REL = (
    "src/features/Conversation/Messages/AssistantGroup/Tool/Inspector/Inspectors.test.tsx"
)
_TOOL_TITLE_REL = (
    "src/features/Conversation/Messages/AssistantGroup/Tool/Inspector/ToolTitle.test.tsx"
)

_INSPECTORS_SOURCE = _HERE / "InspectorInspectors.test.tsx"
_TOOL_TITLE_SOURCE = _HERE / "InspectorToolTitle.test.tsx"

meta = PatchMeta(
    name="inspector_chip_fallback_tests",
    description=(
        "Regression tests pinning the tool-card chip non-empty contract: "
        "Inspectors forwards args to the custom inspector and falls back to "
        "command when description is missing; ToolTitle renders gracefully "
        "with empty args."
    ),
    files=(_INSPECTORS_REL, _TOOL_TITLE_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "Front-end chip blank when args.description missing; backend fix in "
        "wire_tool_call injects api_name as fallback. These tests pin the "
        "consumer contract: chip text is args.description || args.command, "
        "so the user never sees a folded tool card with empty header text."
    ),
    technical_detail=(
        "Whole-file copy of Inspectors.test.tsx and ToolTitle.test.tsx; "
        "drives the existing Inspectors and ToolTitle components and "
        "mocks getBuiltinInspector to inject a fake RunCommandInspector "
        "that mirrors the chip contract."
    ),
    verify_file=_INSPECTORS_REL,
    verify_marker="chip non-empty contract",
)


def apply(ctx: PatchContext) -> bool:
    if not _INSPECTORS_SOURCE.is_file():
        raise SystemExit(f"[inspector_chip_fallback_tests] missing source: {_INSPECTORS_SOURCE}")
    if not _TOOL_TITLE_SOURCE.is_file():
        raise SystemExit(f"[inspector_chip_fallback_tests] missing source: {_TOOL_TITLE_SOURCE}")

    changed_a = ctx.write_if_changed(
        _INSPECTORS_REL, _INSPECTORS_SOURCE.read_text(encoding="utf-8")
    )
    changed_b = ctx.write_if_changed(
        _TOOL_TITLE_REL, _TOOL_TITLE_SOURCE.read_text(encoding="utf-8")
    )
    return changed_a or changed_b
