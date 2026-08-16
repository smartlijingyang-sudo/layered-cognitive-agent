"""
跨档口依赖集成——钻石依赖、级联停业、自动恢复。

美食广场里的档口并不是孤立营业的：有人提供水源（基础服务），有人依赖水源做饮料，
还有人需要饮料才能做冰沙——这就形成了一条依赖链。

本模块验证三种关键场景：
1. **钻石依赖**：A 提供水，B 和 C 都需要水，D 需要 B 和 C 的输出。能否按正确顺序全部开业？
2. **级联停业**：关掉水源，下游所有档口是否自动停业？
3. **自动恢复**：水源恢复后，所有下游档口能否自动重新开业？
"""

from __future__ import annotations

import pytest

from lca.layer0_infra.plugin.kernel import (
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
    reconcile,
)
from lca.layer0_infra.plugin.kernel._lifecycle import deactivate


def _spec(
    name: str,
    *,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
) -> PluginSpec:
    """建造一份「档口规格书」：名字、依赖的水电接口、提供的招牌服务。"""
    return PluginSpec(
        name=name,
        apply=lambda ctx, cfg: None,
        inject=inject,
        provides=provides,
    )


def _handle(
    entry_id: str,
    spec: PluginSpec,
    *,
    injected: tuple[str, ...] | None = None,
) -> PluginHandle:
    """为一份规格书生成一张「入驻许可证」。"""
    return PluginHandle(
        entry_id=entry_id,
        spec=spec,
        config={},
        injected=injected if injected is not None else spec.inject,
    )


# ── Test 1: Diamond dependency ────────────────────────────────


@pytest.mark.asyncio
async def test_diamond_dependency_activation_order() -> None:
    """钻石依赖：A 提供水源(a)，B 和 C 都需要水源并分别生产果汁(b)和奶茶(c)，
    D 需要果汁和奶茶才能做甜品(d)。验证全部档口能按正确依赖顺序开业。

    这是美食广场最经典的依赖拓扑——◇ 菱形。A 是一切的基础，
    B 和 C 互不依赖但都需要 A，D 则需要 B 和 C 同时就绪。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="a"))
    h_b = _handle("b", _spec("b", inject=("a",), provides="b"))
    h_c = _handle("c", _spec("c", inject=("a",), provides="c"))
    h_d = _handle("d", _spec("d", inject=("b", "c"), provides="d"))

    for h in (h_a, h_b, h_c, h_d):
        host.register_handle(h)

    await reconcile(host)

    assert h_a.state is PluginState.ACTIVE
    assert h_b.state is PluginState.ACTIVE
    assert h_c.state is PluginState.ACTIVE
    assert h_d.state is PluginState.ACTIVE

    # Verify services mounted
    assert host.get_service("a") is not None
    assert host.get_service("b") is not None
    assert host.get_service("c") is not None
    assert host.get_service("d") is not None


# ── Test 2: Cascade on provider removal ──────────────────────


@pytest.mark.asyncio
async def test_cascade_on_provider_removal() -> None:
    """级联停业：A 供水，B 用水做饮料。关掉 A 的水阀 → B 因为断水也被迫停业。

    物业管理暂时关闭了 A 的水源（deactivate permanent=False），
    依赖水源的 B 立刻被波及——从 ACTIVE 跌回 PENDING，等待水源恢复。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="a"))
    h_b = _handle("b", _spec("b", inject=("a",), provides="b"))

    host.register_handle(h_a)
    host.register_handle(h_b)

    await reconcile(host)
    assert h_a.state is PluginState.ACTIVE
    assert h_b.state is PluginState.ACTIVE

    # Deactivate A (non-permanent to allow re-activation later)
    await deactivate(host, h_a, permanent=False)
    assert h_a.state is PluginState.PENDING
    # B should have been cascaded
    assert h_b.state is PluginState.PENDING


# ── Test 3: Re-activation when deps return ───────────────────


