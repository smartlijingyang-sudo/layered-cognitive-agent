"""Patch: render ConnectorAuthCard inside AssistantGroup child-block final answers.

The composioConnect flow emits ``[widget:connector_auth?...]`` from an assistant
message that is part of a tool-using chain. LobeHub's conversation-flow wraps
tool-using chains into an ``assistantGroup`` virtual message rendered by
``AssistantGroupMessage`` -> ``ContentBlock``, which previously had no connector
widget handling, so the tag leaked as plain text and no authorization card
appeared. This patch adds the same detection / tag-stripping / card mount that
``connector_auth_card`` provides for the standalone ``AssistantMessage`` path.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_CONTENT_BLOCK_REL = "src/features/Conversation/Messages/AssistantGroup/components/ContentBlock.tsx"

meta = PatchMeta(
    name="connector_auth_group_card",
    description="Render ConnectorAuthCard inside AssistantGroup child-block final answers",
    files=(_CONTENT_BLOCK_REL,),
    risk="low",
    category="ui",
    depends_on=("assistant_avatar_widget",),
    why="composioConnect emits [widget:connector_auth] from a tool-using chain rendered by ContentBlock, which leaked the tag as plain text",
    technical_detail=(
        "Adds ConnectorAuthCard import, [widget:connector_auth] detection, tag "
        "stripping, and the card mount to ContentBlock.tsx so connector auth "
        "cards render in assistantGroup final answers (the composioConnect path)."
    ),
    verify_file=_CONTENT_BLOCK_REL,
    verify_marker="ConnectorAuthCard",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    cb_text = ctx.read(_CONTENT_BLOCK_REL)
    cb_original = cb_text

    # 1. 注入 ConnectorAuthCard import
    import_anchor = "import AssistantAvatarWidget from '../../components/AssistantAvatarWidget';"
    import_repl = (
        "import AssistantAvatarWidget from '../../components/AssistantAvatarWidget';\n"
        "import ConnectorAuthCard from '../../components/ConnectorAuthCard';"
    )
    if "import ConnectorAuthCard from '../../components/ConnectorAuthCard';" not in cb_text:
        if import_anchor not in cb_text:
            raise SystemExit(
                "connector_auth_group_card: AssistantAvatarWidget import anchor not found"
            )
        cb_text = cb_text.replace(import_anchor, import_repl, 1)

    # 2. 注入检测逻辑 + 标签剥离（挂在 avatarGroupAgentId 之前）
    detect_anchor = (
        "    const avatarGroupAgentId = useConversationStore(\n"
        "      (s) => dataSelectors.getDisplayMessageById(assistantId)(s)?.agentId,\n"
        "    );"
    )
    detect_repl = (
        "    const isConnectorAuthWidget = Boolean(\n"
        "      content &&\n"
        "        (content.includes('[widget:connector_auth') ||\n"
        "          content.includes('connect.composio.dev') ||\n"
        "          content.includes('composio.dev/api/v1/auth/redirect') ||\n"
        "          content.includes('backend.composio.dev')),\n"
        "    );\n"
        "    let connectorAuthProps: {\n"
        "      appName?: string;\n"
        "      authUrl?: string;\n"
        "      intentId?: string;\n"
        "      connectionId?: string;\n"
        "    } | null = null;\n"
        "    if (isConnectorAuthWidget && typeof content === 'string') {\n"
        "      const widgetMatch = content.match(/\\[widget:connector_auth\\?([^\\]]+)\\]/);\n"
        "      if (widgetMatch) {\n"
        "        const params = new URLSearchParams(widgetMatch[1]);\n"
        "        const intentId = params.get('intentId') || '';\n"
        "        connectorAuthProps = {\n"
        "          appName: params.get('appName') || 'Gmail',\n"
        "          authUrl: intentId || params.get('authUrl') || '',\n"
        "          intentId,\n"
        "          connectionId: params.get('connectionId') || '',\n"
        "        };\n"
        "      } else {\n"
        "        const urlMatch = content.match(/https?:\\/\\/[^\\s\\)\\\"\\'\\>]+composio\\.dev[^\\s\\)\\\"\\'\\>]*/);\n"
        "        if (urlMatch) {\n"
        "          const authUrl = urlMatch[0];\n"
        "          const tokenMatch = authUrl.match(/token=([^&]+)/);\n"
        "          const lower = content.toLowerCase();\n"
        "          const appName = lower.includes('github') ? 'GitHub' : lower.includes('slack') ? 'Slack' : lower.includes('drive') ? 'Google Drive' : 'Gmail';\n"
        "          connectorAuthProps = {\n"
        "            appName,\n"
        "            authUrl,\n"
        "            connectionId: tokenMatch ? tokenMatch[1] : undefined,\n"
        "          };\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "    const connectorAuthCleanContent =\n"
        "      isConnectorAuthWidget && typeof content === 'string'\n"
        "        ? content.replace(/\\[widget:connector_auth\\?[^\\]]+\\]/g, '').trim()\n"
        "        : content;\n"
        "    const avatarGroupAgentId = useConversationStore(\n"
        "      (s) => dataSelectors.getDisplayMessageById(assistantId)(s)?.agentId,\n"
        "    );"
    )
    if "isConnectorAuthWidget" not in cb_text:
        if detect_anchor not in cb_text:
            raise SystemExit(
                "connector_auth_group_card: ContentBlock avatarGroupAgentId anchor not found"
            )
        cb_text = cb_text.replace(detect_anchor, detect_repl, 1)

    # 3. MessageContent 渲染剥离后的内容
    override_anchor = "              contentOverride={isAvatarPickerWidget ? avatarPickerCleanContent : contentOverride}"
    override_repl = (
        "              contentOverride={\n"
        "                isAvatarPickerWidget\n"
        "                  ? avatarPickerCleanContent\n"
        "                  : isConnectorAuthWidget\n"
        "                    ? connectorAuthCleanContent\n"
        "                    : contentOverride\n"
        "              }"
    )
    if (
        "isConnectorAuthWidget\n                    ? connectorAuthCleanContent" not in cb_text
        and override_anchor in cb_text
    ):
        cb_text = cb_text.replace(override_anchor, override_repl, 1)

    # 4. 在内容块下方挂载 ConnectorAuthCard
    mount_anchor = (
        "        {isAvatarPickerWidget && avatarGroupAgentId && (\n"
        "          <SafeBoundary>\n"
        "            <AssistantAvatarWidget assistantId={avatarGroupAgentId} />\n"
        "          </SafeBoundary>\n"
        "        )}"
    )
    mount_repl = (
        f"{mount_anchor}\n"
        "        {connectorAuthProps && (\n"
        "          <SafeBoundary>\n"
        "            <ConnectorAuthCard\n"
        "              appName={connectorAuthProps.appName}\n"
        "              authUrl={connectorAuthProps.authUrl}\n"
        "              intentId={connectorAuthProps.intentId}\n"
        "              connectionId={connectorAuthProps.connectionId}\n"
        "            />\n"
        "          </SafeBoundary>\n"
        "        )}"
    )
    if "<ConnectorAuthCard" not in cb_text:
        if mount_anchor not in cb_text:
            raise SystemExit(
                "connector_auth_group_card: ContentBlock avatar mount anchor not found"
            )
        cb_text = cb_text.replace(mount_anchor, mount_repl, 1)

    if cb_text != cb_original:
        ctx.write(_CONTENT_BLOCK_REL, cb_text)
        changed = True

    return changed
