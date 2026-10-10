"""Tests for decision.parse prompt leak guard (INV-OUTPUT-01).

Guards against model attention slips that regurgitate internal prompt sections
(such as Deferred tool namespaces, 记忆写入与写盘铁律, 未检索标注).
"""

from lca.nodes.think.decision.parse import _guard_prompt_leak


def test_guard_prompt_leak_preserves_clean_text() -> None:
    """Normal conversational text without prompt leakage remains unchanged."""
    text = "你好！很高兴为您服务。请问需要创建哪种类型的助理？"
    cleaned = _guard_prompt_leak(text)
    assert cleaned == text


def test_guard_prompt_leak_strips_trailing_prompt_regurgitation() -> None:
    """When model generates normal text followed by leaked prompt sections,
    the leaked prompt section is cleanly stripped off.
    """
    text = (
        "好的，我来帮您创建一个新闻研究助理。\n\n"
        "（未检索标注：以上工具属于 agent 命名空间，需通过 tool_search 延迟检索后使用）\n\n"
        "Deferred tool namespaces (call tool_search(namespace='...') before using):\n"
        "- agent: 助理元数据维护与管理\n\n"
        "## 记忆写入与写盘铁律\n"
        "1. 不得虚假断言已经写入记忆..."
    )
    cleaned = _guard_prompt_leak(text)
    assert cleaned == "好的，我来帮您创建一个新闻研究助理。"


def test_guard_prompt_leak_replaces_pure_leak_with_safe_fallback() -> None:
    """When model regurgitates 100% prompt text without normal conversation,
    it is replaced with a clean, user-friendly fallback message.
    """
    text = (
        "Deferred tool namespaces (call tool_search(namespace='...') before using):\n"
        "- agent: 助理元数据维护与管理\n\n"
        "## 记忆写入与写盘铁律\n"
        "1. 不得虚假断言已经写入记忆..."
    )
    cleaned = _guard_prompt_leak(text)
    assert cleaned is not None
    assert "Deferred tool namespaces" not in cleaned
    assert "记忆写入与写盘铁律" not in cleaned
    assert "稍候" in cleaned or "处理" in cleaned
