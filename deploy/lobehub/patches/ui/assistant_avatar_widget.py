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
_CONTENT_BLOCK_REL = "src/features/Conversation/Messages/AssistantGroup/components/ContentBlock.tsx"
_SOURCE_NAME = "AssistantAvatarWidget.tsx"

meta = PatchMeta(
    name="assistant_avatar_widget",
    description="Render interactive AssistantAvatarWidget for generated-image candidate picker",
    files=(_COMPONENT_REL, _ASSISTANT_REL, _CONTENT_BLOCK_REL),
    risk="low",
    category="ui",
    depends_on=("connector_auth_card",),
    why="Provide generated-image avatar candidate picker cards in chat backed by the avatar REST API",
    technical_detail=(
        "Installs AssistantAvatarWidget.tsx in Conversation/Messages/components, mounts it in "
        "Assistant/index.tsx next to a LCA-AVATAR-PICKER-MOUNT comment marker, and mounts it in "
        "AssistantGroup/components/ContentBlock.tsx so group child-block final answers strip the "
        "[widget:avatar_picker] tag and render the picker card. Verifies the mount marker (not just "
        "the component file) so reverts of Assistant/index.tsx are detected."
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="LCA-AVATAR-PICKER-MOUNT",
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
        "      cleanContent = cleanContent.replace(/\\[widget:avatar_picker(?:\\?[^\\]]+)?\\]/g, '').trim();\n"
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
        "            {/* LCA-AVATAR-PICKER-MOUNT */}\n"
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

    # 3. Patch ContentBlock.tsx (assistantGroup child-block final answer)
    cb_text = ctx.read(_CONTENT_BLOCK_REL)
    cb_original = cb_text

    # import
    cb_import_anchor = "import MessageContent from './MessageContent';"
    cb_import_repl = (
        "import MessageContent from './MessageContent';\n"
        "import AssistantAvatarWidget from '../../components/AssistantAvatarWidget';"
    )
    if "import AssistantAvatarWidget from '../../components/AssistantAvatarWidget';" not in cb_text:
        if cb_import_anchor not in cb_text:
            raise SystemExit(
                "assistant_avatar_widget: ContentBlock MessageContent import anchor not found"
            )
        cb_text = cb_text.replace(cb_import_anchor, cb_import_repl, 1)

    # detection / cleanContent / agentId
    cb_detect_anchor = (
        "    const showMessageContent = hasContent || content === LOADING_FLAT || hasTools;"
    )
    cb_detect_repl = (
        "    const isAvatarPickerWidget = Boolean(\n"
        "      content &&\n"
        "        (content.includes('[widget:avatar_picker') ||\n"
        "          (content.includes('恐龙') && (content.includes('卡片') || content.includes('选'))) ||\n"
        "          (content.includes('形象') && (content.includes('卡片') || content.includes('候选')))),\n"
        "    );\n"
        "    const avatarPickerCleanContent =\n"
        "      isAvatarPickerWidget && typeof content === 'string'\n"
        "        ? content.replace(/\\[widget:avatar_picker(?:\\?[^\\]]+)?\\]/g, '').trim()\n"
        "        : content;\n"
        "    const avatarGroupAgentId = useConversationStore(\n"
        "      (s) => dataSelectors.getDisplayMessageById(assistantId)(s)?.agentId,\n"
        "    );\n"
        "    const showMessageContent = hasContent || content === LOADING_FLAT || hasTools;"
    )
    if "isAvatarPickerWidget" not in cb_text:
        if cb_detect_anchor not in cb_text:
            raise SystemExit(
                "assistant_avatar_widget: ContentBlock showMessageContent anchor not found"
            )
        cb_text = cb_text.replace(cb_detect_anchor, cb_detect_repl, 1)

    # render cleaned content in MessageContent
    cb_override_anchor = (
        "            <MessageContent\n              contentOverride={contentOverride}"
    )
    cb_override_repl = (
        "            <MessageContent\n"
        "              contentOverride={isAvatarPickerWidget ? avatarPickerCleanContent : contentOverride}"
    )
    if (
        "contentOverride={isAvatarPickerWidget ? avatarPickerCleanContent : contentOverride}"
        not in cb_text
    ):
        if cb_override_anchor not in cb_text:
            raise SystemExit(
                "assistant_avatar_widget: ContentBlock MessageContent contentOverride anchor not found"
            )
        cb_text = cb_text.replace(cb_override_anchor, cb_override_repl, 1)

    # mount the widget below the cleaned content block
    cb_mount_anchor = (
        "        {showMessageContent && (\n"
        '          <SafeBoundary variant="alert">\n'
        "            <MessageContent\n"
        "              contentOverride={isAvatarPickerWidget ? avatarPickerCleanContent : contentOverride}\n"
        "              disableStreaming={disableMarkdownStreaming}\n"
        "              hasToolsOverride={hasToolsOverride}\n"
        "              id={id}\n"
        "            />\n"
        "          </SafeBoundary>\n"
        "        )}"
    )
    cb_mount_repl = (
        f"{cb_mount_anchor}\n"
        "        {isAvatarPickerWidget && avatarGroupAgentId && (\n"
        "          <SafeBoundary>\n"
        "            <AssistantAvatarWidget assistantId={avatarGroupAgentId} />\n"
        "          </SafeBoundary>\n"
        "        )}"
    )
    if "<AssistantAvatarWidget" not in cb_text:
        if cb_mount_anchor not in cb_text:
            raise SystemExit("assistant_avatar_widget: ContentBlock render block anchor not found")
        cb_text = cb_text.replace(cb_mount_anchor, cb_mount_repl, 1)

    if cb_text != cb_original:
        ctx.write(_CONTENT_BLOCK_REL, cb_text)
        changed = True

    return changed
