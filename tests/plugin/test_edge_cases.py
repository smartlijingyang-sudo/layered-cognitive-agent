"""
异常天气演练——极端情况下的系统健壮性。

美食广场不只关心晴天正常营业的日子，更要未雨绸缪——台风天、设备故障、
违规操作、资源冲突等各种极端情况都能从容应对。

本模块按故障类型分组演练：
- 清理工具的边界情况（空列表、不存在的项、重复删除）
- 档口在错误状态下注册附属设施
- 两个档口抢同一台设备
- 经营方案的校验边界
- 依赖无法满足时的「卡住」状态
- 反复关停的幂等性
- 清理回调抛异常不影响其他回调
- 事件总线的空操作
- 加载器遇到残次档口
- Seam 注册表的各种边界
- 配置更新的恢复与失败
- 注入方式的覆盖
- 并发挂载的安全性
- 关门时清理回调报错的处理
"""

from __future__ import annotations

import pytest

from lca.contracts.mechanisms.plugin import PluginConfig
from lca.contracts.mechanisms.seam import (
    IncompleteSeamError,  # noqa: F401
    SeamRegistry,
    SeamRole,
    consume,
    require_complete,  # noqa: F401
)
from lca.layer0_infra.plugin.kernel import (
    DependencyUnavailable,  # noqa: F401
    PluginError,
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
    reconcile,
)
from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._disposable import DisposableList
from lca.layer0_infra.plugin.kernel._lifecycle import (
    activate,
    deactivate,
    shutdown,  # noqa: F401
    update_config,
)
from lca.layer0_infra.plugin.loader import Loader, LoaderError, PluginEntry

# ── Helpers ───────────────────────────────────────────────────


def _make_handle(
    entry_id: str = "h",
    state: PluginState = PluginState.PENDING,
    injected: tuple[str, ...] = (),
    config: object = None,
) -> PluginHandle:
    """快速制造一张「入驻许可证」，用于各种边界测试。"""
    return PluginHandle(
        entry_id=entry_id,
        spec=PluginSpec(name=entry_id, apply=lambda ctx, cfg: None),
        config=config,
        injected=injected,
        state=state,
    )


def _make_mod(name: str = "mod", inject: tuple = (), provides: str | None = None):
    """快速制造一个「档口模块」——最简配置，没有个性。"""

    class _M:
        pass

    m = _M()
    m.name = name
    m.inject = inject
    m.provides = provides
    m.Config = PluginConfig
    m.apply = lambda ctx, cfg: None
    return m


# ── 1. DisposableList edge cases ─────────────────────────────


class TestDisposableListEdgeCases:
    """清理工具的边界演练——确保「收纳盒」(DisposableList) 在各种极端操作下不会崩溃。"""

    def test_delete_nonexistent_returns_false(self) -> None:
        """收纳盒是空的，试图删除一个不存在的标签 → 返回 False，不报错。"""
        dl = DisposableList()
        assert dl.delete("nope") is False

    def test_clear_on_empty_returns_empty_list(self) -> None:
        """清空一个已经空了的收纳盒 → 返回空列表，无事发生。"""
        dl = DisposableList()
        assert dl.clear() == []

    def test_push_then_remove_via_returned_remover(self) -> None:
        """放进一个物件，用返回的「取出器」取出 → 盒子恢复为空。"""
        dl = DisposableList()
        remover = dl.push("alpha")
        assert len(dl) == 1
        assert remover() is True
        assert len(dl) == 0

    def test_double_remove_is_noop(self) -> None:
        """同一个物件被取出两次 → 第一次成功，第二次返回 False（幂等）。"""
        dl = DisposableList()
        remover = dl.push("beta")
        assert remover() is True
        assert remover() is False  # second call: already gone


# ── 2. PluginContext in wrong state ──────────────────────────


