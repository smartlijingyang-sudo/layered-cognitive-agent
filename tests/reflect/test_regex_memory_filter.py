# tests/reflect/test_regex_memory_filter.py
from __future__ import annotations

import pytest

from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter


@pytest.mark.asyncio
async def test_regex_filter_matches_explicit_tokens():
    filter_ = RegexMemoryFilter()
    hit = await filter_.evaluate("我是软件架构师")
    assert hit.should_extract is True
    assert hit.source == "regex"
    assert hit.confidence == 0.8
    assert "matched_tokens" in hit.reason

    miss = await filter_.evaluate("今天天气真不错，执行编译命令")
    assert miss.should_extract is False
    assert miss.source == "regex"
    assert miss.confidence == 0.0
    assert miss.reason == "no_tokens_matched"


@pytest.mark.asyncio
async def test_regex_filter_matches_preference_and_style():
    filter_ = RegexMemoryFilter()
    hit_pref = await filter_.evaluate("以后回答请简洁一点")
    assert hit_pref.should_extract is True
    assert hit_pref.source == "regex"
