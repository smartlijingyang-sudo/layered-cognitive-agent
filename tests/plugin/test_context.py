"""档口与广场的交互窗口测试 —— mount / require / effect / events / child。

每个档口通过交互窗口（PluginContext）与美食广场管理处沟通：
- mount：「我带来了一台设备，请登记」；require：「我需要一台设备」
- effect：「我走的时候记得帮我关灯」—— 逆序执行清理
- events：监听广场广播（on / once / bail / serial / waterfall）
- child：档口可以开一个子窗口，用于某次特定运营任务
"""

from __future__ import annotations

import contextlib

import pytest

from lca.layer0_infra.plugin.kernel import (
    DependencyUnavailable,
    PluginError,
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
)
from lca.layer0_infra.plugin.kernel._context import PluginContext


def _make_ctx(
    *,
    entry_id: str = "test",
    injected: tuple[str, ...] = (),
    state: PluginState = PluginState.LOADING,
) -> PluginContext:
    """快速搭建一个模拟档口 + 交互窗口的测试环境。"""
    host = PluginHost()
    handle = PluginHandle(
        entry_id=entry_id,
        spec=PluginSpec(name=entry_id, apply=lambda ctx, cfg: None),
        config={},
        injected=injected,
        state=state,
    )
    host.register_handle(handle)
    return PluginContext(host, handle)


# ── Mount / Require / Get / Set ─────────────────────────────


class TestMountRequireGet:
    """设备登记与领取测试 —— 档口通过窗口向广场登记或领取设备。"""

    def test_mount_then_require(self) -> None:
        """档口登记一台设备后，立刻就能领取它——即存即取。"""
        ctx = _make_ctx(injected=("llm",))
        ctx.mount("llm", "llm-service")
        assert ctx.require("llm") == "llm-service"

    def test_require_missing_raises_dependency_unavailable(self) -> None:
        """领取一台未登记的设备——报错：依赖不可用。"""
        ctx = _make_ctx(injected=("llm",))
        with pytest.raises(DependencyUnavailable):
            ctx.require("llm")

    def test_get_returns_none_for_missing(self) -> None:
        """用 get 查一台不存在的设备——安静返回 None。"""
        ctx = _make_ctx()
        assert ctx.get("nonexistent") is None

    def test_get_returns_default(self) -> None:
        """get 支持默认值——查不到就返回兜底。"""
        ctx = _make_ctx()
        assert ctx.get("x", 42) == 42

    def test_mount_empty_key_raises(self) -> None:
        """设备名不能为空——管理处拒绝无名设备。"""
        ctx = _make_ctx()
        with pytest.raises(ValueError, match="empty"):
            ctx.mount("", object())

    def test_require_without_inject_raises_plugin_error(self) -> None:
        """没有在入驻申请表上声明需要的设备，直接领取会被拒绝。"""
        ctx = _make_ctx(injected=())
        with pytest.raises(PluginError, match="must declare"):
            ctx.require("llm")

    def test_mount_same_owner_updates_value(self) -> None:
        """同一个档口重新登记同一台设备——更新为新值，不算重复。"""
        ctx = _make_ctx()
        ctx.mount("x", "v1")
        ctx.mount("x", "v2")  # same handle → update
        assert ctx.get("x") == "v2"

    def test_set_overwrites_owned_service(self) -> None:
        """set 可以覆盖自己已登记的设备值——前提是先 mount 过。"""
        ctx = _make_ctx()
        ctx.mount("x", "v1")
        ctx.set("x", "v2")
        assert ctx.get("x") == "v2"

    def test_set_unowned_service_raises(self) -> None:
        """set 不能凭空操作——没登记过的设备直接 set 会被拒绝。"""
        ctx = _make_ctx()
        # Set without prior mount
        with pytest.raises(PluginError, match="without prior mount"):
            ctx.set("x", "v1")

    def test_set_cross_owner_raises(self) -> None:
        """别的档口登记的设备，你不能动——所有权隔离。"""
        host = PluginHost()
        h1 = PluginHandle(
            entry_id="owner",
            spec=PluginSpec(name="owner", apply=lambda c, cfg: None),
            config={},
            injected=(),
            state=PluginState.LOADING,
        )
        h2 = PluginHandle(
            entry_id="other",
            spec=PluginSpec(name="other", apply=lambda c, cfg: None),
            config={},
            injected=(),
            state=PluginState.LOADING,
        )
        host.register_handle(h1)
        host.register_handle(h2)
        ctx1 = PluginContext(host, h1)
        ctx2 = PluginContext(host, h2)
        ctx1.mount("x", "from-owner")
        with pytest.raises(PluginError, match="owned by"):
            ctx2.set("x", "from-other")

    def test_mount_returns_cleanup(self) -> None:
        """mount 返回一个清理函数——调用后设备从台账上消失。"""
        ctx = _make_ctx()
        cleanup = ctx.mount("x", "val")
        assert callable(cleanup)
        cleanup()
        assert ctx.get("x") is None


