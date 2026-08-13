"""Patch: host_console — floating local-host terminal panel."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent

meta = PatchMeta(
    name="host_console",
    description="Floating panel: Presence device + Console PTY",
    files=(
        "src/features/LcaHostConsole/index.tsx",
        "src/layout/SPAGlobalProvider/index.tsx",
    ),
    risk="low",
    category="ui",
    depends_on=(),
    why="Local host sidecar is a stack capability; UI only projects it",
    technical_detail="Copy LcaHostConsole; mount it beside DevDockLayout.",
    verify_file="src/layout/SPAGlobalProvider/index.tsx",
    verify_marker="LcaHostConsole",
)


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(
        "src/features/LcaHostConsole/index.tsx",
        (_HERE / "LcaHostConsole.tsx").read_text(encoding="utf-8"),
    )
    rel = "src/layout/SPAGlobalProvider/index.tsx"
    text = ctx.read(rel)
    if "LcaHostConsole" in text:
        return changed
    old_import = "import { isDesktop } from '@/const/version';\n"
    new_import = (
        "import { isDesktop } from '@/const/version';\n"
        "import LcaHostConsole from '@/features/LcaHostConsole';\n"
    )
    if old_import not in text:
        raise SystemExit("[host_console] isDesktop import anchor not found")
    text = text.replace(old_import, new_import, 1)
    old_mount = "<DevDockLayout>{content}</DevDockLayout>"
    new_mount = (
        "<DevDockLayout>\n"
        "            {content}\n"
        "            <LcaHostConsole />\n"
        "          </DevDockLayout>"
    )
    if old_mount not in text:
        raise SystemExit("[host_console] DevDockLayout mount anchor not found")
    ctx.write(rel, text.replace(old_mount, new_mount, 1))
    return True
