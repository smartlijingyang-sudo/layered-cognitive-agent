"""Onboarding scripted opening and greeting logic (INV-05).

Provides deterministic two-bubble pacing for new users,
and proactive personalized greetings for existing users.
"""

from __future__ import annotations

import re

_NAME_PATTERN = re.compile(r"-\s+\*\*Name:\*\*\s*(.+)", re.IGNORECASE)

_NEW_USER_BUBBLE_1_EN = (
    "Hey! I’m your personal agent, not just a regular assistant. "
    "I can help take things off your plate."
)
_NEW_USER_BUBBLE_2_EN = "Before we get started, what’s your name?"

_NEW_USER_BUBBLE_1_ZH = (
    "你好！我是你的专属个人 Agent。\n"
    "我不仅是一个普通的问答助手，更能帮你把手头复杂繁琐的事情接过去。"
)
_NEW_USER_BUBBLE_2_ZH = "在正式开始之前，我该怎么称呼你呢？"


def extract_user_name_from_user_md(user_md: str) -> str:
    """从 USER.md 提取用户的显示称呼。"""
    if not user_md:
        return ""
    match = _NAME_PATTERN.search(user_md)
    if match:
        return match.group(1).strip()
    return ""


def get_onboarding_opening_messages(
    *,
    user_state: str = "pending",
    user_name: str = "",
    assistant_name: str = "小助",
    role_title: str = "专属",
    locale: str = "en",
) -> tuple[str, ...]:
    """返回首轮开场白消息列表。

    - pending (新用户): 返回 2 条消息（立人设 + 询问称谓）；
    - completed (老用户): 返回 1 条个性化打招呼消息，附带起名引导。
    """
    is_zh = locale.strip().lower().startswith("zh")

    if user_state == "pending":
        if is_zh:
            return (_NEW_USER_BUBBLE_1_ZH, _NEW_USER_BUBBLE_2_ZH)
        return (_NEW_USER_BUBBLE_1_EN, _NEW_USER_BUBBLE_2_EN)

    name_label = user_name.strip() or ("朋友" if is_zh else "friend")
    role_label = role_title.strip() or ("专属" if is_zh else "personal")
    asst_label = assistant_name.strip() or ("小助" if is_zh else "Assistant")

    if is_zh:
        greeting = (
            f"你好，{name_label}！我是你的 {role_label} 助理。\n"
            f"你可以直接叫我 {asst_label}，或者在下方定制你想叫我的名字与风格："
        )
    else:
        greeting = (
            f"Hey, {name_label}! I'm your {role_label} agent.\n"
            f"You can call me {asst_label}, or customize my name and vibe below:"
        )
    return (greeting,)


# ── 改名后固定流程（对齐 Muse onboarding 机制）─────────────────────────────
# 固定文案放模块常量，函数只做 locale 选择和变量填充。
# 模型不即兴发挥：庆祝 → 能力介绍 → 连接引导，三步顺序写死。

_POST_NAMING_CELEBRATE_ZH = "{name}，名字不错，我喜欢！"
_POST_NAMING_INTRO_ZH = (
    "关于我，有几件事你可能想知道：\n"
    "• 我有自己的电脑，你不在的时候我也能帮你把事情办了。\n"
    "• 经过你的同意，我可以帮你管邮箱、日历这些应用。"
)
_POST_NAMING_CONNECT_ZH = "想先从连接邮箱开始吗？或者直接告诉我你清单上的其他事。"

_POST_NAMING_CELEBRATE_EN = "{name} it is. I like it."
_POST_NAMING_INTRO_EN = (
    "A few things to know about me:\n"
    "• I have my own computer, so I can get things done while you're away.\n"
    "• With your approval, I can manage apps like your email and calendar."
)
_POST_NAMING_CONNECT_EN = (
    "Want to start by connecting Gmail? Or hand me something else on your list."
)


def get_post_naming_messages(
    *,
    assistant_name: str,
    locale: str = "zh",
) -> tuple[str, ...]:
    """返回改名成功后的固定介绍气泡（庆祝 → 能力介绍 → 连接引导）。

    文案固定，只有名字是变量。前端依次渲染为 assistant 气泡，
    随后展示连接器卡片（由 settle 响应的 show_connectors 触发）。
    """
    is_zh = locale.strip().lower().startswith("zh")
    name = assistant_name.strip() or ("小助" if is_zh else "Assistant")

    if is_zh:
        return (
            _POST_NAMING_CELEBRATE_ZH.format(name=name),
            _POST_NAMING_INTRO_ZH,
            _POST_NAMING_CONNECT_ZH,
        )
    return (
        _POST_NAMING_CELEBRATE_EN.format(name=name),
        _POST_NAMING_INTRO_EN,
        _POST_NAMING_CONNECT_EN,
    )
