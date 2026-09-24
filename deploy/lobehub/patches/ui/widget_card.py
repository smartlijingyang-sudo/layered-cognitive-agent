"""Patch: render interactive WidgetCard for user choice selection and /answer resume.

Part of Grok Bot alignment (ADR-0248 §3.3 / s03):
Allows users to click structured options presented by send_message(type='widget'),
which automatically resolves the WAITING_INPUT state via POST /runs/:id/answer.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/WidgetCard.tsx"
_SOURCE_NAME = "WidgetCard.tsx"

meta = PatchMeta(
    name="widget_card",
    description="Render interactive WidgetCard for user choice options and /answer resume",
    files=(_COMPONENT_REL,),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide Grok-style interactive widget option cards and seamless /answer resume in LobeHub",
    technical_detail=(
        "Creates WidgetCard.tsx in Conversation/Messages/components to render structured option buttons"
    ),
    verify_file=_COMPONENT_REL,
    verify_marker="WidgetCard",
)


def apply(ctx: PatchContext) -> bool:
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[widget_card] missing patch source: {source}")
    return ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8"))
