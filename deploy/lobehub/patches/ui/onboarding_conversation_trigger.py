"""Patch: trigger proactive Muse-style onboarding greeting when entering empty agent chat."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_HOOK_REL = "src/features/Conversation/hooks/useOnboardingGreeting.ts"
_CONVERSATION_REL = "src/routes/(main)/agent/features/Conversation/ConversationArea.tsx"
_SOURCE_NAME = "useOnboardingGreeting.ts"

meta = PatchMeta(
    name="onboarding_conversation_trigger",
    description="Proactively trigger Muse-style onboarding greeting in ConversationArea",
    files=(_HOOK_REL, _CONVERSATION_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why="Proactively greet new users and prompt for name in ConversationArea",
    technical_detail=(
        "Installs useOnboardingGreeting.ts hook and patches ConversationArea.tsx to invoke it"
    ),
    verify_file=_CONVERSATION_REL,
    verify_marker="useOnboardingGreeting",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    # 1. Write useOnboardingGreeting.ts hook
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[onboarding_conversation_trigger] missing patch source: {source}")
    if ctx.write_if_changed(_HOOK_REL, source.read_text(encoding="utf-8")):
        changed = True

    # 2. Patch ConversationArea.tsx
    conv_text = ctx.read(_CONVERSATION_REL)
    original = conv_text

    import_anchor = "import { useAgentContext } from '@/features/Conversation/useAgentContext';"
    import_repl = (
        "import { useAgentContext } from '@/features/Conversation/useAgentContext';\n"
        "import { useOnboardingGreeting } from '@/features/Conversation/hooks/useOnboardingGreeting';"
    )
    if "import { useOnboardingGreeting }" not in conv_text:
        if import_anchor not in conv_text:
            raise AssertionError("onboarding_conversation_trigger: import anchor not found")
        conv_text = conv_text.replace(import_anchor, import_repl, 1)

    invoke_anchor = "  const messages = useChatStore((s) => s.dbMessagesMap[chatKey]);\n\n  log('contextKey %s: %o', chatKey, messages);"
    invoke_repl = (
        "  const messages = useChatStore((s) => s.dbMessagesMap[chatKey]);\n\n"
        "  useOnboardingGreeting(context, messages);\n\n"
        "  log('contextKey %s: %o', chatKey, messages);"
    )
    if "useOnboardingGreeting(context, messages);" not in conv_text:
        if invoke_anchor not in conv_text:
            raise AssertionError("onboarding_conversation_trigger: invoke anchor not found")
        conv_text = conv_text.replace(invoke_anchor, invoke_repl, 1)

    if conv_text != original:
        ctx.write(_CONVERSATION_REL, conv_text)
        changed = True

    return changed
