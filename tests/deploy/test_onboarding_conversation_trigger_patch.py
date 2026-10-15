"""Tests for onboarding_conversation_trigger patch (ADR-0252 / Onboarding ceremony).

Validates patch discovery, metadata contract, hook source presence, the pure
greeting-ordering helper, and ConversationArea integration.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import discover_patches

_HOOK_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "lobehub"
    / "patches"
    / "ui"
    / "useOnboardingGreeting.ts"
)
_HELPER_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "lobehub"
    / "patches"
    / "ui"
    / "onboardingGreeting.ts"
)
_TEST_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "lobehub"
    / "patches"
    / "ui"
    / "onboardingGreeting.test.ts"
)


def test_onboarding_conversation_trigger_discovered() -> None:
    modules = discover_patches()
    by_name = {m.meta.name: m for m in modules}
    assert "onboarding_conversation_trigger" in by_name

    patch = by_name["onboarding_conversation_trigger"]
    assert patch.meta.category == "ui"
    assert "useOnboardingGreeting" in patch.meta.verify_marker
    assert "src/features/Conversation/hooks/useOnboardingGreeting.ts" in patch.meta.files
    assert "src/features/Conversation/hooks/onboardingGreeting.ts" in patch.meta.files
    assert "src/features/Conversation/hooks/onboardingGreeting.test.ts" in patch.meta.files
    assert "src/routes/(main)/agent/features/Conversation/ConversationArea.tsx" in patch.meta.files


def test_use_onboarding_greeting_source_contract() -> None:
    assert _HOOK_SOURCE.is_file(), f"Missing hook source: {_HOOK_SOURCE}"
    content = _HOOK_SOURCE.read_text(encoding="utf-8")
    assert "useOnboardingGreeting" in content
    assert "buildOnboardingGreetingMessages" in content
    assert "messageService.createMessage" in content
    assert "createdAt" in content
    assert "lca_greeted_" in content
    assert "/lca-api/v1/onboarding/welcome" in content


def test_onboarding_greeting_helper_source_contract() -> None:
    assert _HELPER_SOURCE.is_file(), f"Missing helper source: {_HELPER_SOURCE}"
    content = _HELPER_SOURCE.read_text(encoding="utf-8")
    assert "buildOnboardingGreetingMessages" in content
    assert "createdAt" in content


def test_onboarding_greeting_vitest_source_present() -> None:
    assert _TEST_SOURCE.is_file(), f"Missing vitest source: {_TEST_SOURCE}"
    content = _TEST_SOURCE.read_text(encoding="utf-8")
    assert "buildOnboardingGreetingMessages" in content
    assert "backdates greeting bubbles" in content


def test_deployed_conversation_area_has_trigger() -> None:
    conv_file = (
        Path(__file__).resolve().parents[2]
        / "lobehub-ui"
        / "src"
        / "routes"
        / "(main)"
        / "agent"
        / "features"
        / "Conversation"
        / "ConversationArea.tsx"
    )
    assert conv_file.is_file(), f"Missing deployed ConversationArea.tsx: {conv_file}"
    content = conv_file.read_text(encoding="utf-8")
    assert "import { useOnboardingGreeting }" in content
    assert "useOnboardingGreeting(context, messages);" in content


def test_deployed_greeting_helper_and_test_present() -> None:
    ui_root = Path(__file__).resolve().parents[2] / "lobehub-ui"
    helper = ui_root / "src/features/Conversation/hooks/onboardingGreeting.ts"
    vitest = ui_root / "src/features/Conversation/hooks/onboardingGreeting.test.ts"
    assert helper.is_file(), f"Missing deployed helper: {helper}"
    assert vitest.is_file(), f"Missing deployed vitest: {vitest}"
