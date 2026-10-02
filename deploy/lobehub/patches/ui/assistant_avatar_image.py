"""Patch: render AssistantAvatarImage (active avatar) in header and message bubbles.

Consumes ``GET /v1/assistants/{id}/avatar`` (Task 6) and listens for
``lca-assistant-avatar-changed`` (dispatched by the Task 7 WS client) so the
active generated avatar appears in the conversation header and the assistant
message bubbles, falling back to the existing SVG mascot when no avatar is
active.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantAvatarImage.tsx"
_HEADER_REL = "src/routes/(main)/agent/features/Conversation/Header/index.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "AssistantAvatarImage.tsx"

meta = PatchMeta(
    name="assistant_avatar_image",
    description=(
        "Render AssistantAvatarImage (active avatar) in conversation header and message bubbles"
    ),
    files=(_COMPONENT_REL, _HEADER_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=("assistant_avatar_widget", "assistant_status_drawer"),
    why=(
        "Show the generated active avatar image (GET /v1/assistants/{id}/avatar) "
        "in the conversation header and assistant message bubbles, falling back "
        "to the SVG mascot when no avatar is active"
    ),
    technical_detail=(
        "Installs AssistantAvatarImage.tsx in Conversation/Messages/components, "
        "mounts it in the agent Conversation Header (replacing the center mascot "
        "when active) and in Assistant/index.tsx via ChatItem customAvatarRender."
    ),
    verify_file=_COMPONENT_REL,
    verify_marker="AssistantAvatarImage",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 AssistantAvatarImage.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[assistant_avatar_image] missing patch source: {source}")
    text = source.read_text(encoding="utf-8")
    try:
        current = ctx.read(_COMPONENT_REL)
    except FileNotFoundError:
        current = None
    # Always ``write`` (which registers the file in the manifest) even when
    # content is unchanged: reconcile clears ``written`` on a patch source SHA
    # change, and an unchanged new file would otherwise lose its manifest
    # coverage and show up as drift.
    ctx.write(_COMPONENT_REL, text)
    if current != text:
        changed = True

    # 2. Conversation Header：active 头像存在时替换中心 Mascot，否则回退 Mascot
    header_text = ctx.read(_HEADER_REL)
    original_header = header_text

    if "import AssistantAvatarImage" not in header_text:
        import_anchor = "import AssistantTopMascot from '@/features/Conversation/components/AssistantTopMascot';"
        if import_anchor not in header_text:
            raise SystemExit("[assistant_avatar_image] Header mascot import anchor not found")
        header_text = header_text.replace(
            import_anchor,
            import_anchor
            + "\nimport AssistantAvatarImage from "
            + "'@/features/Conversation/Messages/components/AssistantAvatarImage';",
            1,
        )

    if "<AssistantAvatarImage" not in header_text:
        mascot_anchor = (
            "          <AssistantTopMascot\n"
            "            assistantId={targetAssistantId}\n"
            "            name={agentTitle || '架构小助'}\n"
            "            onOpenDrawer={() => setDrawerOpen(true)}\n"
            "          />"
        )
        if mascot_anchor not in header_text:
            raise SystemExit("[assistant_avatar_image] Header AssistantTopMascot anchor not found")
        mascot_repl = (
            "          <AssistantAvatarImage\n"
            "            assistantId={targetAssistantId}\n"
            "            size={42}\n"
            "            fallback={\n"
            "              <AssistantTopMascot\n"
            "                assistantId={targetAssistantId}\n"
            "                name={agentTitle || '架构小助'}\n"
            "                onOpenDrawer={() => setDrawerOpen(true)}\n"
            "              />\n"
            "            }\n"
            "          />"
        )
        header_text = header_text.replace(mascot_anchor, mascot_repl, 1)

    if header_text != original_header:
        ctx.write(_HEADER_REL, header_text)
        changed = True

    # 3. 消息气泡：ChatItem customAvatarRender 换成 AssistantAvatarImage
    assistant_text = ctx.read(_ASSISTANT_REL)
    original_assistant = assistant_text

    if "import AssistantAvatarImage" not in assistant_text:
        import_anchor = "import AssistantAvatarWidget from '../components/AssistantAvatarWidget';"
        if import_anchor not in assistant_text:
            raise SystemExit(
                "[assistant_avatar_image] AssistantAvatarWidget import anchor not found"
            )
        assistant_text = assistant_text.replace(
            import_anchor,
            import_anchor
            + "\nimport AssistantAvatarImage from '../components/AssistantAvatarImage';",
            1,
        )

    if "customAvatarRender" not in assistant_text:
        chat_anchor = (
            "        avatar={avatar}\n"
            "        belowMessage={hasEmptyErrorMessage ? footerRender : undefined}"
        )
        if chat_anchor not in assistant_text:
            raise SystemExit("[assistant_avatar_image] ChatItem avatar anchor not found")
        chat_repl = (
            "        avatar={avatar}\n"
            "        customAvatarRender={(_, node) => (\n"
            '          <AssistantAvatarImage assistantId={agentId} size={36} shape="square" fallback={node} />\n'
            "        )}\n"
            "        belowMessage={hasEmptyErrorMessage ? footerRender : undefined}"
        )
        assistant_text = assistant_text.replace(chat_anchor, chat_repl, 1)

    if assistant_text != original_assistant:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed
