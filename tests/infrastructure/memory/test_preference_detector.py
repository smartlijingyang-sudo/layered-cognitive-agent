"""偏好探测的两个轴：显式指令与风格维度。

`is_preference_statement` 决定一行流水算不算偏好，`is_explicit_instruction`
决定它是否带用户授权。两者分开是因为 Phase 0 条件二要求无记忆动词的偏好句
也被捕获，而捕获面一放宽，授权面就不能跟着放宽，否则一次误判就永久提升。
"""

from __future__ import annotations

import pytest

from lca.infrastructure.memory.contextfiles.domain.trail import (
    is_explicit_instruction,
    is_preference_statement,
)


@pytest.mark.parametrize(
    "text",
    ["还是简洁一点好", "别那么啰嗦", "回复请简短", "我喜欢简洁的回复"],
)
def test_style_statements_without_memory_verbs_are_preferences(text: str) -> None:
    """Phase 0 条件二的判据句，全部不含 `记住|以后|偏好` 一类标记。"""
    assert is_preference_statement(text) is True


@pytest.mark.parametrize(
    "text",
    ["还是简洁一点好", "别那么啰嗦", "我喜欢简洁的回复", "这段代码很简洁"],
)
def test_style_topic_alone_is_not_an_explicit_instruction(text: str) -> None:
    """提到风格词不等于用户下了指令。授权面比捕获面窄。"""
    assert is_explicit_instruction(text) is False


@pytest.mark.parametrize(
    "text",
    ["以后回复要简洁", "记住，回复要简洁", "回复要简短一点"],
)
def test_explicit_style_instruction_is_both(text: str) -> None:
    assert is_preference_statement(text) is True
    assert is_explicit_instruction(text) is True


@pytest.mark.parametrize("text", ["以后不要用 emoji", "用户偏好短回复", "请不要这样"])
def test_explicit_non_style_instruction_stays_a_preference(text: str) -> None:
    """既有的显式指令语义不变，拓宽不削弱原有捕获。"""
    assert is_preference_statement(text) is True
    assert is_explicit_instruction(text) is True


@pytest.mark.parametrize("text", ["李雷说项目下周发布", "查询北京天气", "别删那个文件", ""])
def test_ordinary_lines_are_neither(text: str) -> None:
    assert is_preference_statement(text) is False
    assert is_explicit_instruction(text) is False
