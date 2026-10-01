"""Tests for Onboarding scripted opening pacing and greeting (INV-05)."""

from lca.application.onboarding.script import (
    extract_user_name_from_user_md,
    get_onboarding_opening_messages,
)


def test_onboarding_opening_new_user_two_bubbles():
    msgs = get_onboarding_opening_messages(user_state="pending")
    # INV-05: Exactly 2 messages, deterministic wording
    assert len(msgs) == 2
    assert "个人 Agent" in msgs[0]
    assert "接过去" in msgs[0]
    assert "怎么称呼你" in msgs[1]


def test_onboarding_opening_existing_user_greeting():
    msgs = get_onboarding_opening_messages(
        user_state="completed",
        user_name="李超",
        assistant_name="小助",
        role_title="架构分析师",
    )
    assert len(msgs) == 1
    assert "李超" in msgs[0]
    assert "架构分析师" in msgs[0]
    assert "小助" in msgs[0]
    assert "怎么称呼你" not in msgs[0]  # Never asks for name again!


def test_extract_user_name_from_user_md():
    md = "# USER.md\n\n- **Name:** 李超\n- **Role:** 系统架构师\n"
    assert extract_user_name_from_user_md(md) == "李超"

    # Fallback when empty or not matching
    assert extract_user_name_from_user_md("") == ""
    assert extract_user_name_from_user_md("Just random text") == ""
