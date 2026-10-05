"""风格偏好词表与维度键归 contracts 单一 owner。

`govern()`（cognition）与 `_trail_episode`（infrastructure）需要同一份「这段文本
指的是哪个回复风格维度」的判定。infrastructure 不能向上导入 cognition，所以词表
与维度键落在两者都能导入的 contracts 层。
"""

from __future__ import annotations

from lca.contracts.models.memory.episode import (
    STYLE_PREFERENCE_DIMENSION,
    matched_style_token,
)


def test_style_token_is_found_in_a_preference_statement() -> None:
    assert matched_style_token("还是简洁一点好") == "简洁"
    assert matched_style_token("别那么啰嗦") == "啰嗦"
    assert matched_style_token("我要详细的说明") == "详细"


def test_non_style_text_matches_nothing() -> None:
    assert matched_style_token("查询北京天气") is None
    assert matched_style_token("") is None


def test_task_5_widened_the_vocabulary_to_the_criterion_sentences() -> None:
    """Task 1 钉住的边界在 Task 5 显式放宽，`简短` 进词表。"""
    assert matched_style_token("回复请简短") == "简短"
    assert matched_style_token("我喜欢简洁的回复") == "简洁"


def test_widening_stays_bounded() -> None:
    """放宽只加了 `简短`。不含风格词的表述仍然不命中。"""
    assert matched_style_token("我喜欢言简意赅的回复") is None
    assert matched_style_token("说短一点") is None
    assert matched_style_token("别删那个文件") is None


def test_first_vocabulary_entry_wins() -> None:
    """多个风格词同时出现时取值确定，不依赖调用方顺序。"""
    assert matched_style_token("要简洁还是详细") == "简洁"


def test_dimension_key_matches_what_govern_emits() -> None:
    """维度键就是 `govern()` 与 `canonical_dedupe_key` 已经在用的那一个字面量。"""
    assert STYLE_PREFERENCE_DIMENSION == "preference:verbosity"