@pytest.mark.asyncio
async def test_reactivation_when_deps_return() -> None:
    """断水恢复：A 供水、B 用水 → 关掉 A（B 跟着停）→ 重新开启 A（B 自动恢复营业）。

    水源短暂检修后恢复供应。reconcile 像一位勤勉的物业管理——
    它发现 A 的依赖（无）已满足，于是让 A 重新开业；A 一回来，
    B 的依赖也满足了，B 也自动恢复营业。一切无需人工干预。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="a"))
    h_b = _handle("b", _spec("b", inject=("a",), provides="b"))

    host.register_handle(h_a)
    host.register_handle(h_b)

    await reconcile(host)
    assert h_a.state is PluginState.ACTIVE
    assert h_b.state is PluginState.ACTIVE

    # Deactivate A → B cascades
    await deactivate(host, h_a, permanent=False)
    assert h_a.state is PluginState.PENDING
    assert h_b.state is PluginState.PENDING

    # Reconcile → A's deps are met (none), so A reactivates
    await reconcile(host)
    assert h_a.state is PluginState.ACTIVE
    # B depends on 'a', now provided again
    assert h_b.state is PluginState.ACTIVE


# ── Test 4: Provider replacement ─────────────────────────────


@pytest.mark.asyncio
async def test_provider_replacement() -> None:
    """档口换老板：A 提供某服务(x) → A 永久退租(DISPOSED) → B 接手提供同样的服务(x) → 依赖 x 的 C 恢复营业。

    原来的档口 A 永久关门了，但它提供的服务(x)不能断——
    物业找来新的供应商 B 接手。B 开业后，一直在等 x 的 C 终于可以开张了。
    就像美食广场里某个做拉面的师傅走了，新来一个拉面师傅接手，
    等着拉面做配菜的小饭馆立刻恢复正常。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="x"))
    host.register_handle(h_a)

    await reconcile(host)
    assert h_a.state is PluginState.ACTIVE

    # Deactivate A permanently
    await deactivate(host, h_a, permanent=True)
    assert h_a.state is PluginState.DISPOSED
    assert host.get_service("x") is None

    # B provides 'x' instead
    h_b = _handle("b", _spec("b", provides="x"))
    host.register_handle(h_b)

    # C injects 'x'
    h_c = _handle(
        "c",
        _spec("c", inject=("x",), provides="c_holder"),
    )
    host.register_handle(h_c)

    await reconcile(host)
    assert h_b.state is PluginState.ACTIVE
    assert h_c.state is PluginState.ACTIVE
    assert host.get_service("x") is not None


# ── Test 5: Deep chain ───────────────────────────────────────


@pytest.mark.asyncio
async def test_deep_chain_cascade() -> None:
    """四级供应链：A→B→C→D，每一级为下一级提供原料。
    关掉中间的 B → 下游 C 和 D 全部停业，但上游 A 安然无恙。

    想象一条食物链：A 种菜 → B 洗菜切菜 → C 炒菜 → D 装盘上桌。
    洗菜工 B 突然请假了，切菜工 C 没活干，装盘工 D 也闲着——
    但种菜的 A 完全不受影响，他还在地里忙着呢。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="ka"))
    h_b = _handle("b", _spec("b", inject=("ka",), provides="kb"))
    h_c = _handle("c", _spec("c", inject=("kb",), provides="kc"))
    h_d = _handle("d", _spec("d", inject=("kc",), provides="kd"))

    for h in (h_a, h_b, h_c, h_d):
        host.register_handle(h)

    await reconcile(host)
    for h in (h_a, h_b, h_c, h_d):
        assert h.state is PluginState.ACTIVE

    # Deactivate B → C and D cascade (they depend transitively)
    await deactivate(host, h_b, permanent=False)
    assert h_b.state is PluginState.PENDING
    assert h_c.state is PluginState.PENDING
    assert h_d.state is PluginState.PENDING
    # A unaffected
    assert h_a.state is PluginState.ACTIVE


# ── Test 6: Independent branches ─────────────────────────────


@pytest.mark.asyncio
async def test_independent_branches_isolation() -> None:
    """两条互不相干的供应链 A→B 和 C→D：关掉 A 只影响 B，C 和 D 完全不受波及。

    美食广场分东西两个区，各自有独立的供应链。
    东区的 A 档口停业，只会连累依赖它的 B；
    西区的 C 和 D 井水不犯河水，照常营业。
    """
    host = PluginHost()

    h_a = _handle("a", _spec("a", provides="ka"))
    h_b = _handle("b", _spec("b", inject=("ka",), provides="kb"))
    h_c = _handle("c", _spec("c", provides="kc"))
    h_d = _handle("d", _spec("d", inject=("kc",), provides="kd"))

    for h in (h_a, h_b, h_c, h_d):
        host.register_handle(h)

    await reconcile(host)
    for h in (h_a, h_b, h_c, h_d):
        assert h.state is PluginState.ACTIVE

    # Deactivate A → B cascades, but C and D stay ACTIVE
    await deactivate(host, h_a, permanent=False)
    assert h_a.state is PluginState.PENDING
    assert h_b.state is PluginState.PENDING
    assert h_c.state is PluginState.ACTIVE
    assert h_d.state is PluginState.ACTIVE