# ── Effects ──────────────────────────────────────────────────


class TestEffect:
    """关灯清单测试 —— 「我走的时候记得帮我关灯」，逆序执行清理。"""

    def test_disposer_lifo(self) -> None:
        """关灯清单逆序执行——最后登记的灯最先关。"""
        ctx = _make_ctx()
        log: list[str] = []
        ctx.effect(lambda: log.append("a") or (lambda: log.append("dispose-a")))
        ctx.effect(lambda: log.append("b") or (lambda: log.append("dispose-b")))
        assert log == ["a", "b"]

        # Run disposers LIFO
        while ctx._handle.effects:
            cleanup, _ = ctx._handle.effects.pop()
            cleanup()
        assert log == ["a", "b", "dispose-b", "dispose-a"]

    def test_suppresses_exceptions(self) -> None:
        """关灯时某个灯坏了不影响其他灯——异常被吞掉，其余继续清理。"""
        ctx = _make_ctx()
        log: list[str] = []

        def ok():
            return lambda: log.append("ok")

        def failing():
            return lambda: (_ for _ in ()).throw(RuntimeError("boom"))

        ctx.effect(ok)
        ctx.effect(failing)

        while ctx._handle.effects:
            cleanup, _ = ctx._handle.effects.pop()
            with contextlib.suppress(Exception):
                cleanup()
        assert "ok" in log

    def test_generator_effect(self) -> None:
        """生成器 effect：一次 setup 可以产出多个关灯指令。"""
        ctx = _make_ctx()
        log: list[str] = []

        def gen_setup():
            yield lambda: log.append("d1")
            yield lambda: log.append("d2")

        ctx.effect(gen_setup)
        # 生成器产出的 disposer 被注册为清理函数
        assert len(ctx._handle.effects) >= 1

    def test_effect_none_return(self) -> None:
        """effect 什么都不返回时，仍给出一个可调用的空清理函数。"""
        ctx = _make_ctx()
        cleanup = ctx.effect(lambda: None)
        assert callable(cleanup)

    def test_effect_in_wrong_state_raises(self) -> None:
        """档口还没开始营业（PENDING 状态），不允许登记关灯清单。"""
        ctx = _make_ctx(state=PluginState.PENDING)
        with pytest.raises(PluginError, match="Cannot register effect"):
            ctx.effect(lambda: None)

    def test_effect_meta_recorded(self) -> None:
        """登记关灯清单时可以附带标签——方便日后诊断排查。"""
        ctx = _make_ctx()
        ctx.effect(lambda: None, label="test-effect")
        metas = ctx._handle.get_effects_meta()
        assert any(m.label == "test-effect" for m in metas)


# ── Events ───────────────────────────────────────────────────


class TestEvents:
    """广场广播监听测试 —— 档口订阅广播、一次性监听、管道式传播。"""

    @pytest.mark.asyncio
    async def test_on_and_emit(self) -> None:
        """档口订阅一条广播后，广场播报时档口能收到。"""
        ctx = _make_ctx()
        log: list[str] = []
        ctx.on("test", lambda: log.append("fired"))
        await ctx.emit("test")
        assert log == ["fired"]

    @pytest.mark.asyncio
    async def test_once_fires_only_once(self) -> None:
        """一次性监听：只听一次，第二次播报就不再响应。"""
        ctx = _make_ctx()
        log: list[str] = []
        ctx.once("evt", lambda: log.append("once"))
        await ctx.emit("evt")
        await ctx.emit("evt")
        assert log == ["once"]

    @pytest.mark.asyncio
    async def test_listener_cleanup_on_disposal(self) -> None:
        """档口关门后，之前订阅的广播自动取消——不会再收到消息。"""
        ctx = _make_ctx()
        log: list[str] = []
        ctx.on("evt", lambda: log.append("heard"))

        # Dispose all effects (simulating lifecycle cleanup)
        while ctx._handle.effects:
            cleanup, _ = ctx._handle.effects.pop()
            cleanup()

        await ctx.emit("evt")
        assert log == []

    @pytest.mark.asyncio
    async def test_bail_dispatch(self) -> None:
        """bail 模式：任一监听者返回非空值就立刻中断并返回。"""
        ctx = _make_ctx()
        ctx.on("check", lambda: "stop")
        result = ctx.bail("check")
        assert result == "stop"

    @pytest.mark.asyncio
    async def test_serial_dispatch(self) -> None:
        """serial 模式：依次调用所有监听者，遇到非空返回值即停止。"""
        ctx = _make_ctx()
        ctx.on("calc", lambda v: v + 1)
        result = await ctx.serial("calc", 10)
        # bail value: 11 is non-None/non-False
        assert result == 11

    @pytest.mark.asyncio
    async def test_waterfall_dispatch(self) -> None:
        """waterfall 模式：像流水线审批链，每个监听者可以决定是否继续。"""
        ctx = _make_ctx()
        log: list[str] = []
        ctx.on("chain", lambda v, next_fn: log.append("first") or next_fn())
        ctx.on("chain", lambda v, next_fn: log.append("second") or next_fn())
        result = await ctx.waterfall("chain", 5, terminal=lambda: "done")
        assert log == ["first", "second"]
        assert result == "done"


# ── Child context ────────────────────────────────────────────


class TestChild:
    """子窗口测试 —— 档口可以开一个子窗口，用于某次特定的运营任务。"""

    def test_child_inherits_parent_mounts(self) -> None:
        """子窗口自动继承父窗口登记的所有设备——站在巨人肩膀上。"""
        ctx = _make_ctx(injected=("llm",))
        ctx.mount("llm", "parent-llm")
        child = ctx.child(key="run-1")
        assert child.require("llm") == "parent-llm"

    def test_child_overlay_shadows(self) -> None:
        """子窗口可以在自己的覆盖层上放一台同名设备——遮住父窗口那台。"""
        ctx = _make_ctx(injected=("tools",))
        ctx.mount("tools", "parent-tools")
        child = ctx.child(key="run-1")
        child._overlay["tools"] = "child-tools"
        assert child.require("tools") == "child-tools"
        assert ctx.require("tools") == "parent-tools"

    def test_child_put_without_parent(self) -> None:
        """子窗口可以放一台父窗口没有的设备——自己的东西，父窗口看不到。"""
        ctx = _make_ctx(injected=("plane",))
        child = ctx.child(key="run-1")
        child._overlay["plane"] = "this-run"
        assert child.require("plane") == "this-run"
        assert ctx.get("plane") is None

    def test_child_empty_key_rejected(self) -> None:
        """子窗口必须有名字——空 key 被拒绝。"""
        ctx = _make_ctx()
        with pytest.raises(ValueError, match="empty"):
            ctx.child(key="")

    def test_child_with_values(self) -> None:
        """创建子窗口时可以直接带入一批覆盖值——开箱即用的装备。"""
        ctx = _make_ctx(injected=("k",))
        child = ctx.child(key="r", values={"k": "overlaid"})
        assert child.get("k") == "overlaid"

    def test_child_parent_property(self) -> None:
        """子窗口能通过 parent 属性找到父窗口——知道谁生了自己。"""
        ctx = _make_ctx()
        child = ctx.child(key="r")
        assert child.parent is ctx

    def test_root_has_no_parent(self) -> None:
        """顶层窗口没有父窗口——它是从石头里蹦出来的。"""
        ctx = _make_ctx()
        assert ctx.parent is None


