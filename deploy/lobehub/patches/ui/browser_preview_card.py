"""Patch: render interactive BrowserPreviewCard for live browser sessions.

Part of Grok Bot / Meta Muse alignment (ADR-0248 §5.3 / s13):
Renders a compact browser preview card in chat stream with live title, URL, and takeover buttons.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/BrowserPreviewCard.tsx"
_SOURCE_NAME = "BrowserPreviewCard.tsx"

meta = PatchMeta(
    name="browser_preview_card",
    description="Render interactive BrowserPreviewCard for live browser sessions in chat",
    files=(_COMPONENT_REL,),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide Grok/Muse-style live browser card with thumbnail and takeover button in chat stream",
    technical_detail=(
        "Installs BrowserPreviewCard.tsx in Conversation/Messages/components"
    ),
    verify_file=_COMPONENT_REL,
    verify_marker="BrowserPreviewCard",
)


def apply(ctx: PatchContext) -> bool:
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[browser_preview_card] missing patch source: {source}")
    return ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8"))
