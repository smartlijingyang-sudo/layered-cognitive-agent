"""招商办测试——审核资质、拓扑排序、驱动开业。

Loader 就是美食广场的招商办：
1. 审核每个档口的资质（配置校验、依赖声明）
2. 按依赖关系拓扑排序（供货商先开业）
3. 驱动开业流程（reconcile）

本模块测试招商办的各种场景：正常招商、资质不符、重复摊位等。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.mechanisms.plugin import PluginConfig
from lca.layer0_infra.plugin.kernel import PluginState
from lca.layer0_infra.plugin.loader import Loader, LoaderError, PluginEntry

# ── Helpers ──────────────────────────────────────────────────


def _make_module(
    name: str,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    *,
    on_apply: Any = None,
    config_cls: type[PluginConfig] = PluginConfig,
) -> Any:
    """伪造一个档口模块：有名字、经营范围、依赖声明和开业动作。"""

    class Module:
        pass

    mod = Module()
    mod.name = name
    mod.inject = inject
    mod.provides = provides
    mod.Config = config_cls

    def apply(ctx: Any, config: Any) -> Any:
        if on_apply is not None:
            return on_apply(ctx, config)

    mod.apply = apply
    return mod


def _entry(
    id: str,
    module: Any = None,
    *,
    config: dict[str, Any] | None = None,
    disabled: bool = False,
    inject: tuple[str, ...] | dict[str, Any] | None = None,
) -> PluginEntry:
    return PluginEntry(
        id=id,
        module=module,
        config=config or {},
        disabled=disabled,
        inject=inject,
    )


# ════════════════════════════════════════════════════════════
# 1. 正常招商 —— 基础加载
# ════════════════════════════════════════════════════════════


class TestBasicLoading:
    """基础加载：空广场、单个档口、依赖链、配置解析等正常场景。"""

    @pytest.mark.asyncio
    async def test_empty_profile_yields_empty_tree(self) -> None:
        """空招商方案 → 美食广场空空如也。"""
        tree = await Loader().load([])
        assert tree.entries == []

    @pytest.mark.asyncio
    async def test_single_plugin_no_deps(self) -> None:
        """独立档口无依赖 → 直接开业，提供的设备挂上招牌。"""
        mod = _make_module("solo", provides="solo-svc")
        tree = await Loader().load([_entry("solo", mod)])

        assert len(tree.entries) == 1
        assert tree.entries[0].id == "solo"
        handle = tree.host.handles["solo"]
        assert handle.state is PluginState.ACTIVE
        assert tree.host.get_service("solo-svc") is not None

    @pytest.mark.asyncio
    async def test_two_plugins_respect_inject_order(self) -> None:
        """两个档口有依赖关系 → 招商办自动按拓扑排序，供货商先开业。"""
        a = _make_module("a", provides="a")
        b = _make_module("b", inject=("a",), provides="b")

        # Declare them in reverse order — loader should still sort correctly
        tree = await Loader().load(
            [
                _entry("b", b),
                _entry("a", a),
            ]
        )

        assert tree.host.handles["a"].state is PluginState.ACTIVE
        assert tree.host.handles["b"].state is PluginState.ACTIVE

    @pytest.mark.asyncio
    async def test_plugin_can_mount_via_ctx(self) -> None:
        """档口可以通过 ctx.mount 主动注册设备。"""

        def on_apply(ctx: Any, config: Any) -> None:
            ctx.mount("my-svc", {"hello": "world"})

        mod = _make_module("mounter", on_apply=on_apply)
        tree = await Loader().load([_entry("mounter", mod)])

        assert tree.host.get_service("my-svc") == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_parsed_config_received(self) -> None:
        """配置会被解析成对应的 PluginConfig 子类再传给档口。"""

        class MyConfig(PluginConfig):
            model: str = "gpt-4"

        received: list[Any] = []

        def on_apply(ctx: Any, config: Any) -> None:
            received.append(config)

        mod = _make_module("cfg-plugin", on_apply=on_apply, config_cls=MyConfig)
        await Loader().load(
            [
                _entry("cfg-plugin", mod, config={"model": "claude-3"}),
            ]
        )

        assert len(received) == 1
        assert isinstance(received[0], MyConfig)
        assert received[0].model == "claude-3"

    @pytest.mark.asyncio
    async def test_disabled_entries_skipped(self) -> None:
        """标记为 disabled 的档口 → 招商办直接跳过，不登记入驻。"""
        mod = _make_module("disabled-mod", provides="nope")
        tree = await Loader().load([_entry("disabled-mod", mod, disabled=True)])

        assert tree.entries == []
        assert "disabled-mod" not in tree.host.handles

    @pytest.mark.asyncio
    async def test_duplicate_ids_raise(self) -> None:
        """两个档口申请同一个摊位号 → 招商办拒绝，报错 duplicate plugin id。"""
        mod = _make_module("dup")
        with pytest.raises(LoaderError, match="duplicate plugin id"):
            await Loader().load(
                [
                    _entry("same-id", mod),
                    _entry("same-id", mod),
                ]
            )


# ════════════════════════════════════════════════════════════
# 2. 招商失败 —— 各种异常
# ════════════════════════════════════════════════════════════


class TestFailureSemantics:
    """招商失败场景：缺依赖、抢摊位、开业翻车、配置不合格、循环依赖。"""

    @pytest.mark.asyncio
    async def test_missing_inject_reports_key(self) -> None:
        """档口声明需要某设备但没人提供 → 招商办报错，指出缺哪个。"""
        mod = _make_module("needy", inject=("nonexistent-dep",))
        with pytest.raises(LoaderError, match="nonexistent-dep"):
            await Loader().load([_entry("needy", mod)])

    @pytest.mark.asyncio
    async def test_double_provides_fails(self) -> None:
        """两个档口声明提供同一台设备 → 招商办拒绝。"""
        a = _make_module("a1", provides="shared-key")
        b = _make_module("a2", provides="shared-key")
        with pytest.raises(LoaderError, match="shared-key"):
            await Loader().load(
                [
                    _entry("a1", a),
                    _entry("a2", b),
                ]
            )

    @pytest.mark.asyncio
    async def test_apply_failure_marks_failed(self) -> None:
        """档口开业时出事 → 状态变 FAILED，错误被记录，但招商流程继续。"""

        def bad_apply(ctx: Any, config: Any) -> None:
            raise RuntimeError("boom")

        mod = _make_module("bad", provides="bad-svc", on_apply=bad_apply)
        # apply failure → handle goes to FAILED state; Loader._check_failures
        # skips FAILED handles (they're reported during activate).
        # The loader still succeeds but the handle is FAILED.
        tree = await Loader().load([_entry("bad", mod)])
        handle = tree.host.handles["bad"]
        assert handle.state is PluginState.FAILED
        assert handle.error is not None

    @pytest.mark.asyncio
    async def test_config_validation_fails_load(self) -> None:
        """配置审核不过 → 招商办拒绝该档口入驻。"""

        class StrictConfig(PluginConfig):
            required_field: str

        mod = _make_module("strict", config_cls=StrictConfig)
        # Empty config → validation should fail
        with pytest.raises(LoaderError, match="config validation failed"):
            await Loader().load([_entry("strict", mod, config={})])

    @pytest.mark.asyncio
    async def test_cycle_detected(self) -> None:
        """两个档口互相依赖 → 招商办检测到循环依赖，拒绝招商。"""
        a = _make_module("a", inject=("b-svc",), provides="a-svc")
        b = _make_module("b", inject=("a-svc",), provides="b-svc")
        with pytest.raises(LoaderError, match="cycle"):
            await Loader().load(
                [
                    _entry("a", a),
                    _entry("b", b),
                ]
            )


# ════════════════════════════════════════════════════════════
# 3. 招商成果 —— 树形结构
# ════════════════════════════════════════════════════════════


class TestTreeStructure:
    """招商完成后的成果：tree.entries 列出所有开业档口，tree.dispose() 统一打烊。"""

    @pytest.mark.asyncio
    async def test_entries_list_contains_activated_plugins(self) -> None:
        """招商完成后，entries 列表包含所有已开业的档口。"""
        a = _make_module("a", provides="a")
        b = _make_module("b", provides="b")
        tree = await Loader().load(
            [
                _entry("a", a),
                _entry("b", b),
            ]
        )
        ids = {e.id for e in tree.entries}
        assert ids == {"a", "b"}

    @pytest.mark.asyncio
    async def test_disposers_populated(self) -> None:
        """开业时登记了清理措施的档口 → tree._disposers 不为空。"""

        def on_apply(ctx: Any, config: Any) -> None:
            ctx.mount("svc-x", 42)

        mod = _make_module("with-disposer", on_apply=on_apply)
        tree = await Loader().load([_entry("with-disposer", mod)])
        assert len(tree._disposers) >= 1

    @pytest.mark.asyncio
    async def test_booted_tree_dispose_runs_without_error(self) -> None:
        """招商完成的广场执行统一打烊（dispose）不会报错。"""
        mod = _make_module("disposable", provides="disp-svc")
        tree = await Loader().load([_entry("disposable", mod)])
        # dispose should not raise
        tree.dispose()


# ════════════════════════════════════════════════════════════
# 4. 档口覆盖模块声明 —— inject override
# ════════════════════════════════════════════════════════════


class TestEntryInjectOverride:
    """招商方案（entry）可以覆盖档口自带的依赖声明。

    模块自己说要依赖某设备，但招商方案里可以改写——以方案为准。
    """

    @pytest.mark.asyncio
    async def test_entry_inject_overrides_module_inject(self) -> None:
        """模块声明 inject=('missing',) 但招商方案覆盖为 () → 以方案为准，正常开业。"""
        a = _make_module("a", provides="a-svc")

        # Module declares inject=("missing",) but entry overrides to ()
        b_mod = _make_module("b", inject=("missing",), provides="b-svc")
        entry_b = _entry("b", b_mod, inject=())

        tree = await Loader().load(
            [
                _entry("a", a),
                entry_b,
            ]
        )
        # Without override, b would fail because 'missing' doesn't exist.
        # With entry inject override to (), b activates fine.
        assert tree.host.handles["b"].state is PluginState.ACTIVE


# ════════════════════════════════════════════════════════════
# 5. 类形态档口 —— class plugin
# ════════════════════════════════════════════════════════════


class TestClassPlugin:
    """类形态的档口：apply 是类方法，返回实例作为服务。"""

    @pytest.mark.asyncio
    async def test_is_class_constructor_called(self) -> None:
        """类形态档口的 apply 被调用 → 构造函数执行，实例注册为服务。"""
        constructed: list[Any] = []

        class MyPlugin:
            name = "class-plugin"
            inject: tuple[str, ...] = ()
            provides = "class-svc"
            Config = PluginConfig

            def __init__(self) -> None:
                pass

            @classmethod
            def apply(cls, ctx: Any, config: Any) -> Any:
                instance = cls()
                constructed.append((ctx, config))
                return instance

        tree = await Loader().load([_entry("class-plugin", MyPlugin)])
        handle = tree.host.handles["class-plugin"]
        assert handle.state is PluginState.ACTIVE
        assert len(constructed) == 1
        # Service should be auto-mounted under provides key
        svc = tree.host.get_service("class-svc")
        assert svc is not None
