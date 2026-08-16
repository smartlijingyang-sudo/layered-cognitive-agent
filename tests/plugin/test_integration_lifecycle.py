"""
完整生命周期集成——从 PENDING 到 DISPOSED 的全程跟踪。

想象一座繁忙的「共享美食广场」，每个档口（Plugin）都有自己的生命周期：
申请入驻(PENDING) → 装修施工(LOADING) → 正式开业(ACTIVE) → 卸货清场(UNLOADING) → 关门走人(DISPOSED)。

本模块全程跟踪一个档口从递交申请到最终退租的完整经历，同时考察那些
不走运的档口——装修失败(FAILED)、被要求整改后重新开业的情况。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.layer0_infra.plugin.kernel import (
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
    reconcile,
)
from lca.layer0_infra.plugin.kernel._lifecycle import (
    deactivate,
    shutdown,
    update_config,
)


def _spec(
    name: str,
    *,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    apply_fn: Any = None,
    validate: Any = None,
) -> PluginSpec:
    """建造一份「档口规格书」——名字、需要的水电接口(inject)、提供的招牌菜(provides)。"""
    return PluginSpec(
        name=name,
        apply=apply_fn or (lambda ctx, cfg: None),
        inject=inject,
        provides=provides,
        validate=validate,
    )


def _handle(
    entry_id: str,
    spec: PluginSpec,
    *,
    config: Any = None,
    injected: tuple[str, ...] = (),
    desired: bool = True,
) -> PluginHandle:
    """为一份规格书生成一张「入驻许可证」(PluginHandle)，包含配置和期望状态。"""
    return PluginHandle(
        entry_id=entry_id,
        spec=spec,
        config=config or {},
        injected=injected,
        desired=desired,
    )


# ── Test 1: Happy path ────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_pending_to_disposed() -> None:
    """一个档口的完整一生：申请(PENDING) → 装修(LOADING) → 开业(ACTIVE) → 卸货(UNLOADING) → 关门(DISPOSED)。

    这位摊主经历了美食广场最标准的流程——递交申请、等待审批、装修开业、
    最终体面地退租。我们用事件监听器记录每一步状态变迁，确认没有遗漏任何环节。
    """
    host = PluginHost()
    spec = _spec("simple", provides="simple")
    handle = _handle("simple", spec)
    host.register_handle(handle)

    # Track state transitions
    transitions: list[PluginState] = []

    def _on_status(h: PluginHandle, _old: PluginState) -> None:
        transitions.append(h.state)

    host.events.on("tester", "internal/status", _on_status)

    assert handle.state is PluginState.PENDING

    await reconcile(host)
    assert handle.state is PluginState.ACTIVE

    await deactivate(host, handle, permanent=True)
    assert handle.state is PluginState.DISPOSED

    # Verify we saw LOADING → ACTIVE during activate, and UNLOADING → DISPOSED during deactivate
    assert PluginState.LOADING in transitions
    assert PluginState.ACTIVE in transitions
    assert PluginState.UNLOADING in transitions
    assert PluginState.DISPOSED in transitions


# ── Test 2: Failed then re-activated ─────────────────────────


@pytest.mark.asyncio
async def test_failed_then_reactivated() -> None:
    """装修翻车后的档口：第一次开业失败(FAILED) → 整改申请(non-permanent deactivate → PENDING) → 重新开业(ACTIVE)。

    摊主第一次装修时出了事故（apply 抛异常），被标记为 FAILED。
    物业管理让他回去整改（deactivate permanent=False），档口回到 PENDING 等待复审。
    第二次 reconcile 时，摊主终于把装修搞定了——顺利开业。
    """
    host = PluginHost()

    call_count = 0

    def flaky_apply(ctx: Any, cfg: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")

    spec = _spec("flaky", provides="flaky", apply_fn=flaky_apply)
    handle = _handle("flaky", spec)
    host.register_handle(handle)

    # First reconcile → FAILED
    await reconcile(host)
    assert handle.state is PluginState.FAILED
    assert handle.error is not None

    # Deactivate non-permanent → PENDING
    await deactivate(host, handle, permanent=False)
    assert handle.state is PluginState.PENDING

    # Reconcile again → should succeed (call_count == 2)
    await reconcile(host)
    assert handle.state is PluginState.ACTIVE
    assert handle.error is None


# ── Test 3: Multiple plugins lifecycle ────────────────────────


@pytest.mark.asyncio
async def test_multiple_plugins_shutdown_reverse_order() -> None:
    """三个档口(A→B→C 依赖链)全部开业 → 美食广场统一关门 → 按逆序退租(C 先走，B 其次，A 最后)。

    美食广场要打烊了。物业管理规定：最后开业的档口先退租，
    因为依赖方必须先走，被依赖方才安心离开。
    A 提供水源，B 需要水源并生产果汁，C 需要果汁做冰沙——
    关门前先把冰沙卖了(C)、再关果汁机(B)、最后关水龙头(A)。
    """
    host = PluginHost()

    spec_a = _spec("a", provides="a")
    spec_b = _spec("b", inject=("a",), provides="b")
    spec_c = _spec("c", inject=("b",), provides="c")

    h_a = _handle("a", spec_a)
    h_b = _handle("b", spec_b, injected=("a",))
    h_c = _handle("c", spec_c, injected=("b",))

    host.register_handle(h_a)
    host.register_handle(h_b)
    host.register_handle(h_c)

    await reconcile(host)
    assert h_a.state is PluginState.ACTIVE
    assert h_b.state is PluginState.ACTIVE
    assert h_c.state is PluginState.ACTIVE

    dispose_order: list[str] = []

    def _on_dispose(h: PluginHandle) -> None:
        dispose_order.append(h.entry_id)

    host.events.on("tester2", "internal/plugin.disposed", _on_dispose)

    await shutdown(host)

    assert h_a.state is PluginState.DISPOSED
    assert h_b.state is PluginState.DISPOSED
    assert h_c.state is PluginState.DISPOSED
    # Reverse order: C, B, A
    assert dispose_order == ["c", "b", "a"]


# ── Test 4: Effect lifecycle (LIFO) ──────────────────────────


@pytest.mark.asyncio
async def test_effect_lifecycle_lifo_disposal() -> None:
    """档口注册了一堆「运营附属设施」(mount、event listener、effect) →
    关门时按后进先出(LIFO)顺序逐一拆除。

    摊主开业期间陆续搭建了三组附属设施（e1、e2、e3），
    还挂载了一个服务(my_svc)和一个事件监听器。
    关门清场时，最后搭建的 e3 最先拆除——就像叠盘子一样，最上面的先拿走。
    """
    host = PluginHost()
    dispose_log: list[str] = []

    def apply_with_effects(ctx: Any, cfg: Any) -> None:
        # Register mount (auto cleanup)
        ctx.mount("my_svc", "value")

        # Register event listener
        ctx.on("custom/event", lambda *a: None)

        # Register explicit effects: setup returns a cleanup that logs on disposal
        ctx.effect(lambda: lambda: dispose_log.append("effect_1"), label="e1")
        ctx.effect(lambda: lambda: dispose_log.append("effect_2"), label="e2")
        ctx.effect(lambda: lambda: dispose_log.append("effect_3"), label="e3")

    spec = _spec("effector", provides="effector", apply_fn=apply_with_effects)
    handle = _handle("effector", spec)
    host.register_handle(handle)

    await reconcile(host)
    assert handle.state is PluginState.ACTIVE
    # Verify effects registered
    assert len(handle.effects) >= 3

    await deactivate(host, handle, permanent=True)
    assert handle.state is PluginState.DISPOSED
    # LIFO: last registered disposed first
    assert dispose_log == ["effect_3", "effect_2", "effect_1"]
    # Service removed
    assert host.get_service("my_svc") is None


# ── Test 5: Config update with rollback ──────────────────────


@pytest.mark.asyncio
async def test_config_update_with_rollback() -> None:
    """档口更换经营方案(config)：合规则换方案成功；交了份会被打回的方案 → 自动回滚到上一版。

    摊主一开始提交了一份合规的经营方案(mode=ok)，顺利开业。
    后来想改成新方案(mode=updated)，审核通过，继续营业。
    但如果交了一份注定失败的方案(fail=True)，物业管理会直接退回，
    档口恢复到上一版方案继续运营——不会因为一次改方案就把店关了。
    """
    host = PluginHost()

    def strict_apply(ctx: Any, cfg: Any) -> None:
        mode = ctx.config if isinstance(ctx.config, dict) else {}
        if mode.get("fail"):
            raise RuntimeError("config rejected")

    def validate_fn(raw: Any) -> Any:
        if isinstance(raw, dict) and raw.get("fail"):
            raise ValueError("bad config")
        return raw

    spec = _spec(
        "configurable", provides="configurable", apply_fn=strict_apply, validate=validate_fn
    )
    handle = _handle("configurable", spec, config={"mode": "ok"})
    host.register_handle(handle)

    await reconcile(host)
    assert handle.state is PluginState.ACTIVE
    assert handle.config == {"mode": "ok"}

    # Valid update
    await update_config(host, "configurable", {"mode": "updated"})
    assert handle.state is PluginState.ACTIVE
    assert handle.config == {"mode": "updated"}

    # Failing update → should rollback
    from lca.layer0_infra.plugin.kernel._types import PluginError

    with pytest.raises(PluginError, match="config update failed"):
        await update_config(host, "configurable", {"fail": True})

    # Rolled back to previous valid config
    assert handle.state is PluginState.ACTIVE
    assert handle.config == {"mode": "updated"}
