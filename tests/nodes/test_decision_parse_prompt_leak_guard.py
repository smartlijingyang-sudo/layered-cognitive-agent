"""Tests for decision.parse prompt leak guard (INV-OUTPUT-01).

Guards against model attention slips that regurgitate internal prompt sections
(such as Deferred tool namespaces, 记忆写入与写盘铁律, 未检索标注).

RA-116: leak inputs are derived from the canonical marker seam
(``lca.contracts.models.cognition.prompt_leak_markers``) instead of
hardcoding copies, so the test exercises the real producer strings and the
guard pattern is verified to be built from the seam.
"""

from lca.contracts.models.cognition.prompt_leak_markers import (
    DEFER_CATALOG_HEADER,
    LEAK_MARKER_PATTERNS,
    MEMORY_WRITE_RULES_HEADER,
    UNRETRIEVED_LABEL,
)
from lca.nodes.think.decision.parse import _LEAK_CUTOFF_REGEX, _guard_prompt_leak


def _leaked_catalog_block() -> str:
    """A realistic model regurgitation of prompt-internal sections.

    Built from the seam constants so the test tracks the real producer
    strings (session.py / memory.py) rather than hardcoded copies.
    """
    return (
        f"（{UNRETRIEVED_LABEL}：以上工具属于 agent 命名空间，需通过 tool_search 延迟检索后使用）\n\n"
        f"{DEFER_CATALOG_HEADER}\n"
        "- agent: 助理元数据维护与管理\n\n"
        f"{MEMORY_WRITE_RULES_HEADER}\n"
        "1. 不得虚假断言已经写入记忆..."
    )


def test_guard_prompt_leak_preserves_clean_text() -> None:
    """Normal conversational text without prompt leakage remains unchanged."""
    text = "你好！很高兴为您服务。请问需要创建哪种类型的助理？"
    cleaned = _guard_prompt_leak(text)
    assert cleaned == text


def test_guard_prompt_leak_strips_trailing_prompt_regurgitation() -> None:
    """When model generates normal text followed by leaked prompt sections,
    the leaked prompt section is cleanly stripped off.
    """
    text = "好的，我来帮您创建一个新闻研究助理。\n\n" + _leaked_catalog_block()
    cleaned = _guard_prompt_leak(text)
    assert cleaned == "好的，我来帮您创建一个新闻研究助理。"


def test_guard_prompt_leak_replaces_pure_leak_with_safe_fallback() -> None:
    """When model regurgitates 100% prompt text without normal conversation,
    it is replaced with a clean, user-friendly fallback message.
    """
    text = _leaked_catalog_block()
    cleaned = _guard_prompt_leak(text)
    assert cleaned is not None
    assert "Deferred tool namespaces" not in cleaned
    assert "记忆写入与写盘铁律" not in cleaned
    assert "稍候" in cleaned or "处理" in cleaned


def test_guard_pattern_built_from_seam_markers() -> None:
    """RA-116: the guard pattern is built from the seam's canonical list.

    Every live marker fragment appears in the compiled pattern; the three
    dead markers (## 认知闭集 / ## 核心不变量 / ## 系统指令) are gone.
    """
    pattern = _LEAK_CUTOFF_REGEX.pattern
    for fragment in LEAK_MARKER_PATTERNS:
        assert fragment in pattern, fragment
    for dead in ("认知闭集", "核心不变量", "系统指令"):
        assert dead not in pattern, dead
