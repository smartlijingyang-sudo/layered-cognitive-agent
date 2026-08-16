"""美食广场运营逻辑——状态机驱动的全部故事。

共享美食广场里有几十个档口（插件），它们各自独立运营，
却通过共享设备（服务）相互依赖。本模块测试所有运营动作：

- reconcile（广场巡查）：检查所有等待中的档口，依赖满足了就让他们开业
- activate（开业流程）：PENDING → LOADING → ACTIVE（筹备 → 装修 → 开业）
- deactivate（停业流程）：ACTIVE → UNLOADING → PENDING（停业 → 清理 → 等待重新开业）
- shutdown（美食广场打烊）：所有档口逆序关门
- update_config（翻修菜单）：事务性更换配置，失败则回滚
- cascade（级联停业）：油炸机坏了 → 炸鸡档口和薯条档口自动停业
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
from lca.layer0_infra.plugin.kernel._lifecycle import (
    activate,
    deactivate,
    shutdown,
    update_config,
)
from lca.layer0_infra.plugin.kernel._service import Service
from lca.layer0_infra.plugin.kernel._types import PluginError

# ── Helpers ─────────────────────────────────────────────────


def _noop_apply(ctx, config):
    """啥也不做的档口——开门营业但不提供任何服务。"""
    return None


def _make_handle(
    entry_id: str = "test",
    *,
    apply_fn=_noop_apply,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    config=None,
    desired: bool = True,
    is_class: bool = False,
    validate=None,
) -> PluginHandle:
    """快速搭建一个档口：给好名字、经营范围和是否想开业。"""
    spec = PluginSpec(
        name=entry_id,
        apply=apply_fn,
        inject=inject,
        provides=provides,
        is_class=is_class,
        validate=validate,
    )
    return PluginHandle(
        entry_id=entry_id,
        spec=spec,
        config=config if config is not None else {},
        injected=inject,
        desired=desired,
    )


def _make_host_with_handle(entry_id: str = "test", **kw) -> tuple[PluginHost, PluginHandle]:
    """建造一座美食广场，并把一个档口登记入驻。"""
    host = PluginHost()
    handle = _make_handle(entry_id, **kw)
    host.register_handle(handle)
    return host, handle


# ════════════════════════════════════════════════════════════
# reconcile —— 广场巡查
# ════════════════════════════════════════════════════════════


class TestReconcile:
    """广场巡查：遍历所有等待中的档口，依赖满足了就让他们开业。

    巡查员一圈一圈地走，每轮把能开业的档口都开起来；
    如果某一轮没有任何进展，就收工。
    """

    @pytest.mark.asyncio
    async def test_activates_pending_with_satisfied_deps(self):
        """没有依赖的档口，reconcile 后直接开业。"""
        host, handle = _make_host_with_handle("p1")
        assert handle.state is PluginState.PENDING

        await reconcile(host)

        assert handle.state is PluginState.ACTIVE

    @pytest.mark.asyncio
    async def test_activates_chain_in_order(self):
        """依赖链条：供货商先开业，依赖他的档口才能跟上。"""
        host = PluginHost()

        provider = _make_handle(
            "provider",
            apply_fn=lambda ctx, cfg: ctx.mount("svc", "value"),
            provides="svc",
        )
        consumer = _make_handle("consumer", inject=("svc",))

        host.register_handle(provider)
        host.register_handle(consumer)

        await reconcile(host)

        assert provider.state is PluginState.ACTIVE
        assert consumer.state is PluginState.ACTIVE

    @pytest.mark.asyncio
    async def test_stops_when_stable(self):
        """巡查到没有新档口能开业时就收工——缺设备的档口继续等着。"""
        host = PluginHost()

        ready = _make_handle("ready")
        blocked = _make_handle("blocked", inject=("missing_service",))

        host.register_handle(ready)
        host.register_handle(blocked)

        await reconcile(host)

        assert ready.state is PluginState.ACTIVE
        assert blocked.state is PluginState.PENDING  # deps not met

    @pytest.mark.asyncio
    async def test_skips_non_desired_handles(self):
        """不想开业的档口，巡查时跳过——哪怕设备齐全也不管。"""
        host, handle = _make_host_with_handle("nd", desired=False)

        await reconcile(host)

        assert handle.state is PluginState.PENDING  # not activated

    @pytest.mark.asyncio
    async def test_skips_non_pending_handles(self):
        """已经在装修中（LOADING）的档口，巡查员不会重复打扰。"""
        host, handle = _make_host_with_handle("loading")
        handle.state = PluginState.LOADING

        await reconcile(host)

        assert handle.state is PluginState.LOADING  # unchanged


# ════════════════════════════════════════════════════════════
# activate —— 开业流程
# ════════════════════════════════════════════════════════════


class TestActivate:
    """开业流程：PENDING → LOADING → ACTIVE（筹备 → 装修 → 正式开业）。

    每个档口从等待状态开始，先审核配置文件，然后执行开业动作（apply），
    成功后挂上招牌（服务注册），正式营业。
    """

    @pytest.mark.asyncio
    async def test_validates_config_runs_apply_becomes_active(self):
        """顺利开业：审核配置 → 执行开业 → 状态变 ACTIVE。"""
        host, handle = _make_host_with_apply("a1")

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE
        assert handle.error is None

    @pytest.mark.asyncio
    async def test_auto_mounts_provides(self):
        """档口声明了 provide 但没主动注册设备 → 系统自动挂上招牌。"""
        host, handle = _make_host_with_apply(
            "am",
            apply_fn=lambda ctx, cfg: None,
            provides="am_svc",
        )

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE
        assert host.get_service("am_svc") is not None
        assert "am_svc" in handle.provided_services

    @pytest.mark.asyncio
    async def test_function_shape(self):
        """函数形态的档口：apply 返回一个清理函数（disposer），关门时调用。"""
        disposed = False

        def apply_fn(ctx, cfg):
            def disposer():
                nonlocal disposed
                disposed = True

            return disposer

        host, handle = _make_host_with_apply("fn", apply_fn=apply_fn)

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE
        assert len(handle.effects) >= 1

    @pytest.mark.asyncio
    async def test_class_shape_service_subclass(self):
        """类形态的档口：实例化 Service 子类，自动注册为服务。"""

        class MyService(Service):
            name = "my-svc"

            def __init__(self, ctx, config):
                super().__init__(ctx, config)
                self.initialized = True

        host, handle = _make_host_with_apply(
            "cls",
            apply_fn=lambda ctx, cfg: MyService(ctx, cfg),
            is_class=True,
            provides="my-svc",
        )

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE
        svc = host.get_service("my-svc")
        assert svc is not None
        assert svc.initialized is True

    @pytest.mark.asyncio
    async def test_failure_marks_failed_with_error(self):
        """开业过程中出事 → 状态变 FAILED，事故原因记录在案。"""
        exc = ValueError("boom")
        host, handle = _make_host_with_apply(
            "fail", apply_fn=lambda ctx, cfg: (_ for _ in ()).throw(exc)
        )

        await activate(host, handle)

        assert handle.state is PluginState.FAILED
        assert handle.error is exc

    @pytest.mark.asyncio
    async def test_effects_disposed_on_failure(self):
        """开业中途出事 → 已登记的善后措施按 LIFO 顺序逐一执行。"""
        dispose_log: list[str] = []

        def apply_fn(ctx, cfg):
            ctx.effect(lambda: lambda: dispose_log.append("e1"), label="e1")
            ctx.effect(lambda: lambda: dispose_log.append("e2"), label="e2")
            raise RuntimeError("apply boom")

        host, handle = _make_host_with_apply("ef", apply_fn=apply_fn)

        await activate(host, handle)

        assert handle.state is PluginState.FAILED
        # LIFO order: e2 before e1
        assert dispose_log == ["e2", "e1"]

    @pytest.mark.asyncio
    async def test_activate_noop_when_not_pending(self):
        """已经在营业（ACTIVE）的档口，activate 不会重复操作。"""
        host, handle = _make_host_with_apply("np")
        handle.state = PluginState.ACTIVE

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE  # unchanged

    @pytest.mark.asyncio
    async def test_activate_noop_when_not_desired(self):
        """不想开业的档口，activate 不会强行让他营业。"""
        host, handle = _make_host_with_apply("nd", desired=False)

        await activate(host, handle)

        assert handle.state is PluginState.PENDING  # unchanged

    @pytest.mark.asyncio
    async def test_validate_config_called(self):
        """自定义配置审核函数在开业前被调用。"""
        validated_with = None

        def validate(cfg):
            nonlocal validated_with
            validated_with = cfg
            return cfg

        host, handle = _make_host_with_apply(
            "val",
            config={"key": "value"},
            validate=validate,
        )

        await activate(host, handle)

        assert handle.state is PluginState.ACTIVE
        assert validated_with == {"key": "value"}

    @pytest.mark.asyncio
    async def test_validate_failure_marks_failed(self):
        """配置审核不过 → 状态变 FAILED，无法开业。"""

        def validate(cfg):
            raise ValueError("bad config")

        host, handle = _make_host_with_apply("vf", validate=validate)

        await activate(host, handle)

        assert handle.state is PluginState.FAILED
        assert isinstance(handle.error, ValueError)
        assert "bad config" in str(handle.error)


# ════════════════════════════════════════════════════════════
# deactivate —— 停业流程
# ════════════════════════════════════════════════════════════


class TestDeactivate:
    """停业流程：ACTIVE → UNLOADING → PENDING/DISPOSED（停业 → 清理 → 等待重新开业 / 彻底拆除）。

    停业时按 LIFO 顺序执行清理，撤掉设备，注销服务。
    permanent=True 表示彻底拆除（DISPOSED），permanent=False 只是暂时歇业（PENDING）。
    """

    @pytest.mark.asyncio
    async def test_runs_effect_disposers_lifo(self):
        """停业时清理措施按 LIFO 顺序执行：后登记的先清理。"""
        dispose_log: list[str] = []

        def apply_fn(ctx, cfg):
            ctx.effect(lambda: lambda: dispose_log.append("first"), label="first")
            ctx.effect(lambda: lambda: dispose_log.append("second"), label="second")
            ctx.effect(lambda: lambda: dispose_log.append("third"), label="third")

        host, handle = _make_host_with_apply("lifo", apply_fn=apply_fn)
        await activate(host, handle)
        dispose_log.clear()

        await deactivate(host, handle, permanent=True)

        assert dispose_log == ["third", "second", "first"]

    @pytest.mark.asyncio
    async def test_removes_owned_services(self):
        """停业时下架该档口提供的所有设备/服务。"""

        def apply_fn(ctx, cfg):
            ctx.mount("my_svc", "the_value")

        host, handle = _make_host_with_apply("rm", apply_fn=apply_fn)
        await activate(host, handle)
        assert host.get_service("my_svc") == "the_value"

        await deactivate(host, handle, permanent=True)

        assert host.get_service("my_svc") is None
        assert "my_svc" not in handle.provided_services

    @pytest.mark.asyncio
    async def test_permanent_true_disposed(self):
        """permanent=True：彻底拆除，状态变为 DISPOSED。"""
        host, handle = _make_host_with_apply("perm")
        await activate(host, handle)

        await deactivate(host, handle, permanent=True)

        assert handle.state is PluginState.DISPOSED

    @pytest.mark.asyncio
    async def test_permanent_false_pending(self):
        """permanent=False：暂时歇业，状态回到 PENDING，可以重新开业。"""
        host, handle = _make_host_with_apply("temp")
        await activate(host, handle)

        await deactivate(host, handle, permanent=False)

        assert handle.state is PluginState.PENDING

    @pytest.mark.asyncio
    async def test_cascade_to_dependents(self):
        """供货商停业 → 依赖他的下游档口自动跟着歇业（级联）。"""
        host = PluginHost()

        def provider_apply(ctx, cfg):
            ctx.mount("shared", "value")

        provider = _make_handle("provider", apply_fn=provider_apply, provides="shared")
        consumer = _make_handle("consumer", inject=("shared",))
        host.register_handle(provider)
        host.register_handle(consumer)

        await reconcile(host)
        assert provider.state is PluginState.ACTIVE
        assert consumer.state is PluginState.ACTIVE

        await deactivate(host, provider, permanent=False)

        assert provider.state is PluginState.PENDING
        assert consumer.state is PluginState.PENDING  # cascaded

    @pytest.mark.asyncio
    async def test_noop_when_already_disposed(self):
        """已经拆除（DISPOSED）的档口，停业操作不会有任何动作。"""
        host, handle = _make_host_with_apply("done")
        handle.state = PluginState.DISPOSED

        await deactivate(host, handle, permanent=True)

        assert handle.state is PluginState.DISPOSED

    @pytest.mark.asyncio
    async def test_noop_when_already_pending(self):
        """还在筹备（PENDING）的档口，临时停业不会改变状态。"""
        host, handle = _make_host_with_apply("pend")

        await deactivate(host, handle, permanent=False)

        assert handle.state is PluginState.PENDING  # unchanged

    @pytest.mark.asyncio
    async def test_pending_permanent_becomes_disposed(self):
        """permanent=True on PENDING handle → DISPOSED."""
        host, handle = _make_host_with_apply("pd")

        await deactivate(host, handle, permanent=True)

        assert handle.state is PluginState.DISPOSED

    @pytest.mark.asyncio
    async def test_clears_error(self):
        """停业会清除之前记录的错误——重新开始，既往不咎。"""
        host, handle = _make_host_with_apply(
            "err",
            apply_fn=lambda ctx, cfg: (_ for _ in ()).throw(ValueError("x")),
        )
        await activate(host, handle)
        assert handle.state is PluginState.FAILED
        assert handle.error is not None

        await deactivate(host, handle, permanent=False)

        assert handle.error is None
        assert handle.state is PluginState.PENDING


# ════════════════════════════════════════════════════════════
# shutdown —— 美食广场打烊
# ════════════════════════════════════════════════════════════


class TestShutdown:
    """美食广场打烊：所有档口逆序关门。

    最后开业的最先关门（LIFO），确保依赖关系不会在关门过程中断裂。
    """

    @pytest.mark.asyncio
    async def test_deactivates_all_reverse_order(self):
        """打烊时所有档口按注册逆序逐一关门：c 先关，b 其次，a 最后。"""
        host = PluginHost()
        order: list[str] = []

        def make_apply(eid):
            def apply_fn(ctx, cfg):
                ctx.effect(lambda: lambda: order.append(eid), label=eid)

            return apply_fn

        for eid in ("a", "b", "c"):
            h = _make_handle(eid, apply_fn=make_apply(eid))
            host.register_handle(h)

        await reconcile(host)
        assert all(h.state is PluginState.ACTIVE for h in host.handles.values())
        order.clear()

        await shutdown(host)

        # Reverse order: c, b, a
        assert order == ["c", "b", "a"]
        for h in host.handles.values():
            assert h.state is PluginState.DISPOSED
            assert h.desired is False

    @pytest.mark.asyncio
    async def test_shutdown_empty_host(self):
        """空广场打烊——什么也不会发生，但也不会报错。"""
        host = PluginHost()
        await shutdown(host)  # should not raise


# ════════════════════════════════════════════════════════════
# update_config —— 翻修菜单
# ════════════════════════════════════════════════════════════


class TestUpdateConfig:
    """翻修菜单：事务性更换配置文件，失败则回滚到旧版本。

    就像档口要换菜单：先歇业、换上新菜单、重新开业。
    如果新菜单有问题（apply 失败），就恢复旧菜单重新营业。
    """

    @pytest.mark.asyncio
    async def test_successful_update(self):
        """顺利翻修：换上配置后重新开业，apply 拿到新配置。"""
        configs_seen: list = []

        def apply_fn(ctx, cfg):
            configs_seen.append(cfg)

        host, handle = _make_host_with_apply("uc", apply_fn=apply_fn, config={"v": 1})
        await reconcile(host)
        assert handle.state is PluginState.ACTIVE
        configs_seen.clear()

        result = await update_config(host, "uc", {"v": 2})

        assert result is handle
        assert handle.config == {"v": 2}
        assert handle.state is PluginState.ACTIVE
        assert configs_seen == [{"v": 2}]

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self):
        """翻修失败 → 回滚到旧配置，重新开业。"""
        call_count = 0

        def apply_fn(ctx, cfg):
            nonlocal call_count
            call_count += 1
            if cfg.get("bad"):
                raise RuntimeError("bad config")

        host, handle = _make_host_with_apply("rb", apply_fn=apply_fn, config={"bad": False})
        await reconcile(host)
        assert handle.state is PluginState.ACTIVE

        with pytest.raises(PluginError, match="config update failed"):
            await update_config(host, "rb", {"bad": True})

        # Rolled back to old config and re-activated
        assert handle.config == {"bad": False}
        assert handle.state is PluginState.ACTIVE

    @pytest.mark.asyncio
    async def test_non_desired_handle_just_updates_config(self):
        """不想开业的档口：只更新配置，不会触发开业流程。"""
        host, handle = _make_host_with_apply("nd", desired=False, config={"old": True})

        result = await update_config(host, "nd", {"new": True})

        assert result is handle
        assert handle.config == {"new": True}
        assert handle.state is PluginState.PENDING  # not activated


# ════════════════════════════════════════════════════════════
# State transition events —— 运营日志
# ════════════════════════════════════════════════════════════


class TestStateTransitionEvents:
    """运营日志：每次状态变化都会发出事件，供监控系统记录。"""

    @pytest.mark.asyncio
    async def test_activate_emits_status_events(self):
        """开业过程发出两条状态日志：从 PENDING 到 LOADING，再从 LOADING 到 ACTIVE。"""
        host = PluginHost()
        handle = _make_handle("ev")
        host.register_handle(handle)

        status_events: list = []
        host.events.on("ev", "internal/status", lambda *args: status_events.append(args))

        await activate(host, handle)

        # (handle, from_state) — first from PENDING, then from LOADING
        assert len(status_events) == 2
        assert status_events[0] == (handle, PluginState.PENDING)
        assert status_events[1] == (handle, PluginState.LOADING)

    @pytest.mark.asyncio
    async def test_activate_emits_plugin_active(self):
        """开业成功后发出 plugin.active 事件——恭喜新档口开张。"""
        host = PluginHost()
        handle = _make_handle("pa")
        host.register_handle(handle)

        active_events: list = []
        host.events.on("pa", "internal/plugin.active", lambda *args: active_events.append(args))

        await activate(host, handle)

        assert len(active_events) == 1
        assert active_events[0] == (handle,)

    @pytest.mark.asyncio
    async def test_deactivate_emits_disposed_event(self):
        """彻底拆除后发出 plugin.disposed 事件。"""
        host = PluginHost()
        handle = _make_handle("dp")
        host.register_handle(handle)
        await activate(host, handle)

        disposed_events: list = []
        host.events.on("dp", "internal/plugin.disposed", lambda *args: disposed_events.append(args))

        await deactivate(host, handle, permanent=True)

        assert len(disposed_events) == 1
        assert disposed_events[0] == (handle,)

    @pytest.mark.asyncio
    async def test_deactivate_emits_status_events(self):
        """停业过程发出两条状态日志：从 ACTIVE 到 UNLOADING，再从 UNLOADING 到最终状态。"""
        host = PluginHost()
        handle = _make_handle("ds")
        host.register_handle(handle)
        await activate(host, handle)

        status_events: list = []
        host.events.on("ds", "internal/status", lambda *args: status_events.append(args))

        await deactivate(host, handle, permanent=True)

        # (handle, from_state) — first from ACTIVE, then from UNLOADING
        assert len(status_events) == 2
        assert status_events[0] == (handle, PluginState.ACTIVE)
        assert status_events[1] == (handle, PluginState.UNLOADING)


# ════════════════════════════════════════════════════════════
# Cascade —— 级联停业
# ════════════════════════════════════════════════════════════


class TestCascade:
    """级联停业：一个档口倒了，依赖它的下游也自动歇业。

    就像油炸机坏了 → 炸鸡档口和薯条档口都没法干了。
    """

    @pytest.mark.asyncio
    async def test_deactivating_provider_cascades_to_consumers(self):
        """供货商被拆除 → 依赖他的下游档口自动回到 PENDING 等待。"""
        host = PluginHost()

        def provider_apply(ctx, cfg):
            ctx.mount("svc_a", "value_a")

        provider = _make_handle("provider", apply_fn=provider_apply, provides="svc_a")
        consumer = _make_handle("consumer", inject=("svc_a",))
        host.register_handle(provider)
        host.register_handle(consumer)

        await reconcile(host)
        assert provider.state is PluginState.ACTIVE
        assert consumer.state is PluginState.ACTIVE

        await deactivate(host, provider, permanent=True)

        assert provider.state is PluginState.DISPOSED
        assert consumer.state is PluginState.PENDING  # cascaded

    @pytest.mark.asyncio
    async def test_cascade_only_affects_dependent_consumers(self):
        """级联只影响依赖被撤服务的档口，其他档口不受波及。"""
        host = PluginHost()

        def pa_apply(ctx, cfg):
            ctx.mount("svc_a", "va")

        def pb_apply(ctx, cfg):
            ctx.mount("svc_b", "vb")

        pa = _make_handle("pa", apply_fn=pa_apply, provides="svc_a")
        pb = _make_handle("pb", apply_fn=pb_apply, provides="svc_b")
        # Consumer depends on both services
        consumer = _make_handle("consumer", inject=("svc_a", "svc_b"))
        host.register_handle(pa)
        host.register_handle(pb)
        host.register_handle(consumer)

        await reconcile(host)
        assert all(h.state is PluginState.ACTIVE for h in host.handles.values())

        # Deactivate pa → cascade should hit consumer (depends on svc_a)
        await deactivate(host, pa, permanent=True)

        assert pa.state is PluginState.DISPOSED
        assert consumer.state is PluginState.PENDING  # cascaded
        assert pb.state is PluginState.ACTIVE  # unaffected

    @pytest.mark.asyncio
    async def test_cascade_permanent_false_consumer_can_reactivate(self):
        """暂时歇业（permanent=False）→ 供货商恢复后，下游也能重新开业。"""
        host = PluginHost()

        def provider_apply(ctx, cfg):
            ctx.mount("svc", "val")

        provider = _make_handle("provider", apply_fn=provider_apply, provides="svc")
        consumer = _make_handle("consumer", inject=("svc",))
        host.register_handle(provider)
        host.register_handle(consumer)

        await reconcile(host)
        assert consumer.state is PluginState.ACTIVE

        # Non-permanent deactivate: provider goes PENDING, consumer cascaded
        await deactivate(host, provider, permanent=False)
        assert provider.state is PluginState.PENDING
        assert consumer.state is PluginState.PENDING

        # Reconcile should re-activate both
        await reconcile(host)
        assert provider.state is PluginState.ACTIVE
        assert consumer.state is PluginState.ACTIVE


# ── Shared helper ───────────────────────────────────────────


def _make_host_with_apply(
    entry_id: str = "test",
    *,
    apply_fn=_noop_apply,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    config=None,
    desired: bool = True,
    is_class: bool = False,
    validate=None,
) -> tuple[PluginHost, PluginHandle]:
    """建造一座美食广场，把一个带开业动作的档口登记入驻。"""
    host = PluginHost()
    handle = _make_handle(
        entry_id,
        apply_fn=apply_fn,
        inject=inject,
        provides=provides,
        config=config,
        desired=desired,
        is_class=is_class,
        validate=validate,
    )
    host.register_handle(handle)
    return host, handle
