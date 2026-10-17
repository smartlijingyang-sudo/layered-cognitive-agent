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
_THEME_REL = "src/layout/GlobalProvider/AppTheme.tsx"

meta = PatchMeta(
    name="browser_viewer_drawer",
    description="Render right slide-out BrowserViewerDrawer for live browser inspection and takeover",
    files=(_DRAWER_REL, _CANVAS_REL, _TOOLBAR_REL, _THEME_REL),
    risk="low",
    category="ui",
    depends_on=("browser_preview_card",),
    why="Provide full-screen / slide-out browser viewport with live canvas and keyboard/mouse injection",
    technical_detail=(
        "Installs BrowserViewerDrawer.tsx, BrowserCanvas.tsx, and BrowserToolbar.tsx in Conversation/components, "
        "and mounts BrowserViewerDrawer globally in layout/GlobalProvider/AppTheme.tsx"
    ),
    verify_file=_THEME_REL,
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

    # Patch layout/GlobalProvider/AppTheme.tsx for global drawer presence
    theme_text = ctx.read(_THEME_REL)

    # 注入 import
    if "import BrowserViewerDrawer" not in theme_text:
        theme_text = (
            "import BrowserViewerDrawer from '@/features/Conversation/components/BrowserViewerDrawer';\n"
            + theme_text
        )

    # 注入全局抽屉挂载
    mount_marker = "{/* LCA-BROWSER-VIEWER-DRAWER-GLOBAL */}"
    if mount_marker not in theme_text:
        mount_anchor = "            {children}"
        if mount_anchor in theme_text:
            mount_repl = (
                f"{mount_anchor}\n            {mount_marker}\n            <BrowserViewerDrawer />"
            )
            theme_text = theme_text.replace(mount_anchor, mount_repl, 1)

    if ctx.write_if_changed(_THEME_REL, theme_text):
        changed = True

    return changed
