"""Patch: render interactive AssistantAvatarWidget for generated-image candidate picker.

Fetches candidates from ``GET /v1/assistants/{id}/avatar/candidates``, activates
the selected one via ``POST /v1/assistants/{id}/avatar/set``, broadcasts
``lca-assistant-avatar-changed`` and shows first-person success feedback.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantAvatarWidget.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "AssistantAvatarWidget.tsx"

meta = PatchMeta(
    name="assistant_avatar_widget",
    description="Render interactive AssistantAvatarWidget for generated-image candidate picker",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=("connector_auth_card",),
    why="Provide generated-image avatar candidate picker cards in chat backed by the avatar REST API",
    technical_detail=(
        "Installs AssistantAvatarWidget.tsx in Conversation/Messages/components and mounts it in Assistant/index.tsx"
    ),
    verify_file=_COMPONENT_REL,
    verify_marker="avatar/candidates",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 AssistantAvatarWidget.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[assistant_avatar_widget] missing patch source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    # 注入 import
    import_anchor = "import ConnectorAuthCard from '../components/ConnectorAuthCard';"
    import_repl = (
        "import ConnectorAuthCard from '../components/ConnectorAuthCard';\n"
        "import AssistantAvatarWidget from '../components/AssistantAvatarWidget';"
    )
    if (
        "import AssistantAvatarWidget from '../components/AssistantAvatarWidget';"
        not in assistant_text
    ):
        if import_anchor not in assistant_text:
            raise SystemExit("assistant_avatar_widget: ConnectorAuthCard import anchor not found")
        assistant_text = assistant_text.replace(import_anchor, import_repl, 1)

    # 注入检测逻辑
    detect_anchor = (
        "    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));"
    )
    detect_repl = (
        "    const isAvatarPickerWidget = Boolean(\n"
        "      content &&\n"
        "        (content.includes('[widget:avatar_picker') ||\n"
        "          (content.includes('恐龙') && (content.includes('卡片') || content.includes('选'))) ||\n"
        "          (content.includes('形象') && (content.includes('卡片') || content.includes('候选')))),\n"
        "    );\n"
        "    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));"
    )
    if "isAvatarPickerWidget" not in assistant_text and detect_anchor in assistant_text:
        assistant_text = assistant_text.replace(detect_anchor, detect_repl, 1)

    # 注入 cleanContent 去掉标签
    clean_anchor = "      cleanContent = cleanContent.replace(/\\[widget:connector_auth\\?[^\\]]+\\]/g, '').trim();\n    }"
    clean_repl = (
        "      cleanContent = cleanContent.replace(/\\[widget:connector_auth\\?[^\\]]+\\]/g, '').trim();\n"
        "    }\n"
        "    if (isAvatarPickerWidget && cleanContent) {\n"
        "      cleanContent = cleanContent.replace(/\\[widget:avatar_picker\\?[^\\]]+\\]/g, '').trim();\n"
        "    }"
    )
    if (
        "isAvatarPickerWidget && cleanContent" not in assistant_text
        and clean_anchor in assistant_text
    ):
        assistant_text = assistant_text.replace(clean_anchor, clean_repl, 1)

    # 注入 messageExtra 挂载
    mount_anchor = (
        "            {connectorAuthProps && (\n"
        "              <ConnectorAuthCard\n"
        "                appName={connectorAuthProps.appName}\n"
        "                authUrl={connectorAuthProps.authUrl}\n"
        "                connectionId={connectorAuthProps.connectionId}\n"
        "              />\n"
        "            )}"
    )
    mount_repl = (
        f"{mount_anchor}\n"
        "            {isAvatarPickerWidget && (\n"
        "              <AssistantAvatarWidget\n"
        "                assistantId={agentId}\n"
        "              />\n"
        "            )}"
    )
    if "<AssistantAvatarWidget" not in assistant_text and mount_anchor in assistant_text:
        assistant_text = assistant_text.replace(mount_anchor, mount_repl, 1)

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed
