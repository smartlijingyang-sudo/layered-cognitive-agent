"""ProviderDispatch 直接用例：命名 provider 路由表（register/use/current/replace）。

lca.infrastructure.capability.dispatch.dispatch.ProviderDispatch 是
Definition 服务（llm / web / skills / subagents seam）共享的 provider
挂载形态——register 幂等 disposer（注册即 effect，卸载即撤销）、
replace 原子路由替换、use/current 单激活模式。此前 0 直接用例。
"""

from __future__ import annotations

import pytest

from lca.infrastructure.capability.dispatch.dispatch import ProviderDispatch


def _table() -> ProviderDispatch:
    return ProviderDispatch("test-seam")


# ── register ──────────────────────────────────────────────────────────────


def test_register_first_provider_becomes_active():
    provider = object()
    t = _table()
    dispose = t.register("a", provider)
    assert t.active == "a"
    assert t.current() is provider
    dispose()


def test_register_second_does_not_steal_active_without_activate():
    t = _table()
    pa, pb = object(), object()
    t.register("a", pa)
    t.register("b", pb)
    assert t.active == "a"
    assert t.current() is pa


def test_register_activate_true_takes_over():
    t = _table()
    pa, pb = object(), object()
    t.register("a", pa)
    t.register("b", pb, activate=True)
    assert t.active == "b"
    assert t.current() is pb


def test_register_rejects_empty_name():
    t = _table()
    with pytest.raises(ValueError, match="empty"):
        t.register("   ", object())
    assert t.names() == []


def test_register_rejects_duplicate():
    t = _table()
    pa = object()
    t.register("a", pa)
    with pytest.raises(KeyError, match="already registered"):
        t.register("a", object())
    assert t.current() is pa  # 重复注册不扰动已有路由


def test_register_strips_name():
    t = _table()
    t.register("  a  ", object())
    assert t.names() == ["a"]
    with pytest.raises(KeyError, match="already registered"):
        t.register("a", object())


def test_register_does_not_emit_change():
    t = _table()
    calls: list[int] = []
    t.on_change(lambda: calls.append(1))
    t.register("a", object())
    assert calls == []  # 只有 disposer/replace 触发通知


# ── disposer ──────────────────────────────────────────────────────────────


def test_disposer_removes_and_falls_back_active():
    t = _table()
    pa, pb = object(), object()
    dispose_a = t.register("a", pa)
    t.register("b", pb)
    dispose_a()
    assert t.names() == ["b"]
    assert t.active == "b"
    assert t.current() is pb
    with pytest.raises(KeyError, match="unknown provider"):
        t.get("a")


def test_disposer_idempotent():
    t = _table()
    calls: list[int] = []
    t.on_change(lambda: calls.append(1))
    dispose_a = t.register("a", object())
    t.register("b", object())
    dispose_a()
    n = len(calls)
    dispose_a()  # 第二次是空操作
    assert len(calls) == n
    assert t.names() == ["b"]
    assert t.active == "b"


def test_dispose_non_active_keeps_active():
    t = _table()
    pa, pb = object(), object()
    t.register("a", pa)
    dispose_b = t.register("b", pb)
    dispose_b()
    assert t.active == "a"
    assert t.current() is pa


def test_dispose_last_provider_leaves_no_active():
    t = _table()
    dispose = t.register("a", object())
    dispose()
    assert t.active is None
    with pytest.raises(RuntimeError, match="no provider registered"):
        t.current()


# ── replace ───────────────────────────────────────────────────────────────


def test_replace_swaps_provider_atomically():
    t = _table()
    pa, pa2 = object(), object()
    t.register("a", pa)
    dispose = t.replace("a", pa2)
    assert t.get("a") is pa2
    assert t.active == "a"  # 名不变，路由换
    assert t.current() is pa2
    dispose()
    with pytest.raises(KeyError):
        t.get("a")


def test_replace_unknown_raises():
    t = _table()
    with pytest.raises(KeyError, match="unknown provider"):
        t.replace("nope", object())


def test_replace_same_provider_is_noop_without_notify():
    t = _table()
    calls: list[int] = []
    t.on_change(lambda: calls.append(1))
    pa = object()
    t.register("a", pa)
    noop = t.replace("a", pa)
    assert t.get("a") is pa
    assert calls == []  # 恒等替换不触发变更通知
    noop()  # 无操作 disposer，可安全调用


def test_replace_disposer_falls_back_active():
    t = _table()
    pa2, pb = object(), object()
    t.register("a", object())
    t.register("b", pb)
    dispose = t.replace("a", pa2)
    dispose()
    assert t.names() == ["b"]
    assert t.active == "b"
    assert t.current() is pb


def test_replace_disposer_idempotent():
    t = _table()
    calls: list[int] = []
    t.on_change(lambda: calls.append(1))
    t.register("a", object())
    t.register("b", object())
    dispose = t.replace("a", object())
    dispose()
    n = len(calls)
    dispose()
    assert len(calls) == n


# ── use / current / get / names ────────────────────────────────────────────


def test_use_switches_active():
    t = _table()
    pa, pb = object(), object()
    t.register("a", pa)
    t.register("b", pb)
    assert t.use("b") is pb
    assert t.active == "b"
    assert t.current() is pb


def test_use_unknown_lists_available_providers():
    t = _table()
    t.register("a", object())
    t.register("b", object())
    with pytest.raises(KeyError) as exc_info:
        t.use("nope")
    assert "['a', 'b']" in str(exc_info.value)


def test_get_does_not_change_active():
    t = _table()
    pa, pb = object(), object()
    t.register("a", pa)
    t.register("b", pb)
    assert t.get("b") is pb
    assert t.active == "a"


def test_names_returns_insertion_order():
    t = _table()
    t.register("b", object())
    t.register("a", object())
    assert t.names() == ["b", "a"]


def test_current_with_no_provider_raises():
    t = _table()
    with pytest.raises(RuntimeError, match="no provider registered"):
        t.current()


# ── on_change ─────────────────────────────────────────────────────────────


def test_on_change_fires_on_dispose_and_replace():
    t = _table()
    calls: list[int] = []
    t.on_change(lambda: calls.append(1))
    dispose_a = t.register("a", object())
    dispose_a()
    assert len(calls) == 1
    t.register("b", object())
    t.replace("b", object())
    assert len(calls) == 2
    t.use("b")  # use 不触发通知
    assert len(calls) == 2


def test_on_change_disposer_removes_listener():
    t = _table()
    calls: list[int] = []
    off = t.on_change(lambda: calls.append(1))
    off()
    off()  # 重复 off 安全
    dispose = t.register("a", object())
    dispose()
    assert calls == []


def test_listener_exception_does_not_break_notification():
    t = _table()
    good: list[int] = []

    def bad() -> None:
        raise RuntimeError("boom")

    t.on_change(bad)
    t.on_change(lambda: good.append(1))
    dispose = t.register("a", object())
    dispose()  # 不应抛：异常被吞并记 warning
    assert good == [1]
