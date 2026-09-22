"""Tests for enhanced pre-filter robustness, dotenv loading, and environmental facts."""

from __future__ import annotations

import pytest

from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter
from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter


@pytest.mark.asyncio
async def test_fallback_filter_loads_dotenv_and_detects_facts():
    filter_ = FallbackMemoryFilter()
    # 验证环境事实与偏好不被门禁漏判
    for statement in [
        "生产数据库端口是 5433，只能读不能写",
        "记住：所有代码提交前必须执行 lint",
        "我不喜欢啰嗦，请直接给代码",
    ]:
        decision = await filter_.evaluate(statement)
        assert decision.should_extract is True, f"Failed on: {statement} (reason: {decision.reason})"


@pytest.mark.asyncio
async def test_regex_filter_matches_environmental_and_factual_tokens():
    regex_filter = RegexMemoryFilter()
    for statement in [
        "生产数据库端口是 5433",
        "记住：发布前必须跑单元测试",
        "服务器IP为 10.0.0.1",
        "系统架构规范约定禁止直接读写物理表",
    ]:
        decision = await regex_filter.evaluate(statement)
        assert decision.should_extract is True, f"Failed on: {statement} (reason: {decision.reason})"