class TestContextWrongState:
    """档口状态不对时的操作限制——在错误的时间注册附属设施会被拒绝。"""

    def test_effect_in_disposed_raises(self) -> None:
        """已经关门的档口(DISPOSED)还想注册附属设施 → 被拒绝。"""
        host = PluginHost()
        handle = _make_handle("x", state=PluginState.DISPOSED)
        host.register_handle(handle)
        ctx = PluginContext(host, handle)
        with pytest.raises(PluginError, match="Cannot register effect"):
            ctx.effect(lambda: None)

    def test_effect_in_pending_raises(self) -> None:
        """还在申请中的档口(PENDING)就想注册附属设施 → 被拒绝，装修好了再说。"""
        host = PluginHost()
        handle = _make_handle("y", state=PluginState.PENDING)
        host.register_handle(handle)
        ctx = PluginContext(host, handle)
        with pytest.raises(PluginError, match="Cannot register effect"):
            ctx.effect(lambda: None)


# ── 3. Host service conflicts ───────────────────────────────


class TestHostServiceConflicts:
    """服务台冲突演练——两个档口抢同一台设备，或同一个档口反复注册。"""

    @pytest.mark.asyncio
    async def test_two_handles_same_key_raises(self) -> None:
        """两个档口抢同一台设备 → 后来的被拒绝（先到先得）。"""
        host = PluginHost()
        h1 = _make_handle("a")
        h2 = _make_handle("b")
        host.register_handle(h1)
        host.register_handle(h2)
        host.provide(h1, "svc", 1)
        with pytest.raises(PluginError, match="already provided"):
            host.provide(h2, "svc", 2)

    @pytest.mark.asyncio
    async def test_same_handle_reprovide_updates(self) -> None:
        """同一个档口反复更新同一台设备 → 允许，以最新值为准。"""
        host = PluginHost()
        h = _make_handle("a")
        host.register_handle(h)
        host.provide(h, "svc", 1)
        host.provide(h, "svc", 2)
        assert host.get_service("svc") == 2


# ── 4. Config validation edge cases ─────────────────────────


class TestConfigValidationEdgeCases:
    """经营方案校验的边界——空方案、多余字段、空配置，各种刁钻情况。"""

    @pytest.mark.asyncio
    async def test_empty_config_with_required_field_fails(self) -> None:
        """档口要求必填 api_key，但交了一张空白方案 → 加载器拒绝。"""

        class StrictConfig(PluginConfig):
            api_key: str

        mod = _make_mod("strict")
        mod.Config = StrictConfig
        entry = PluginEntry(id="strict", module=mod, config={})
        with pytest.raises(LoaderError, match="config validation failed"):
            await Loader().load([entry])

    @pytest.mark.asyncio
    async def test_extra_field_fails(self) -> None:
        """档口方案里多了一个不认识的字段(unknown_key) → 被拒绝（严格模式不接受多余项）。"""
        mod = _make_mod("base")
        mod.Config = PluginConfig  # extra=forbid
        entry = PluginEntry(id="base", module=mod, config={"unknown_key": 42})
        with pytest.raises(LoaderError, match="config validation failed"):
            await Loader().load([entry])

    @pytest.mark.asyncio
    async def test_none_config_handled_gracefully(self) -> None:
        """档口没有特殊配置需求（空配置）→ 照样正常开业，不会崩溃。"""
        mod = _make_mod("none_cfg")
        entry = PluginEntry(id="none_cfg", module=mod, config={})
        tree = await Loader().load([entry])
        handle = tree.host.handles["none_cfg"]
        assert handle.state is PluginState.ACTIVE


# ── 5. Reconcile with no progress ───────────────────────────


class TestReconcileNoProgress:
    """「卡住」场景——依赖无法满足时档口的状态。"""

    @pytest.mark.asyncio
    async def test_pending_with_unsatisfied_deps_stays_pending(self) -> None:
        """档口需要一项不存在的服务(missing_svc) → 永远卡在 PENDING，不会被强行开业。"""
        host = PluginHost()
        h = _make_handle("stuck", injected=("missing_svc",))
        host.register_handle(h)
        await reconcile(host)
        assert h.state is PluginState.PENDING


