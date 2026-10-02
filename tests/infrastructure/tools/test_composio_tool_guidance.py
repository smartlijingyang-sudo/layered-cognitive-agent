"""Tests for Composio tool guidance and Gmail overview recommendations (INV-02)."""

from __future__ import annotations

from lca.infrastructure.tools.composio import (
    _TOOL_GUIDANCE_OVERRIDES,
    MANAGEMENT_MANIFEST,
    _augment_tool_description,
)


def test_management_manifest_contracts() -> None:
    apis = {api.name: api for api in MANAGEMENT_MANIFEST.api}
    assert "composioConnect" in apis
    assert "composioRefresh" in apis
    assert apis["composioConnect"].namespace == "ext"
    assert apis["composioRefresh"].namespace == "ext"


def test_gmail_tool_guidance_overrides() -> None:
    fetch_desc = _TOOL_GUIDANCE_OVERRIDES.get("GMAIL_FETCH_EMAILS", "")
    assert "max_results" in fetch_desc
    assert "GMAIL_LIST_THREADS" in fetch_desc

    threads_desc = _TOOL_GUIDANCE_OVERRIDES.get("GMAIL_LIST_THREADS", "")
    assert "PREFERRED" in threads_desc or "preferred" in threads_desc.lower()


def test_augment_tool_description_fallback_and_override() -> None:
    # Overridden tool
    desc = _augment_tool_description("GMAIL_FETCH_EMAILS", "Raw description")
    assert "max_results" in desc

    # Un-overridden tool keeps original description
    desc_other = _augment_tool_description("SLACK_SEND_MESSAGE", "Original slack desc")
    assert desc_other == "Original slack desc"
