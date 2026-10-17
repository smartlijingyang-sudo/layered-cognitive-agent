"""Patch: render right slide-out BrowserViewerDrawer for CDP screencast and takeover.

Part of Grok Bot / Meta Muse alignment (ADR-0248 §5.3 / s13):
Provides a responsive slide-out drawer containing navigation bar and interactive Canvas.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_DRAWER_REL = "src/features/Conversation/components/BrowserViewerDrawer.tsx"
_CANVAS_REL = "src/features/Conversation/components/BrowserCanvas.tsx"
_TOOLBAR_REL = "src/features/Conversation/components/BrowserToolbar.tsx"

meta = PatchMeta(
    name="browser_viewer_drawer",
    description="Render right slide-out BrowserViewerDrawer for live browser inspection and takeover",
    files=(_DRAWER_REL, _CANVAS_REL, _TOOLBAR_REL),
    risk="low",
    category="ui",
    depends_on=("browser_preview_card",),
    why="Provide full-screen / slide-out browser viewport with live canvas and keyboard/mouse injection",
    technical_detail=(
        "Installs BrowserViewerDrawer.tsx, BrowserCanvas.tsx, and BrowserToolbar.tsx in Conversation/components"
    ),
    verify_file=_DRAWER_REL,
    verify_marker="BrowserViewerDrawer",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    for rel, filename in [
        (_DRAWER_REL, "BrowserViewerDrawer.tsx"),
        (_CANVAS_REL, "BrowserCanvas.tsx"),
        (_TOOLBAR_REL, "BrowserToolbar.tsx"),
    ]:
        source = _HERE / filename
        if not source.is_file():
            raise SystemExit(f"[browser_viewer_drawer] missing source: {source}")
        if ctx.write_if_changed(rel, source.read_text(encoding="utf-8")):
            changed = True

    return changed