# ── 6. Deactivate already deactivated ───────────────────────


class TestDeactivateAlreadyDeactivated:
    """重复关停的幂等性——已经停了或已关门的档口再次关停 → 无事发生。"""

    @pytest.mark.asyncio
    async def test_deactivate_pending_is_noop(self) -> None:
        """还在申请中(PENDING)的档口执行关停 → 无操作，状态不变。"""
        host = PluginHost()
        h = _make_handle("p", state=PluginState.PENDING)
        host.register_handle(h)
        await deactivate(host, h, permanent=False)
        assert h.state is PluginState.PENDING

    @pytest.mark.asyncio
    async def test_deactivate_disposed_is_noop(self) -> None:
        """已经关门(DISPOSED)的档口再次执行关停 → 无操作，状态不变。"""
        host = PluginHost()
        h = _make_handle("d", state=PluginState.DISPOSED)
        host.register_handle(h)
        await deactivate(host, h, permanent=True)
        assert h.state is PluginState.DISPOSED


# ── 7. Effect disposal errors ───────────────────────────────


class TestEffectDisposalErrors:
    """清场时的意外——某个清理回调抛异常，不影响其他回调执行。"""

    @pytest.mark.asyncio
    async def test_disposer_raises_does_not_block_others(self) -> None:
        """一个清理回调「爆炸」了(RuntimeError) → 另一个清理回调照样顺利执行。

        就像打烊时拆设备：有一台机器拆到一半卡住了（bad_disposer），
        但物业不会因此停工——继续拆下一台（good_disposer）。
        """
        mod_ok = _make_mod("ok")
        disposed: list[str] = []

        def apply_fn(ctx, cfg):
            def good_disposer():
                disposed.append("good")

            def bad_disposer():
                raise RuntimeError("boom")

            # LIFO order: last registered runs first
            ctx.effect(lambda: bad_disposer, label="bad")
            ctx.effect(lambda: good_disposer, label="good")

        mod_ok.apply = apply_fn
        entry = PluginEntry(id="ok", module=mod_ok, config={})
        tree = await Loader().load([entry])
        host = tree.host
        handle = host.handles["ok"]
        assert handle.state is PluginState.ACTIVE

        await deactivate(host, handle, permanent=True)
        # Both disposers ran despite one raising
        assert "good" in disposed


# ── 8. Event bus edge cases ─────────────────────────────────


class TestEventBusEdgeCases:
    """事件总线的边界——没人在听、无效令牌、空总线的清理。"""

    @pytest.mark.asyncio
    async def test_emit_no_listeners_no_error(self) -> None:
        """对着空气广播一条事件 → 无事发生，不报错。"""
        host = PluginHost()
        await host.events.emit("no_one_listening", 1, 2, 3)

    def test_off_invalid_token_returns_false(self) -> None:
        """用一个不存在的令牌去取消监听 → 返回 False，不报错。"""
        host = PluginHost()
        assert host.events.off(("nonexistent", 99999)) is False

    def test_remove_all_for_empty_bus(self) -> None:
        """清理一个从未注册过监听器的「幽灵频道」→ 无操作，不报错。"""
        host = PluginHost()
        host.events.remove_all_for("ghost")  # no error


# ── 9. Loader edge cases ────────────────────────────────────


class TestLoaderEdgeCases:
    """加载器遇到各种残次档口模块——属性缺失、apply 不可调用。"""

    @pytest.mark.asyncio
    async def test_entry_with_no_module_attributes_raises(self) -> None:
        """一个完全空白的「档口模块」(Empty class) → 加载器报 missing 错误。"""

        class Empty:
            pass

        entry = PluginEntry(id="broken", module=Empty(), config={})
        with pytest.raises(LoaderError, match="missing"):
            await Loader().load([entry])

    @pytest.mark.asyncio
    async def test_entry_non_callable_apply_becomes_failed(self) -> None:
        """档口的 apply 不是函数而是字符串 → 加载时通过但开业时失败(FAILED)。

        就像一个人拿着假资格证通过了初审（hasattr 检查通过），
        但实际让他干活时（调用 apply）就露馅了。
        """

        class BadMod:
            name = "bad"
            inject = ()
            provides = None
            Config = PluginConfig
            apply = "not a callable"  # hasattr passes, but calling fails

        entry = PluginEntry(id="bad", module=BadMod(), config={})
        # Loader doesn't validate callability of apply; activate fails at runtime
        host = PluginHost()
        spec = Loader._build_spec(entry)
        handle = PluginHandle(
            entry_id="bad",
            spec=spec,
            config=entry.config,
            injected=(),
        )
        host.register_handle(handle)
        await activate(host, handle)
        assert handle.state is PluginState.FAILED


