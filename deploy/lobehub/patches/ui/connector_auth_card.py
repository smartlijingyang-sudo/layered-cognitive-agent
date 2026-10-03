"""Patch: render interactive ConnectorAuthCard for Composio & external integrations.

Renders high-grade interactive OAuth authorization cards in the chat flow whenever
Composio connection requests or links are emitted, replacing bare links with
popup authorization and automatic connection state polling.
Supports intentId (Zero Model URL Exposure, INV-CAP-05).
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/ConnectorAuthCard.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "ConnectorAuthCard.tsx"

meta = PatchMeta(
    name="connector_auth_card",
    description="Render interactive ConnectorAuthCard for Composio & external integrations",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=("assistant_naming_widget",),
    why="Replace raw text links with beautiful interactive OAuth authorization card in chat",
    technical_detail=(
        "Installs ConnectorAuthCard.tsx in Conversation/Messages/components and mounts it in Assistant/index.tsx"
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="ConnectorAuthCard",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 ConnectorAuthCard.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[connector_auth_card] missing patch source: {source}")
    content = source.read_text(encoding="utf-8")
    if ctx.write_if_changed(_COMPONENT_REL, content):
        changed = True
    else:
        ctx._record(_COMPONENT_REL)

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    # 注入 import
    import_anchor = "import AssistantNamingWidget from '../components/AssistantNamingWidget';"
    import_repl = (
        "import AssistantNamingWidget from '../components/AssistantNamingWidget';\n"
        "import ConnectorAuthCard from '../components/ConnectorAuthCard';"
    )
    if "import ConnectorAuthCard from '../components/ConnectorAuthCard';" not in assistant_text:
        if import_anchor not in assistant_text:
            raise AssertionError("connector_auth_card: AssistantNamingWidget import anchor not found")
        assistant_text = assistant_text.replace(import_anchor, import_repl, 1)

    # 升级或注入解析逻辑 (支持 intentId & 生产域名 connect.composio.dev & 裸链接脱敏)
    parse_anchor = (
        "    const cleanContent = isNamingWidget\n"
        "      ? content.replace(/\\[widget:name_picker\\?token=[^\\]]+\\]/g, '').trim()\n"
        "      : content;"
    )

    old_parse_block = (
        "    const isConnectorAuthWidget = Boolean(\n"
        "      content &&\n"
        "        (content.includes('[widget:connector_auth') ||\n"
        "          content.includes('composio.dev/api/v1/auth/redirect') ||\n"
        "          content.includes('backend.composio.dev')),\n"
        "    );\n"
        "    let connectorAuthProps: { appName?: string; authUrl?: string; connectionId?: string } | null = null;\n"
        "    if (isConnectorAuthWidget && content) {\n"
        "      const widgetMatch = content.match(/\\[widget:connector_auth\\?([^\\]]+)\\]/);\n"
        "      if (widgetMatch) {\n"
        "        const params = new URLSearchParams(widgetMatch[1]);\n"
        "        connectorAuthProps = {\n"
        "          appName: params.get('appName') || 'Gmail',\n"
        "          authUrl: params.get('authUrl') || '',\n"
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
        "    let cleanContent = isNamingWidget\n"
        "      ? content.replace(/\\[widget:name_picker\\?token=[^\\]]+\\]/g, '').trim()\n"
        "      : content;\n"
        "    if (isConnectorAuthWidget && cleanContent) {\n"
        "      cleanContent = cleanContent.replace(/\\[widget:connector_auth\\?[^\\]]+\\]/g, '').trim();\n"
        "    }"
    )

    new_parse_repl = (
        "    const isConnectorAuthWidget = Boolean(\n"
        "      content &&\n"
        "        (content.includes('[widget:connector_auth') ||\n"
        "          content.includes('connect.composio.dev') ||\n"
        "          content.includes('composio.dev/api/v1/auth/redirect') ||\n"
        "          content.includes('backend.composio.dev')),\n"
        "    );\n"
        "    let connectorAuthProps: { appName?: string; authUrl?: string; intentId?: string; connectionId?: string } | null = null;\n"
        "    if (isConnectorAuthWidget && content) {\n"
        "      const widgetMatch = content.match(/\\[widget:connector_auth\\?([^\\]]+)\\]/);\n"
        "      if (widgetMatch) {\n"
        "        const params = new URLSearchParams(widgetMatch[1]);\n"
        "        const intentId = params.get('intentId') || '';\n"
        "        connectorAuthProps = {\n"
        "          appName: params.get('appName') || 'Gmail',\n"
        "          authUrl: intentId || params.get('authUrl') || '',\n"
        "          intentId: intentId,\n"
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
        "    let cleanContent = isNamingWidget\n"
        "      ? content.replace(/\\[widget:name_picker\\?token=[^\\]]+\\]/g, '').trim()\n"
        "      : content;\n"
        "    if (isConnectorAuthWidget && cleanContent) {\n"
        "      cleanContent = cleanContent.replace(/\\[widget:connector_auth\\?[^\\]]+\\]/g, '').trim();\n"
        "    }"
    )

    if old_parse_block in assistant_text:
        assistant_text = assistant_text.replace(old_parse_block, new_parse_repl, 1)
    elif "connectorAuthProps" not in assistant_text and parse_anchor in assistant_text:
        assistant_text = assistant_text.replace(parse_anchor, new_parse_repl, 1)

    # 注入 messageExtra 挂载
    naming_widget_mount = (
        "            {isNamingWidget && (\n"
        "              <AssistantNamingWidget\n"
        "                assistantId={agentId}\n"
        "                embedToken={namingToken}\n"
        "              />\n"
        "            )}"
    )
    connector_mount_repl = (
        f"{naming_widget_mount}\n"
        "            {connectorAuthProps && (\n"
        "              <ConnectorAuthCard\n"
        "                appName={connectorAuthProps.appName}\n"
        "                authUrl={connectorAuthProps.authUrl}\n"
        "                connectionId={connectorAuthProps.connectionId}\n"
        "              />\n"
        "            )}"
    )

    if "<ConnectorAuthCard" not in assistant_text and naming_widget_mount in assistant_text:
        assistant_text = assistant_text.replace(naming_widget_mount, connector_mount_repl, 1)

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed
