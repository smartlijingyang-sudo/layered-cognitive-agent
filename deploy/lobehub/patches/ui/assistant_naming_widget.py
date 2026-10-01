"""Patch: render interactive AssistantNamingWidget for assistant naming ceremony.

Part of Conversational Onboarding and Assistant Naming ceremony (ADR-0252 / Muse alignment):
Allows users to click candidate name chips or enter a custom name during onboarding,
providing real-time preview, confirmation, and celebratory reaction feedback.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/AssistantNamingWidget.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_SOURCE_NAME = "AssistantNamingWidget.tsx"

meta = PatchMeta(
    name="assistant_naming_widget",
    description="Render interactive AssistantNamingWidget for assistant naming ceremony",
    files=(_COMPONENT_REL, _ASSISTANT_REL),
    risk="low",
    category="ui",
    depends_on=("collaboration_team_bar",),
    why="Provide Muse-style interactive naming widget and celebratory reaction in LobeHub onboarding",
    technical_detail=(
        "Creates AssistantNamingWidget.tsx in Conversation/Messages/components and mounts it in Assistant/index.tsx"
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="AssistantNamingWidget",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. Write AssistantNamingWidget.tsx component
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[assistant_naming_widget] missing patch source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch Assistant/index.tsx
    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    # Import
    import_anchor = "import CollaborationTeamBar from '../components/CollaborationTeamBar';"
    import_repl = (
        "import CollaborationTeamBar from '../components/CollaborationTeamBar';\n"
        "import AssistantNamingWidget from '../components/AssistantNamingWidget';"
    )
    if "import AssistantNamingWidget from '../components/AssistantNamingWidget';" not in assistant_text:
        if import_anchor not in assistant_text:
            raise AssertionError("assistant_naming_widget: import anchor not found")
        assistant_text = assistant_text.replace(import_anchor, import_repl, 1)

    # Content extraction and cleaning
    msg_anchor = "    // remove line breaks in artifact tag to make the ast transform easier\n    const message = !editing ? normalizeThinkTags(processWithArtifact(content)) : content;"
    msg_repl = (
        "    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));\n"
        "    const namingToken = isNamingWidget\n"
        "      ? (content.match(/\\[widget:name_picker\\?token=([^\\]]+)\\]/) || [])[1]\n"
        "      : undefined;\n"
        "    const cleanContent = isNamingWidget\n"
        "      ? content.replace(/\\[widget:name_picker\\?token=[^\\]]+\\]/g, '').trim()\n"
        "      : content;\n\n"
        "    // remove line breaks in artifact tag to make the ast transform easier\n"
        "    const message = !editing ? normalizeThinkTags(processWithArtifact(cleanContent)) : content;"
    )
    if "const isNamingWidget" not in assistant_text:
        if msg_anchor not in assistant_text:
            raise AssertionError("assistant_naming_widget: message transform anchor not found")
        assistant_text = assistant_text.replace(msg_anchor, msg_repl, 1)

    # Mount in messageExtra
    extra_anchor = "        messageExtra={\n          <>\n            {interrupted && <InterruptedHint />}"
    extra_repl = (
        "        messageExtra={\n          <>\n            {interrupted && <InterruptedHint />}\n"
        "            {isNamingWidget && (\n"
        "              <AssistantNamingWidget\n"
        "                assistantId={agentId}\n"
        "                embedToken={namingToken}\n"
        "              />\n"
        "            )}"
    )
    if "<AssistantNamingWidget" not in assistant_text:
        if extra_anchor not in assistant_text:
            raise AssertionError("assistant_naming_widget: messageExtra anchor not found")
        assistant_text = assistant_text.replace(extra_anchor, extra_repl, 1)

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed
