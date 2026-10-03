"""Patch: render top animated mascot and right-side status drawer for assistant standing files."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_MASCOT_REL = "src/features/Conversation/components/AssistantTopMascot.tsx"
_DRAWER_REL = "src/features/Conversation/components/AssistantStatusDrawer.tsx"
_EDITOR_REL = "src/features/Conversation/components/StandingFileFullscreenEditor.tsx"
_CONNECTORS_REL = "src/features/Conversation/components/ConnectorsPanel.tsx"
_HEADER_REL = "src/routes/(main)/agent/features/Conversation/Header/index.tsx"

meta = PatchMeta(
    name="assistant_status_drawer",
    description="Render top animated mascot and right-side status drawer for assistant standing files",
    files=(_MASCOT_REL, _DRAWER_REL, _EDITOR_REL, _CONNECTORS_REL, _HEADER_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide Muse-style top animated mascot avatar and right status drawer with file SSOT editor and connectors hub",
    technical_detail=(
        "Installs AssistantTopMascot.tsx, AssistantStatusDrawer.tsx, StandingFileFullscreenEditor.tsx,"
        " and ConnectorsPanel.tsx, then patches agent Conversation Header to display"
        " center breathing Mascot and trigger right-side standing files drawer."
        " Updated dynamic activity modal colors with dark-mode white-gray typography and top-tier aesthetic."
    ),
    verify_file=_HEADER_REL,
    verify_marker="AssistantTopMascot",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 UI 组件
    mascot_source = _HERE / "AssistantTopMascot.tsx"
    if not mascot_source.is_file():
        raise SystemExit(f"[assistant_status_drawer] missing mascot source: {mascot_source}")
    if ctx.write_if_changed(_MASCOT_REL, mascot_source.read_text(encoding="utf-8")):
        changed = True

    drawer_source = _HERE / "AssistantStatusDrawer.tsx"
    if not drawer_source.is_file():
        raise SystemExit(f"[assistant_status_drawer] missing drawer source: {drawer_source}")
    if ctx.write_if_changed(_DRAWER_REL, drawer_source.read_text(encoding="utf-8")):
        changed = True

    editor_source = _HERE / "StandingFileFullscreenEditor.tsx"
    if not editor_source.is_file():
        raise SystemExit(f"[assistant_status_drawer] missing editor source: {editor_source}")
    if ctx.write_if_changed(_EDITOR_REL, editor_source.read_text(encoding="utf-8")):
        changed = True

    connectors_source = _HERE / "ConnectorsPanel.tsx"
    if not connectors_source.is_file():
        raise SystemExit(f"[assistant_status_drawer] missing connectors source: {connectors_source}")
    if ctx.write_if_changed(_CONNECTORS_REL, connectors_source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Conversation Header/index.tsx
    header_text = ctx.read(_HEADER_REL)
    original = header_text

    # 替换 import
    if "AssistantTopMascot" not in header_text:
        header_text = header_text.replace(
            "import { memo } from 'react';",
            (
                "import { memo, useCallback, useState } from 'react';\n"
                "import { agentSelectors } from '@/store/agent/selectors';\n"
                "import AssistantStatusDrawer from '@/features/Conversation/components/AssistantStatusDrawer';\n"
                "import AssistantTopMascot from '@/features/Conversation/components/AssistantTopMascot';\n"
                "import StandingFileFullscreenEditor from '@/features/Conversation/components/StandingFileFullscreenEditor';"
            ),
        )

    # 注入状态机与组件
    target_needle = (
        "const effectiveWorkingDirectory = topicWorkingDirectory || agentWorkingDirectory || '';"
    )
    if target_needle in header_text and "drawerOpen" not in header_text:
        replacement = (
            f"{target_needle}\n\n"
            "  const agentTitle = useAgentStore((s) =>\n"
            "    agentId ? agentSelectors.getAgentMetaById(agentId)(s)?.title : undefined,\n"
            "  );\n\n"
            "  const lcaAssistantId = useAgentStore((s) =>\n"
            "    agentId ? (s.agentMap[agentId] as any)?.agencyConfig?.lcaAssistantId : undefined,\n"
            "  );\n"
            "  const targetAssistantId = lcaAssistantId || agentId;\n\n"
            "  const [drawerOpen, setDrawerOpen] = useState(false);\n"
            "  const [editorOpen, setEditorOpen] = useState(false);\n"
            "  const [editingFile, setEditingFile] = useState<{\n"
            "    filename: string;\n"
            "    filePath?: string;\n"
            "    initialHash?: string;\n"
            "  } | null>(null);\n\n"
            "  const handleEditFile = useCallback((filename: string, fileInfo: any) => {\n"
            "    setEditingFile({\n"
            "      filename,\n"
            "      filePath: fileInfo.path,\n"
            "      initialHash: fileInfo.content_hash,\n"
            "    });\n"
            "    setEditorOpen(true);\n"
            "  }, []);"
        )
        header_text = header_text.replace(target_needle, replacement)

    if "targetAssistantId" not in header_text:
        needle_agent_title = (
            "  const agentTitle = useAgentStore((s) =>\n"
            "    agentId ? agentSelectors.getAgentMetaById(agentId)(s)?.title : undefined,\n"
            "  );"
        )
        if needle_agent_title in header_text:
            header_text = header_text.replace(
                needle_agent_title,
                (
                    "  const agentTitle = useAgentStore((s) =>\n"
                    "    agentId ? agentSelectors.getAgentMetaById(agentId)(s)?.title : undefined,\n"
                    "  );\n\n"
                    "  const lcaAssistantId = useAgentStore((s) =>\n"
                    "    agentId ? (s.agentMap[agentId] as any)?.agencyConfig?.lcaAssistantId : undefined,\n"
                    "  );\n"
                    "  const targetAssistantId = lcaAssistantId || agentId;"
                ),
                1,
            )
            header_text = header_text.replace(
                "<AssistantTopMascot\n            assistantId={agentId}",
                "<AssistantTopMascot\n            assistantId={targetAssistantId}",
                1,
            )
            header_text = header_text.replace(
                "<AssistantStatusDrawer\n        open={drawerOpen}\n        onClose={() => setDrawerOpen(false)}\n        assistantId={agentId}",
                "<AssistantStatusDrawer\n        open={drawerOpen}\n        onClose={() => setDrawerOpen(false)}\n        assistantId={targetAssistantId}",
                1,
            )
            header_text = header_text.replace(
                "<StandingFileFullscreenEditor\n          open={editorOpen}\n          onClose={() => setEditorOpen(false)}\n          assistantId={agentId}",
                "<StandingFileFullscreenEditor\n          open={editorOpen}\n          onClose={() => setEditorOpen(false)}\n          assistantId={targetAssistantId}",
                1,
            )

    # 注入 NavHeader children 与 Drawer / Editor 模态窗
    navheader_close = "slotClassNames={{\n          left: headerStyles.slotLeft,\n          right: headerStyles.slotRight,\n        }}\n      />"
    if navheader_close in header_text and "<AssistantTopMascot" not in header_text:
        navheader_replacement = (
            "slotClassNames={{\n"
            "          left: headerStyles.slotLeft,\n"
            "          right: headerStyles.slotRight,\n"
            "        }}\n"
            "      >\n"
            "        <Flexbox horizontal align={'center'} justify={'center'} style={{ pointerEvents: 'auto' }}>\n"
            "          <AssistantTopMascot\n"
            "            assistantId={targetAssistantId}\n"
            "            name={agentTitle || '架构小助'}\n"
            "            onOpenDrawer={() => setDrawerOpen(true)}\n"
            "          />\n"
            "        </Flexbox>\n"
            "      </NavHeader>\n\n"
            "      <AssistantStatusDrawer\n"
            "        open={drawerOpen}\n"
            "        onClose={() => setDrawerOpen(false)}\n"
            "        assistantId={targetAssistantId}\n"
            "        assistantName={agentTitle || '架构小助'}\n"
            "        onEditFile={handleEditFile}\n"
            "      />\n\n"
            "      {editingFile && (\n"
            "        <StandingFileFullscreenEditor\n"
            "          open={editorOpen}\n"
            "          onClose={() => setEditorOpen(false)}\n"
            "          assistantId={targetAssistantId}\n"
            "          assistantName={agentTitle || '架构小助'}\n"
            "          filename={editingFile.filename}\n"
            "          filePath={editingFile.filePath}\n"
            "          initialHash={editingFile.initialHash}\n"
            "        />\n"
            "      )}"
        )
        header_text = header_text.replace(navheader_close, navheader_replacement)

    if header_text != original:
        ctx.write(_HEADER_REL, header_text)
        changed = True

    return changed
