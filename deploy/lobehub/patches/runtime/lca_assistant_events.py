"""Patch: avatar event WS client (assistantEventClient) for avatar refresh.

Copies ``assistantEventClient.ts`` (+ vitest) into
``src/store/chat/agents/transports/lcaGateway/`` and mounts
``AssistantEventClient`` in the agent Conversation Header so
``avatar_updated`` / ``avatar_video_ready`` push the active avatar to
``AssistantAvatarImage``.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_UI_TRANSPORTS = "src/store/chat/agents/transports"
_LCA_GATEWAY_DIR = f"{_UI_TRANSPORTS}/lcaGateway"
_HEADER_REL = "src/routes/(main)/agent/features/Conversation/Header/index.tsx"

_NEW_FILES = (
    "assistantEventClient.ts",
    "assistantEventClient.test.ts",
)


def _modified_files() -> tuple[str, ...]:
    rels = [_HEADER_REL]
    for fname in _NEW_FILES:
        rels.append(f"{_LCA_GATEWAY_DIR}/{fname}")
    return tuple(rels)


meta = PatchMeta(
    name="lca_assistant_events",
    description="LCA avatar event WebSocket client + conversation header mount",
    files=_modified_files(),
    risk="low",
    category="runtime",
    depends_on=("assistant_status_drawer",),
    why=(
        "Push avatar_updated / avatar_video_ready from "
        "/v1/assistants/{id}/events to the frontend so AssistantAvatarImage "
        "refetches the active avatar"
    ),
    technical_detail=(
        "Copies assistantEventClient.ts (+ vitest) into "
        "src/store/chat/agents/transports/lcaGateway/ and mounts "
        "AssistantEventClient in the conversation Header."
    ),
    verify_file=f"{_LCA_GATEWAY_DIR}/assistantEventClient.ts",
    verify_marker="export class AssistantEventClient",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    for fname in _NEW_FILES:
        rel = f"{_LCA_GATEWAY_DIR}/{fname}"
        src = _HERE / "lcaGateway" / fname
        if not src.is_file():
            raise SystemExit(f"[lca_assistant_events] missing patch source: {src}")
        text = src.read_text(encoding="utf-8")
        try:
            current = ctx.read(rel)
        except FileNotFoundError:
            current = None
        # Always ``write`` (which registers the file in the manifest) even
        # when content is unchanged: reconcile clears ``written`` on a patch
        # source SHA change, and an unchanged file would otherwise lose its
        # manifest coverage and show up as drift.
        ctx.write(rel, text)
        if current != text:
            changed = True

    header_text = ctx.read(_HEADER_REL)
    original = header_text

    # 1. 注入 useEffect + AssistantEventClient import
    react_import = "import { memo, useCallback, useState } from 'react';"
    if react_import in header_text:
        header_text = header_text.replace(
            react_import,
            "import { memo, useCallback, useEffect, useState } from 'react';",
            1,
        )

    if "import { AssistantEventClient }" not in header_text:
        import_anchor = "import AssistantTopMascot from '@/features/Conversation/components/AssistantTopMascot';"
        if import_anchor not in header_text:
            raise SystemExit(
                "[lca_assistant_events] Header AssistantTopMascot import anchor not found"
            )
        header_text = header_text.replace(
            import_anchor,
            import_anchor
            + "\nimport { AssistantEventClient } from "
            + "'@/store/chat/agents/transports/lcaGateway/assistantEventClient';",
            1,
        )

    # 2. 消息页挂载：useEffect 里 new AssistantEventClient(assistantId).connect()
    if "new AssistantEventClient(targetAssistantId)" not in header_text:
        mount_anchor = (
            "  const handleEditFile = useCallback((filename: string, fileInfo: any) => {\n"
            "    setEditingFile({\n"
            "      filename,\n"
            "      filePath: fileInfo.path,\n"
            "      initialHash: fileInfo.content_hash,\n"
            "    });\n"
            "    setEditorOpen(true);\n"
            "  }, []);"
        )
        if mount_anchor not in header_text:
            raise SystemExit("[lca_assistant_events] handleEditFile mount anchor not found")
        mount_repl = mount_anchor + (
            "\n\n"
            "  // LCA: 连接 avatar 事件 WS；avatar_updated / avatar_video_ready 到达时\n"
            "  // AssistantAvatarImage 监听 lca-assistant-avatar-changed 自动刷新头像。\n"
            "  useEffect(() => {\n"
            "    if (!targetAssistantId) return;\n"
            "    const client = new AssistantEventClient(targetAssistantId);\n"
            "    client.connect();\n"
            "    return () => client.disconnect();\n"
            "  }, [targetAssistantId]);"
        )
        header_text = header_text.replace(mount_anchor, mount_repl, 1)

    if header_text != original:
        ctx.write(_HEADER_REL, header_text)
        changed = True

    return changed
