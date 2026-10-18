"""Patch: render interactive BrowserPreviewCard for live browser sessions.

Part of Grok Bot / Meta Muse alignment (ADR-0248 §5.3 / s13):
Renders a compact browser preview card in chat stream with live title, URL, and takeover buttons.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/BrowserPreviewCard.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_CONTENT_BLOCK_REL = "src/features/Conversation/Messages/AssistantGroup/components/ContentBlock.tsx"
_GROUP_REL = "src/features/Conversation/Messages/AssistantGroup/components/Group.tsx"
_SOURCE_NAME = "BrowserPreviewCard.tsx"

meta = PatchMeta(
    name="browser_preview_card",
    description="Render interactive BrowserPreviewCard for live browser sessions in chat",
    files=(_COMPONENT_REL, _ASSISTANT_REL, _CONTENT_BLOCK_REL, _GROUP_REL),
    risk="low",
    category="ui",
    depends_on=("cron_task_card_widget",),
    why="Provide Grok/Muse-style live browser card with thumbnail and takeover button in chat stream",
    technical_detail=(
        "Installs BrowserPreviewCard.tsx and mounts it beside the assistant answer, outside the collapsed process fold"
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="BrowserPreviewCard",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 BrowserPreviewCard.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[browser_preview_card] missing patch source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)

    # 注入 import
    if "import BrowserPreviewCard from '../components/BrowserPreviewCard';" not in assistant_text:
        for anchor in (
            "import CronTaskCard from '../components/CronTaskCard';",
            "import AssistantNamingWidget from '../components/AssistantNamingWidget';",
        ):
            if anchor in assistant_text:
                assistant_text = assistant_text.replace(
                    anchor,
                    f"{anchor}\nimport BrowserPreviewCard from '../components/BrowserPreviewCard';",
                    1,
                )
                break

    # 注入检测逻辑（支持 widget 标签以及 tools 属性中的 browser 工具）
    browser_tools_detect = "['browser_open', 'browser_navigate', 'browser_spawn_task', 'browser_steer_task', 'browser_transfer_task']"
    new_is_browser_preview = (
        f"const isBrowserPreview = Boolean(content && content.includes('[widget:browser_preview')) || Boolean(tools && tools.some((t: any) => t?.apiName && {browser_tools_detect}.includes(t.apiName)));"
    )

    if "const isBrowserPreview" in assistant_text:
        # 升级已有判定
        assistant_text = assistant_text.replace(
            "const isBrowserPreview = Boolean(content && content.includes('[widget:browser_preview'));",
            new_is_browser_preview,
            1,
        )
    else:
        for anchor in (
            "const isCronTaskCard = Boolean(content && content.includes('[widget:cron_task_card'));",
            "const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));",
        ):
            if anchor in assistant_text:
                assistant_text = assistant_text.replace(
                    anchor,
                    new_is_browser_preview + "\n    " + anchor,
                    1,
                )
                break

    # 注入 cleanContent 去掉标签
    if "isBrowserPreview && cleanContent" not in assistant_text:
        for anchor in (
            "if (isCronTaskCard && cleanContent) {",
            "if (isNamingWidget && cleanContent) {",
        ):
            if anchor in assistant_text:
                assistant_text = assistant_text.replace(
                    anchor,
                    "if (isBrowserPreview && cleanContent) {\n"
                    "      cleanContent = cleanContent.replace(/\\[widget:browser_preview\\?[^\\]]+\\]/g, '').trim();\n"
                    "    }\n    " + anchor,
                    1,
                )
                break

    # 注入 mount（携带 tools）
    if "<BrowserPreviewCard\n                content={content}\n                tools={tools}" not in assistant_text:
        if "<BrowserPreviewCard\n                content={content}\n              />" in assistant_text:
            assistant_text = assistant_text.replace(
                "<BrowserPreviewCard\n                content={content}\n              />",
                "<BrowserPreviewCard\n                content={content}\n                tools={tools}\n              />",
                1,
            )
        else:
            mount_marker = "{/* LCA-BROWSER-PREVIEW-MOUNT */}"
            if mount_marker not in assistant_text:
                for anchor in (
                    "{/* LCA-CRON-TASK-CARD-MOUNT */}",
                    "{/* LCA-AVATAR-PICKER-MOUNT */}",
                ):
                    if anchor in assistant_text:
                        mount_repl = (
                            f"{mount_marker}\n"
                            "            {isBrowserPreview && (\n"
                            "              <BrowserPreviewCard\n"
                            "                content={content}\n"
                            "                tools={tools}\n"
                            "              />\n"
                            "            )}\n"
                            f"            {anchor}"
                        )
                        assistant_text = assistant_text.replace(anchor, mount_repl, 1)
                        break

    if ctx.write_if_changed(_ASSISTANT_REL, assistant_text):
        changed = True

    # 3. Patch ContentBlock.tsx (使得 AssistantGroup child-block 也能渲染卡片)
    cb_text = ctx.read(_CONTENT_BLOCK_REL)
    if "import BrowserPreviewCard" not in cb_text:
        cb_anchor = "import ConnectorAuthCard from '../../components/ConnectorAuthCard';"
        if cb_anchor in cb_text:
            cb_text = cb_text.replace(
                cb_anchor,
                f"{cb_anchor}\nimport BrowserPreviewCard from '../../components/BrowserPreviewCard';",
                1,
            )

    # Tool-driven cards mount once on Group, outside the collapsed process fold.
    # ContentBlock only reacts when the answer text itself carries the widget tag.
    cb_detect = (
        "    const isBrowserPreview = Boolean(typeof content === 'string' && content.includes('[widget:browser_preview'));\n"
    )
    cb_detect_with_tools = (
        "    const isBrowserPreview = Boolean((typeof content === 'string' && content.includes('[widget:browser_preview')) "
        f"|| (tools && tools.some((t: any) => t?.apiName && {browser_tools_detect}.includes(t.apiName))));\n"
    )
    if cb_detect_with_tools in cb_text:
        cb_text = cb_text.replace(cb_detect_with_tools, cb_detect, 1)
    elif "const isBrowserPreview" not in cb_text:
        cb_detect_anchor = "    const showMessageContent = hasContent || content === LOADING_FLAT || hasTools;"
        if cb_detect_anchor in cb_text:
            cb_text = cb_text.replace(cb_detect_anchor, cb_detect + cb_detect_anchor, 1)

    cb_mount = (
        "        {isBrowserPreview && (\n"
        "          <SafeBoundary>\n"
        "            <BrowserPreviewCard content={typeof content === 'string' ? content : undefined} tools={tools} />\n"
        "          </SafeBoundary>\n"
        "        )}\n"
    )
    if "<BrowserPreviewCard" not in cb_text:
        cb_mount_anchor = "        {showImageItems && ("
        if cb_mount_anchor in cb_text:
            cb_text = cb_text.replace(cb_mount_anchor, cb_mount + cb_mount_anchor, 1)

    if ctx.write_if_changed(_CONTENT_BLOCK_REL, cb_text):
        changed = True

    # 4. Mount one card on the assistant group, outside ProcessFold.
    # The fold defaults to collapsed and unmounts the tool block, so a card
    # that lives only inside ContentBlock never reaches the screen.
    group_text = ctx.read(_GROUP_REL)
    group_import = "import BrowserPreviewCard from '../../components/BrowserPreviewCard';"
    if group_import not in group_text:
        group_import_anchor = "import GroupItem from './GroupItem';"
        if group_import_anchor not in group_text:
            raise SystemExit("[browser_preview_card] Group.tsx missing import anchor")
        group_text = group_text.replace(
            group_import_anchor,
            f"{group_import_anchor}\n{group_import}",
            1,
        )

    group_marker = "{/* LCA-BROWSER-PREVIEW-GROUP */}"
    if group_marker not in group_text:
        tools_anchor = (
            "    const durationText =\n"
            "      turnDurationMs >= 1000 ? formatReasoningDuration(turnDurationMs) : undefined;\n"
        )
        tools_insert = (
            tools_anchor
            + "\n"
            + "    const browserPreviewTools = blocks.flatMap((block) =>\n"
            + "      (block.tools ?? []).filter((tool) =>\n"
            + "        tool?.apiName &&\n"
            + f"        {browser_tools_detect}.includes(tool.apiName),\n"
            + "      ),\n"
            + "    );\n"
        )
        if tools_anchor not in group_text:
            raise SystemExit("[browser_preview_card] Group.tsx missing tools anchor")
        group_text = group_text.replace(tools_anchor, tools_insert, 1)

        mount_anchor = (
            "          )}\n"
            "        </Flexbox>\n"
            "      </MessageAggregationContext>\n"
        )
        mount_insert = (
            "          )}\n"
            f"          {group_marker}\n"
            "          {browserPreviewTools.length > 0 && (\n"
            "            <BrowserPreviewCard tools={browserPreviewTools} />\n"
            "          )}\n"
            "        </Flexbox>\n"
            "      </MessageAggregationContext>\n"
        )
        if mount_anchor not in group_text:
            raise SystemExit("[browser_preview_card] Group.tsx missing mount anchor")
        group_text = group_text.replace(mount_anchor, mount_insert, 1)

    if ctx.write_if_changed(_GROUP_REL, group_text):
        changed = True

    return changed
