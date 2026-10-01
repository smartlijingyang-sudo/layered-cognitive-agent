"""Patch: render interactive AssistantNamingWidget for assistant naming ceremony.

Part of Conversational Onboarding and Assistant Naming ceremony (ADR-0252 / Muse alignment):
Allows users to click candidate name chips or enter a custom name during onboarding,
providing real-time preview, confirmation, and celebratory reaction feedback.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantNamingWidget.tsx"
_SOURCE_NAME = "AssistantNamingWidget.tsx"

meta = PatchMeta(
    name="assistant_naming_widget",
    description="Render interactive AssistantNamingWidget for assistant naming ceremony",
    files=(_COMPONENT_REL,),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide Muse-style interactive naming widget and celebratory reaction in LobeHub onboarding",
    technical_detail=(
        "Creates AssistantNamingWidget.tsx in Conversation/Messages/components to render"
        " candidate name chips, custom input, live greeting preview, and celebratory feedback"
    ),
    verify_file=_COMPONENT_REL,
    verify_marker="AssistantNamingWidget",
)


def apply(ctx: PatchContext) -> bool:
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[assistant_naming_widget] missing patch source: {source}")
    return ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8"))
