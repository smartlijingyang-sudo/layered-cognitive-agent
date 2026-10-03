"""Patch: render interactive CronTaskCard in chat stream for cron notifications and tasks (Task 5).

Mounts ``CronTaskCard.tsx`` in Conversation components, strips ``[widget:cron_task_card]``
from chat text display, and renders the rich interactive task card with inline snooze,
edit, delete, and pause capabilities.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/CronTaskCard.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "CronTaskCard.tsx"

meta = PatchMeta(
    name="cron_task_card_widget",
    description="Render interactive CronTaskCard in chat stream for cron notifications and tasks",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why="Provide in-chat interactive task cards with instant snooze, edit, and delete actions",
    technical_detail=(
        "Installs CronTaskCard.tsx in Conversation/Messages/components, mounts it in "
        "Assistant/index.tsx next to LCA-CRON-TASK-CARD-MOUNT comment marker."
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="CronTaskCard",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. 写入 CronTaskCard.tsx 组件
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[cron_task_card_widget] missing source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)

    # 注入 import
    import_anchor = "import ConnectorAuthCard from '../components/ConnectorAuthCard';"
    import_repl = (
        "import ConnectorAuthCard from '../components/ConnectorAuthCard';\n"
        "import CronTaskCard from '../components/CronTaskCard';"
    )
    if (
        "import CronTaskCard from '../components/CronTaskCard';" not in assistant_text
        and import_anchor in assistant_text
    ):
        assistant_text = assistant_text.replace(import_anchor, import_repl, 1)

    # 注入检测逻辑
    detect_anchor = "const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));"
    detect_repl = (
        "const isCronTaskCard = Boolean(content && content.includes('[widget:cron_task_card'));\n"
        "    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));"
    )
    if "isCronTaskCard" not in assistant_text and detect_anchor in assistant_text:
        assistant_text = assistant_text.replace(detect_anchor, detect_repl, 1)

    # 注入 cleanContent 去掉标签
    clean_anchor = "if (isNamingWidget && cleanContent) {"
    clean_repl = (
        "if (isCronTaskCard && cleanContent) {\n"
        "      cleanContent = cleanContent.replace(/\\[widget:cron_task_card\\][\\s\\S]*?\\[\\/widget:cron_task_card\\]/g, '').trim();\n"
        "    }\n"
        "    if (isNamingWidget && cleanContent) {"
    )
    if "isCronTaskCard && cleanContent" not in assistant_text and clean_anchor in assistant_text:
        assistant_text = assistant_text.replace(clean_anchor, clean_repl, 1)

    # 注入 mount
    mount_marker = "{/* LCA-CRON-TASK-CARD-MOUNT */}"
    if mount_marker not in assistant_text:
        # 在 </Flexbox> 或 messageExtra 之后挂载
        mount_anchor = "{/* LCA-AVATAR-PICKER-MOUNT */}"
        if mount_anchor in assistant_text:
            mount_repl = (
                f"{mount_marker}\n"
                "            {isCronTaskCard && (\n"
                "              <CronTaskCard\n"
                "                content={content}\n"
                "                assistantId={agentId}\n"
                "              />\n"
                "            )}\n"
                f"            {mount_anchor}"
            )
            assistant_text = assistant_text.replace(mount_anchor, mount_repl, 1)

    if ctx.write_if_changed(_ASSISTANT_REL, assistant_text):
        changed = True

    return changed
