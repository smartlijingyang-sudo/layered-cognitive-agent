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
_SOURCE_NAME = "BrowserPreviewCard.tsx"

meta = PatchMeta(
    name="browser_preview_card",
    description="Render interactive BrowserPreviewCard for live browser sessions in chat",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=("cron_task_card_widget",),
    why="Provide Grok/Muse-style live browser card with thumbnail and takeover button in chat stream",
    technical_detail=(
        "Installs BrowserPreviewCard.tsx in Conversation/Messages/components and mounts it in Assistant/index.tsx"
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

    # 注入检测逻辑
    if "isBrowserPreview" not in assistant_text:
        for anchor in (
            "const isCronTaskCard = Boolean(content && content.includes('[widget:cron_task_card'));",
            "const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));",
        ):
            if anchor in assistant_text:
                assistant_text = assistant_text.replace(
                    anchor,
                    "const isBrowserPreview = Boolean(content && content.includes('[widget:browser_preview'));\n    "
                    + anchor,
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

    # 注入 mount
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
                    "              />\n"
                    "            )}\n"
                    f"            {anchor}"
                )
                assistant_text = assistant_text.replace(anchor, mount_repl, 1)
                break

    if ctx.write_if_changed(_ASSISTANT_REL, assistant_text):
        changed = True

    return changed