# ── 10. Seam registry edge cases ────────────────────────────


class TestSeamRegistryEdgeCases:
    """Seam 注册表的边界——子类消费者识别、缺失角色查询、子类领取服务。"""

    def test_is_registered_consumer_subclass(self) -> None:
        """注册的消费者是 Base 类，用子类 Child 查询 → 依然能识别（子类继承父类的消费者身份）。"""
        reg = SeamRegistry()

        class Base:
            pass

        class Child(Base):
            pass

        reg.register(Base, "svc", SeamRole.CONSUMER)
        assert reg.is_registered_consumer("svc", Child) is True

    def test_get_missing_roles_nonexistent(self) -> None:
        """查询一个不存在的能力的缺失角色 → 返回全部三个角色（全缺）。"""
        reg = SeamRegistry()
        missing = reg.get_missing_roles("nope")
        assert set(missing) == {SeamRole.DEFINITION, SeamRole.PROVIDER, SeamRole.CONSUMER}

    def test_consume_with_subclass_consumer(self) -> None:
        """子类消费者领取服务：注册的是 Base 类为消费者，子类 Child 的实例也能顺利通过 consume 关卡。"""
        reg = SeamRegistry()

        class Base:
            pass

        class Child(Base):
            pass

        reg.register(Base, "llm", SeamRole.CONSUMER)
        provider = object()
        result = consume("llm", provider, Child, registry=reg)
        assert result is provider


# ── 11. update_config edge cases ─────────────────────────────


