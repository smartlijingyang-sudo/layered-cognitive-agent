"""Tests for onboarding_conversation_trigger patch (ADR-0252 / Onboarding ceremony).

Validates patch discovery, metadata contract, hook source presence, and ConversationArea integration.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import discover_patches


def test_onboarding_conversation_trigger_discovered() -> None:
    modules = discover_patches()
    by_name = {m.meta.name: m for m in modules}
    assert "onboarding_conversation_trigger" in by_name

    patch = by_name["onboarding_conversation_trigger"]
    assert patch.meta.category == "ui"
    assert "useOnboardingGreeting" in patch.meta.verify_marker
    assert "src/features/Conversation/hooks/useOnboardingGreeting.ts" in patch.meta.files
    assert (
        "src/routes/(main)/agent/features/Conversation/ConversationArea.tsx"
        in patch.meta.files
    )


def test_use_onboarding_greeting_source_contract() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "lobehub"
        / "patches"
        / "ui"
        / "useOnboardingGreeting.ts"
    )
    assert source.is_file(), f"Missing hook source: {source}"
    content = source.read_text(encoding="utf-8")
    assert "useOnboardingGreeting" in content
    assert "optimisticCreateMessage" in content
    assert "lca_greeted_" in content
    assert "/lca-api/v1/onboarding/welcome" in content


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