# ── Accessor / Mixin ─────────────────────────────────────────


class TestAccessorMixin:
    """访问器与混入测试 —— 把服务的方法暴露成窗口的快捷入口。"""

    def test_accessor_defines_computed_property(self) -> None:
        """accessor 定义一个计算属性——每次访问都动态查询。"""
        ctx = _make_ctx()
        ctx.mount("svc", {"greet": lambda: "hi"})
        ctx.accessor("greeting", get=lambda: ctx.get("svc")["greet"]())
        assert ctx._handle._accessors["greeting"]["get"]() == "hi"

    def test_accessor_cleanup_removes(self) -> None:
        """accessor 返回清理函数——调用后快捷入口消失。"""
        ctx = _make_ctx()
        cleanup = ctx.accessor("x", get=lambda: 42)
        assert "x" in ctx._handle._accessors
        cleanup()
        assert "x" not in ctx._handle._accessors

    def test_mixin_forwards_methods(self) -> None:
        """mixin 把服务对象上的方法批量映射成访问器——一键暴露。"""

        class MySvc:
            def alpha(self) -> str:
                return "a"

            def beta(self) -> str:
                return "b"

        ctx = _make_ctx()
        ctx.mount("my_svc", MySvc())
        ctx.mixin("my_svc", ["alpha", "beta"])
        # accessor 的 getter 返回绑定方法（callable），需要再调用一次
        assert ctx._handle._accessors["alpha"]["get"]()() == "a"
        assert ctx._handle._accessors["beta"]["get"]()() == "b"


# ── Properties ───────────────────────────────────────────────


class TestProperties:
    """窗口基本属性测试 —— 档口编号、配置信息等只读属性。"""

    def test_plugin_id(self) -> None:
        """通过窗口能查到自己的档口编号。"""
        ctx = _make_ctx(entry_id="my-plugin")
        assert ctx.plugin_id == "my-plugin"

    def test_config(self) -> None:
        """通过窗口能读到入驻时填写的配置。"""
        host = PluginHost()
        handle = PluginHandle(
            entry_id="t",
            spec=PluginSpec(name="t", apply=lambda c, cfg: None),
            config={"key": "val"},
            injected=(),
            state=PluginState.LOADING,
        )
        host.register_handle(handle)
        ctx = PluginContext(host, handle)
        assert ctx.config == {"key": "val"}


# ── Inject shorthand ────────────────────────────────────────


class TestInject:
    """inject 快捷方式测试 —— 临时创建一个子档口并传入回调。"""

    @pytest.mark.asyncio
    async def test_inject_creates_sub_handle(self) -> None:
        """inject 创建一个子档口，把当前窗口的设备传过去，然后执行回调。"""
        host = PluginHost()
        # Mount a service first
        spec = PluginSpec(name="main", apply=lambda c, cfg: None)
        handle = PluginHandle(
            entry_id="main",
            spec=spec,
            config={},
            injected=(),
            state=PluginState.LOADING,
        )
        host.register_handle(handle)
        ctx = PluginContext(host, handle)
        ctx.mount("llm", "llm-svc")

        log: list[str] = []

        async def callback(sub_ctx: PluginContext) -> None:
            log.append("injected")

        await ctx.inject(("llm",), callback)
        assert "injected" in log