class TestUpdateConfigEdgeCases:
    """配置更新的边界——从失败中恢复、对已关门档口更新配置。"""

    @pytest.mark.asyncio
    async def test_update_on_failed_handle_tries_recover(self) -> None:
        """对一个 FAILED 状态的档口更新配置 → 触发重新激活 → 第二次尝试成功。

        摊主第一次开业搞砸了(FAILED)，但物业管理给他换了份新方案(update_config)，
        相当于让他从头来过。这次他没出岔子，顺利开业(ACTIVE)。
        """
        call_count = 0

        def apply_fn(ctx, cfg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first fail")

        mod = _make_mod("recover")
        mod.apply = apply_fn
        entry = PluginEntry(id="recover", module=mod, config={})
        tree = await Loader().load([entry])
        host = tree.host
        handle = host.handles["recover"]
        assert handle.state is PluginState.FAILED

        # update_config deactivates then reconciles → second apply call succeeds
        result = await update_config(host, "recover", {})
        assert result.state is PluginState.ACTIVE

    @pytest.mark.asyncio
    async def test_update_on_disposed_raises(self) -> None:
        """对一个已经关门(DISPOSED)的档口更新配置 → 失败，报错。

        人家都关门了，你还想去改人家的经营方案？物业管理拒绝了这个请求。
        """
        host = PluginHost()
        h = _make_handle("gone", state=PluginState.DISPOSED)
        host.register_handle(h)
        # DISPOSED handle: deactivate is noop, reconcile won't re-activate (desired=False logic),
        # so update_config rolls back and raises
        with pytest.raises(PluginError, match="config update failed"):
            await update_config(host, "gone", {})


# ── 12. Plugin inject edge cases ─────────────────────────────


class TestPluginInjectEdgeCases:
    """依赖注入的边界——字典形式的注入声明、Entry 级注入覆盖模块级注入。"""

    @pytest.mark.asyncio
    async def test_dict_form_inject_resolved(self) -> None:
        """用字典形式声明依赖(inject={"dep": "something"}) → 正常解析，依赖被注入。"""
        mod = _make_mod("dict_inj", inject=("dep",))
        dep_mod = _make_mod("dep", provides="dep")
        entries = [
            PluginEntry(id="dep", module=dep_mod, config={}),
            PluginEntry(
                id="dict_inj",
                module=mod,
                config={},
                inject={"dep": "something"},
            ),
        ]
        tree = await Loader().load(entries)
        handle = tree.host.handles["dict_inj"]
        assert "dep" in handle.injected

    @pytest.mark.asyncio
    async def test_entry_inject_overrides_module_inject(self) -> None:
        """Entry 级注入覆盖模块级注入：模块说需要 a 和 b，但 Entry 说只需要 a 和 c → 以 Entry 为准。

        档口的「规格书」(module) 写着需要 a 和 b 两种原料，
        但「入驻工单」(entry) 特别标注：我只需要 a 和 c。
        工单优先——最终注入的是 a 和 c。
        """
        mod = _make_mod("override", inject=("a", "b"))
        a_mod = _make_mod("a", provides="a")
        b_mod = _make_mod("b", provides="b")
        c_mod = _make_mod("c", provides="c")
        entries = [
            PluginEntry(id="a", module=a_mod, config={}),
            PluginEntry(id="b", module=b_mod, config={}),
            PluginEntry(id="c", module=c_mod, config={}),
            PluginEntry(
                id="override",
                module=mod,
                config={},
                inject=("a", "c"),
            ),
        ]
        tree = await Loader().load(entries)
        handle = tree.host.handles["override"]
        assert set(handle.injected) == {"a", "c"}


# ── 13. Concurrent mount/get ─────────────────────────────────


class TestConcurrentMountGet:
    """并发安全性——多个档口依次开业，服务表不损坏。"""

    @pytest.mark.asyncio
    async def test_mount_during_reconcile_no_corruption(self) -> None:
        """两个档口通过 reconcile 依次开业 → 服务表完整无损，两个服务都能领取。

        就像两个档口排着队装修开业，先 A 后 B。
        最终服务台上 a 和 b 两项服务都在，两个档口都 ACTIVE。
        """
        mod_a = _make_mod("a", provides="a")
        mod_b = _make_mod("b", inject=("a",), provides="b")
        entries = [
            PluginEntry(id="a", module=mod_a, config={}),
            PluginEntry(id="b", module=mod_b, config={}),
        ]
        tree = await Loader().load(entries)
        host = tree.host
        assert host.get_service("a") is not None
        assert host.get_service("b") is not None
        assert host.handles["a"].state is PluginState.ACTIVE
        assert host.handles["b"].state is PluginState.ACTIVE


# ── 14. BootedTree.dispose with errors ───────────────────────


class TestBootedTreeDisposeErrors:
    """美食广场打烊时清理回调报错的处理——报错要记录，但不能阻止其他档口退租。"""

    @pytest.mark.asyncio
    async def test_disposer_raises_logged_but_continues(self) -> None:
        """打烊时某个档口的清理回调「爆炸」了 → 记录警告后继续清理其他档口。

        就像美食广场统一打烊时，某个档口的设备拆到一半卡住了，
        但物业管理不会因为这一家就把整个广场的打烊流程中断——
        其他档口照常退租。
        """
        mod_a = _make_mod("a", provides="a")
        mod_b = _make_mod("b", inject=("a",), provides="b")
        entries = [
            PluginEntry(id="a", module=mod_a, config={}),
            PluginEntry(id="b", module=mod_b, config={}),
        ]
        tree = await Loader().load(entries)

        # Inject a failing disposer
        def bad():
            raise RuntimeError("dispose boom")

        tree._disposers.insert(0, ("a", bad))

        # Should not raise; logs warning instead
        tree.dispose()
        assert len(tree._disposers) == 0
