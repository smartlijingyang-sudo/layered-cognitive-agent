"""Patch: render MessageReactionBadge on assistant and user message bubbles.

The LCA gateway emits ``reaction_added`` wire events (snake_case fields) which
the runtime patch records in ``reactionStore.ts``. This patch installs
``MessageReactionBadge.tsx`` into ``Conversation/Messages/components`` and
mounts it in both the Assistant and User message components so the aggregated
emoji badges appear on the message bubbles.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/Messages/components/MessageReactionBadge.tsx"
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"
_USER_REL = "src/features/Conversation/Messages/User/index.tsx"
_SOURCE_NAME = "MessageReactionBadge.tsx"

meta = PatchMeta(
    name="message_reaction_badge",
    description="Render emoji reaction badges on assistant and user message bubbles",
    files=(_COMPONENT_REL, _ASSISTANT_REL, _USER_REL),
    risk="low",
    category="ui",
    depends_on=("assistant_avatar_widget",),
    why=(
        "LCA reaction_added gateway events need a visible emoji badge on the "
        "targeted message bubble."
    ),
    technical_detail=(
        "Copies MessageReactionBadge.tsx into Conversation/Messages/components "
        "and mounts it in Assistant/index.tsx and User/index.tsx messageExtra."
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="MessageReactionBadge",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[message_reaction_badge] missing patch source: {source}")
    if ctx.write_if_changed(_COMPONENT_REL, source.read_text(encoding="utf-8")):
        changed = True

    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    import_anchor = "import ConnectorAuthCard from '../components/ConnectorAuthCard';"
    if (
        "import MessageReactionBadge from '../components/MessageReactionBadge';"
        not in assistant_text
    ):
        if import_anchor not in assistant_text:
            raise AssertionError("message_reaction_badge: assistant import anchor not found")
        assistant_text = assistant_text.replace(
            import_anchor,
            import_anchor
            + "\nimport MessageReactionBadge from '../components/MessageReactionBadge';",
            1,
        )

    mount_anchor = (
        "            {isAvatarPickerWidget && (\n"
        "              <AssistantAvatarWidget\n"
        "                assistantId={agentId}\n"
        "              />\n"
        "            )}\n"
        "            <AssistantMessageExtra"
    )
    if "<MessageReactionBadge" not in assistant_text:
        if mount_anchor not in assistant_text:
            raise AssertionError("message_reaction_badge: assistant mount anchor not found")
        assistant_text = assistant_text.replace(
            mount_anchor,
            "            {isAvatarPickerWidget && (\n"
            "              <AssistantAvatarWidget\n"
            "                assistantId={agentId}\n"
            "              />\n"
            "            )}\n"
            "            <MessageReactionBadge messageId={id} />\n"
            "            <AssistantMessageExtra",
            1,
        )

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    user_text = ctx.read(_USER_REL)
    original = user_text

    user_import_anchor = "import ScheduledRunFooter from './ScheduledRunFooter';"
    if "import MessageReactionBadge from '../components/MessageReactionBadge';" not in user_text:
        if user_import_anchor not in user_text:
            raise AssertionError("message_reaction_badge: user import anchor not found")
        user_text = user_text.replace(
            user_import_anchor,
            user_import_anchor
            + "\nimport MessageReactionBadge from '../components/MessageReactionBadge';",
            1,
        )

    user_extra_anchor = (
        "      messageExtra={<UserMessageExtra content={content} extra={extra} id={id} />}"
    )
    if "<MessageReactionBadge" not in user_text:
        if user_extra_anchor not in user_text:
            raise AssertionError("message_reaction_badge: user messageExtra anchor not found")
        user_text = user_text.replace(
            user_extra_anchor,
            "      messageExtra={\n"
            "        <>\n"
            "          <MessageReactionBadge messageId={id} />\n"
            "          <UserMessageExtra content={content} extra={extra} id={id} />\n"
            "        </>\n"
            "      }",
            1,
        )

    if user_text != original:
        ctx.write(_USER_REL, user_text)
        changed = True

    return changed
