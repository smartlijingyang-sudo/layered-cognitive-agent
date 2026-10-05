"""govern() 的风格偏好分支在词表迁到 contracts 后行为不变。

这条分支此前没有测试覆盖。迁移把私有 `_VERBOSITY` 换成 contracts 的词表，
本文件钉住迁移前后的可观察行为一致。
"""

from __future__ import annotations

from lca.cognition.memory.govern import govern
from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass

_NOW_MS = 1790439284180


def _govern(task: str) -> EpisodeFact | None:
    return govern(
        task=task,
        trace_id="trace_style",
        lesson=None,
        observation_success=None,
        observation_error=None,
        last_error=None,
        now_ms=_NOW_MS,
    )


def test_verbosity_branch_emits_the_same_triple() -> None:
    fact = _govern("记住，回复要简洁")

    assert fact is not None
    assert fact.category is MemoryCategory.PREFERENCE
    assert fact.dedupe_key == "preference:verbosity"
    assert fact.content == "用户偏好：简洁"
    assert fact.residual is ResidualClass.instruction


def test_authority_stays_false_on_the_template_route() -> None:
    """模板命中不给首次即提升的授权。翻这个位属被否决的 govern 路线，不在本任务。"""
    fact = _govern("以后回复详细一点")

    assert fact is not None
    assert fact.content == "用户偏好：详细"
    assert fact.explicit_user_authority is False


def test_conjunction_gate_is_unchanged() -> None:
    """`记住|以后` 合取门保持不变，无记忆动词的偏好句仍然不落盘。拓宽属 Task 5。"""
    assert _govern("还是简洁一点好") is None
    assert _govern("别那么啰嗦") is None


def test_matched_token_drives_the_content() -> None:
    """content 用的是命中的那个词，不是整句。"""
    fact = _govern("记住：我要啰嗦一点的解释")

    assert fact is not None
    assert fact.content == "用户偏好：啰嗦"
