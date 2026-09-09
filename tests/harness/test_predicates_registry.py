"""ADR-0214 §6 PR-C: predicate registry 行为契约。

锁定四条不变量:
1. ``register`` + ``resolve`` roundtrip。
2. ``resolve`` 未注册 → ``None``。
3. ``known_predicates`` 返回 sorted tuple。
4. built-in ``perceive.has_minimum_context`` / ``perceive.context_complete``
   真值表符合 task spec(见 ADR-0214 §6.4)。
"""

from __future__ import annotations

import pytest

from lca.harness.graph import predicates
from lca.harness.graph.predicates import (
    perceive_context_complete,
    perceive_has_minimum_context,
)
from lca.harness.graph.traversal import PhaseTraversal


@pytest.fixture(autouse=True)
def _preserve_registry():
    """Snapshot built-ins before each test, restore after.

    Built-ins are module-level globals; tests must not corrupt them.
    """
    snapshot = dict(predicates._REGISTRY)  # intentional test access
    try:
        yield
    finally:
        predicates._REGISTRY.clear()
        predicates._REGISTRY.update(snapshot)


def _make_traversal(artifacts: dict[str, object] | None) -> PhaseTraversal:
    return PhaseTraversal.start(
        plan_ref="test-plan",
        entry_node_id="perceive.main",
        artifacts=artifacts,
        input=None,
    )


def test_register_and_resolve_roundtrip() -> None:
    """``register`` 后 ``resolve`` 拿回同一 callable。"""

    def my_pred(_t: PhaseTraversal) -> bool:
        return True

    predicates.register("custom.demo", my_pred)
    assert predicates.resolve("custom.demo") is my_pred


def test_register_overwrites_idempotently() -> None:
    """同名 ``register`` 是幂等覆盖(避免启动期 race 期间部分状态泄漏)。"""
    first: predicates.Predicate = lambda _t: True  # noqa: E731
    second: predicates.Predicate = lambda _t: False  # noqa: E731
    predicates.register("custom.race", first)
    predicates.register("custom.race", second)
    assert predicates.resolve("custom.race") is second


def test_resolve_unknown_name_returns_none() -> None:
    """``resolve`` 未注册 → ``None``(调用方应决定是抛错还是放行)。"""
    assert predicates.resolve("not.registered") is None


def test_known_predicates_returns_sorted_tuple() -> None:
    """``known_predicates`` 返回 sorted tuple(稳定序列化,便于 Profile 校验)。"""
    # built-ins + 临时注册
    predicates.register("zzz.last", lambda _t: True)
    predicates.register("aaa.first", lambda _t: True)
    known = predicates.known_predicates()
    assert isinstance(known, tuple)
    assert list(known) == sorted(known)
    # built-ins 必须在(已 register 过)
    assert "perceive.has_minimum_context" in known
    assert "perceive.context_complete" in known


# ── Built-in: perceive.has_minimum_context ────────────────────────────────


def test_perceive_has_minimum_context_with_user_text() -> None:
    """artifacts 有 ``user_text`` → precondition 满足。"""
    assert perceive_has_minimum_context(_make_traversal({"user_text": "hi"})) is True


def test_perceive_has_minimum_context_with_staged_attachments() -> None:
    """artifacts 有 ``staged_attachments`` → precondition 满足。"""
    assert perceive_has_minimum_context(_make_traversal({"staged_attachments": ["x"]})) is True


def test_perceive_has_minimum_context_with_clock() -> None:
    """artifacts 有 ``clock`` → precondition 满足(默认情况,traversal 总会带 clock)。"""
    assert perceive_has_minimum_context(_make_traversal({"clock": "2026-09-09"})) is True


def test_perceive_has_minimum_context_empty_artifacts() -> None:
    """artifacts 全空 → precondition 不满足(等 context 准备好再 visit)。"""
    assert perceive_has_minimum_context(_make_traversal({})) is False


# ── Built-in: perceive.context_complete ───────────────────────────────────


def test_perceive_context_complete_user_text_plus_attachment() -> None:
    """``user_text`` + ``staged_attachments`` → terminal_predicate 满足。"""
    assert (
        perceive_context_complete(_make_traversal({"user_text": "hi", "staged_attachments": ["x"]}))
        is True
    )


def test_perceive_context_complete_user_text_plus_sensor() -> None:
    """``user_text`` + ``sensor.*`` → terminal_predicate 满足(感知源任一即可)。"""
    assert (
        perceive_context_complete(_make_traversal({"user_text": "hi", "sensor.audio": "v"})) is True
    )


def test_perceive_context_complete_missing_user_text() -> None:
    """缺 ``user_text`` → terminal_predicate 不满足(任务主体未到)。"""
    assert perceive_context_complete(_make_traversal({"staged_attachments": ["x"]})) is False


def test_perceive_context_complete_missing_attachment_or_sensor() -> None:
    """缺 attachment/sensor → terminal_predicate 不满足(感知未收敛)。"""
    assert perceive_context_complete(_make_traversal({"user_text": "hi"})) is False


def test_perceive_context_complete_empty_artifacts() -> None:
    """全空 → terminal_predicate 不满足。"""
    assert perceive_context_complete(_make_traversal({})) is False
