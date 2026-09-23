"""Patch: room_chat_panel — floating collaboration room list + room chat."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/RoomChatPanel/index.tsx"
_PROVIDER_REL = "src/layout/SPAGlobalProvider/index.tsx"
_SOURCE_NAME = "RoomChatPanel.tsx"

meta = PatchMeta(
    name="room_chat_panel",
    description="Floating panel: collaboration room list + room chat with @mentions",
    files=(_COMPONENT_REL, _PROVIDER_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "Give the browser a minimal room loop: list rooms, read the transcript, "
        "post a message, then watch the folded conclusion arrive."
    ),
    technical_detail=(
        "Copy RoomChatPanel.tsx into src/features/RoomChatPanel/ and mount it "
        "beside LcaHostConsole in SPAGlobalProvider. Uses /lca-api/v1/rooms."
    ),
    verify_file=_PROVIDER_REL,
    verify_marker="RoomChatPanel",
)


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(
        _COMPONENT_REL,
        (_HERE / _SOURCE_NAME).read_text(encoding="utf-8"),
    )

    provider = ctx.read(_PROVIDER_REL)
    if "RoomChatPanel" in provider:
        return changed

    # Import: prefer the host_console-applied state, fall back to upstream.
    import_anchor = "import LcaHostConsole from '@/features/LcaHostConsole';"
    if import_anchor in provider:
        provider = provider.replace(
            import_anchor,
            import_anchor + "\nimport RoomChatPanel from '@/features/RoomChatPanel';",
            1,
        )
    else:
        fallback_import = "import { isDesktop } from '@/const/version';"
        if fallback_import not in provider:
            raise SystemExit("[room_chat_panel] isDesktop import anchor not found")
        provider = provider.replace(
            fallback_import,
            fallback_import + "\nimport RoomChatPanel from '@/features/RoomChatPanel';",
            1,
        )

    # Mount: prefer the host_console-applied state, fall back to upstream.
    mount_anchor = "            <LcaHostConsole />"
    if mount_anchor in provider:
        provider = provider.replace(
            mount_anchor,
            mount_anchor + "\n            <RoomChatPanel />",
            1,
        )
    else:
        fallback_mount = "<DevDockLayout>{content}</DevDockLayout>"
        if fallback_mount not in provider:
            raise SystemExit("[room_chat_panel] DevDockLayout mount anchor not found")
        provider = provider.replace(
            fallback_mount,
            "<DevDockLayout>\n"
            "            {content}\n"
            "            <RoomChatPanel />\n"
            "          </DevDockLayout>",
            1,
        )

    ctx.write(_PROVIDER_REL, provider)
    return True
