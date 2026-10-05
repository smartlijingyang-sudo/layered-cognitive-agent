"""govern() 的闭合模板只捕获单个子句。

回归锁：生产 home ``asst_5166b058964f`` 的 ``memory/episodes/ep_dc6df2f81fd6d9e3.json``
存着 ``用户身份：老李,做架构设计,偏好 Python,回复请简短。写进你的长期记忆。``，
``dedupe_key=identity:name`` 且 ``explicit_user_authority=true``。贪婪 ``(.+)``
把一整句多事实陈述折进一条身份记录，并带上用户授权，因此 ``_lifecycle`` 首次即提升，
之后不再被重新审视。
"""

from __future__ import annotations

from lca.cognition.memory.govern import govern
from lca.contracts.models.memory.episode import EpisodeFact

_NOW_MS = 1790439284180


def _govern(task: str) -> EpisodeFact | None:
    return govern(
        task=task,
        trace_id="trace_govern_boundary",
        lesson=None,
        observation_success=None,
        observation_error=None,
        last_error=None,
        now_ms=_NOW_MS,
    )


def test_name_template_stops_at_the_first_clause() -> None:
    fact = _govern("我叫老李,做架构设计,偏好 Python,回复请简短。写进你的长期记忆。")

    assert fact is not None
    assert fact.content == "用户身份：老李"
    assert fact.dedupe_key == "identity:name"
    assert fact.explicit_user_authority is True


def test_role_template_stops_at_the_first_clause() -> None:
    fact = _govern("我是架构师，主要做后端，喜欢 Python")

    assert fact is not None
    assert fact.content == "用户身份：架构师"
    assert fact.dedupe_key == "identity:role"


def test_folded_facts_never_reach_the_record() -> None:
    """被折进来的其余子句既不属于身份，也不能借身份记录的用户授权落盘。"""
    fact = _govern("我叫老李,做架构设计,偏好 Python,回复请简短。写进你的长期记忆。")

    assert fact is not None
    for fragment in ("做架构设计", "偏好 Python", "回复请简短", "长期记忆"):
        assert fragment not in fact.content


def test_single_clause_capture_is_unchanged() -> None:
    """既有行为锁：无子句标点时捕获整段，与 profile 级测试的断言一致。"""
    role = _govern("我是架构师")
    name = _govern("叫我老李")

    assert role is not None
    assert role.content == "用户身份：架构师"
    assert role.dedupe_key == "identity:role"
    assert name is not None
    assert name.content == "用户身份：老李"
    assert name.dedupe_key == "identity:name"


def test_enumeration_comma_stays_inside_one_capture() -> None:
    """顿号是名词短语内的列举，不是子句边界。"""
    fact = _govern("我是架构师、技术负责人")

    assert fact is not None
    assert fact.content == "用户身份：架构师、技术负责人"
