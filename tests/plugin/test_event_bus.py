"""广场广播系统——EventBus 的 5 种分发方式与生命周期管理。

美食广场中央有一套广播系统，管理方可以通过它向各档口发布通知。
根据场景不同，广播有 5 种分发模式：

- **emit（通知一下就行）**：播完拉倒，不管档口回什么。
- **parallel（所有档口同时响应）**：并发通知，所有档口同时处理，出错了打包汇报。
- **serial（依次确认直到有人拦截）**：按注册顺序逐个通知，
  遇到第一个返回非 None 非 False 的值就停下来。
- **bail（同步拦截）**：同步版本——逐个通知，遇到拦截值就立即返回。
- **waterfall（层层审批链）**：中间件模式——每个 listener 拿到上一环节的结果，
  决定是否继续往下传递，最终到达 terminal。

此外还有：listener 注册/注销（档口入驻广播列表）、prepend 排序、global 标记等辅助机制。
"""

from __future__ import annotations

import asyncio

import pytest

from lca.layer0_infra.plugin.kernel._events import EventBus

# ── Registration ────────────────────────────────────────────


class TestRegistration:
    """档口入驻广播列表——注册、注销、清除的规矩。"""

    def test_on_returns_token_tuple(self) -> None:
        """注册后返回一个令牌（事件名, 序号），以后注销用。"""
        bus = EventBus()
        token = bus.on("owner1", "test.event", lambda: None)
        assert isinstance(token, tuple)
        assert len(token) == 2
        assert token[0] == "test.event"
        assert isinstance(token[1], int)

    def test_tokens_are_unique(self) -> None:
        """每次注册拿到不同的序号——就算事件和档口名一样。"""
        bus = EventBus()
        t1 = bus.on("o", "ev", lambda: None)
        t2 = bus.on("o", "ev", lambda: None)
        assert t1[1] != t2[1]

    def test_off_removes_listener(self) -> None:
        """注销后——广播不再送达该档口。"""
        bus = EventBus()
        calls: list[str] = []
        token = bus.on("o", "ev", lambda: calls.append("x"))
        assert bus.off(token) is True
        asyncio.run(bus.emit("ev"))
        assert calls == []

    def test_off_returns_false_for_unknown_token(self) -> None:
        """注销一个不存在的令牌——返回 False，表示无事可撤。"""
        bus = EventBus()
        assert bus.off(("nope", 999)) is False

    def test_off_returns_false_for_already_removed(self) -> None:
        """同一个令牌注销两次——第二次返回 False。"""
        bus = EventBus()
        token = bus.on("o", "ev", lambda: None)
        assert bus.off(token) is True
        assert bus.off(token) is False

    def test_remove_all_for_clears_one_owner(self) -> None:
        """按档口名清除——只移除该档口的所有监听，其他档口不受影响。"""
        bus = EventBus()
        calls: list[str] = []
        bus.on("alice", "ev", lambda: calls.append("alice"))
        bus.on("alice", "ev", lambda: calls.append("alice2"))
        bus.on("bob", "ev", lambda: calls.append("bob"))
        bus.remove_all_for("alice")
        asyncio.run(bus.emit("ev"))
        assert calls == ["bob"]

    def test_remove_all_for_unknown_owner_is_noop(self) -> None:
        """清除一个不存在的档口——静默无操作，不影响已注册的档口。"""
        bus = EventBus()
        calls: list[str] = []
        bus.on("alice", "ev", lambda: calls.append("alice"))
        bus.remove_all_for("nobody")
        asyncio.run(bus.emit("ev"))
        assert calls == ["alice"]


# ── emit mode ───────────────────────────────────────────────


class TestEmit:
    """广播模式一：通知一下就行——播完拉倒，不管返回值。"""

    async def test_fires_sync_listeners(self) -> None:
        """同步监听器也会按注册顺序被触发。"""
        bus = EventBus()
        calls: list[int] = []
        bus.on("o", "ev", lambda: calls.append(1))
        bus.on("o", "ev", lambda: calls.append(2))
        await bus.emit("ev")
        assert calls == [1, 2]

    async def test_passes_args(self) -> None:
        """广播可以携带参数——所有监听器都能收到。"""
        bus = EventBus()
        captured: list[tuple] = []
        bus.on("o", "ev", lambda *a: captured.append(a))
        await bus.emit("ev", "x", 42)
        assert captured == [("x", 42)]

    async def test_ignores_return_values(self) -> None:
        """监听器的返回值被忽略——emit 本身返回 None。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: 42)
        bus.on("o", "ev", lambda: "hello")
        result = await bus.emit("ev")
        assert result is None

    async def test_no_listeners_no_error(self) -> None:
        """没有人收听这条广播——静默无事发生。"""
        bus = EventBus()
        await bus.emit("nonexistent")


# ── parallel mode ───────────────────────────────────────────


class TestParallel:
    """广播模式二：所有档口同时响应——并发执行，出错打包汇报。"""

    async def test_runs_all_concurrently(self) -> None:
        """所有监听器并发启动——都跑完才算结束。"""
        bus = EventBus()
        calls: list[str] = []

        async def a() -> None:
            calls.append("a")

        async def b() -> None:
            calls.append("b")

        bus.on("o", "ev", a)
        bus.on("o", "ev", b)
        await bus.parallel("ev")
        assert sorted(calls) == ["a", "b"]

    async def test_exception_group_on_errors(self) -> None:
        """多个监听器同时出错——用 ExceptionGroup 打包汇报。"""
        bus = EventBus()

        async def bad1() -> None:
            raise ValueError("boom1")

        async def bad2() -> None:
            raise RuntimeError("boom2")

        bus.on("o", "ev", bad1)
        bus.on("o", "ev", bad2)
        with pytest.raises(ExceptionGroup) as exc_info:  # noqa: F821
            await bus.parallel("ev")
        assert len(exc_info.value.exceptions) == 2

    async def test_empty_no_error(self) -> None:
        """没有监听器——静默无事发生。"""
        bus = EventBus()
        await bus.parallel("nonexistent")

    async def test_passes_args(self) -> None:
        """并发广播也能把参数送达每个监听器。"""
        bus = EventBus()
        captured: list[tuple] = []

        async def grab(*args: object) -> None:
            captured.append(args)

        bus.on("o", "ev", grab)
        await bus.parallel("ev", 1, 2)
        assert captured == [(1, 2)]


# ── serial mode ─────────────────────────────────────────────


class TestSerial:
    """广播模式三：依次确认直到有人拦截——顺序执行，遇到拦截值就停。"""

    async def test_awaits_in_order(self) -> None:
        """监听器按注册顺序依次执行——先到先得。"""
        bus = EventBus()
        order: list[int] = []

        async def step(n: int) -> None:
            await asyncio.sleep(0)
            order.append(n)

        bus.on("o", "ev", lambda: step(1))
        bus.on("o", "ev", lambda: step(2))
        bus.on("o", "ev", lambda: step(3))
        await bus.serial("ev")
        assert order == [1, 2, 3]

    async def test_bails_on_first_non_none_non_false(self) -> None:
        """第一个返回真值（非 None 非 False）的监听器拦截了广播——后面的不再执行。"""
        bus = EventBus()
        calls: list[int] = []

        async def first() -> None:
            calls.append(1)

        def second() -> int:
            calls.append(2)
            return 42

        async def third() -> None:
            calls.append(3)

        bus.on("o", "ev", first)
        bus.on("o", "ev", second)
        bus.on("o", "ev", third)
        result = await bus.serial("ev")
        assert result == 42
        assert calls == [1, 2]

    async def test_false_does_not_bail(self) -> None:
        """返回 False 不算拦截——链条继续往下走。"""
        bus = EventBus()
        calls: list[int] = []
        bus.on("o", "ev", lambda: (calls.append(1), False)[1])
        bus.on("o", "ev", lambda: (calls.append(2), None)[1])
        bus.on("o", "ev", lambda: calls.append(3))
        result = await bus.serial("ev")
        assert result is None
        assert calls == [1, 2, 3]

    async def test_returns_none_when_no_bail(self) -> None:
        """没人拦截——serial 返回 None。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: None)
        bus.on("o", "ev", lambda: False)
        result = await bus.serial("ev")
        assert result is None

    async def test_returns_none_with_no_listeners(self) -> None:
        """没有监听器——serial 返回 None。"""
        bus = EventBus()
        result = await bus.serial("ev")
        assert result is None

    async def test_bail_value_zero_stops_chain(self) -> None:
        """返回 0 也算拦截——0 是 truthy-falsy 边界之外，但 serial 把它视为拦截值。"""
        bus = EventBus()
        calls: list[int] = []
        bus.on("o", "ev", lambda: (calls.append(1), 0)[1])
        bus.on("o", "ev", lambda: calls.append(2))
        result = await bus.serial("ev")
        assert result == 0
        assert calls == [1]


# ── bail mode (sync) ───────────────────────────────────────


class TestBail:
    """广播模式四：同步拦截——逐个通知，遇到拦截值立即返回。"""

    def test_sync_dispatch_stops_at_bail(self) -> None:
        """同步逐个通知——遇到第一个拦截值「stop」就停。"""
        bus = EventBus()
        calls: list[int] = []
        bus.on("o", "ev", lambda: calls.append(1))
        bus.on("o", "ev", lambda: (calls.append(2), "stop")[1])
        bus.on("o", "ev", lambda: calls.append(3))
        result = bus.bail("ev")
        assert result == "stop"
        assert calls == [1, 2]

    def test_returns_none_when_no_bail(self) -> None:
        """没人拦截——bail 返回 None。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: None)
        bus.on("o", "ev", lambda: False)
        assert bus.bail("ev") is None

    def test_returns_none_with_no_listeners(self) -> None:
        """没有监听器——bail 返回 None。"""
        bus = EventBus()
        assert bus.bail("ev") is None

    def test_passes_args(self) -> None:
        """同步广播也能把参数送达每个监听器。"""
        bus = EventBus()
        captured: list[tuple] = []
        bus.on("o", "ev", lambda *a: captured.append(a))
        bus.bail("ev", "hello", 99)
        assert captured == [("hello", 99)]

    def test_truthy_string_bails(self) -> None:
        """返回一个非空字符串——也算拦截，bail 把它带回。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: "intercepted")
        assert bus.bail("ev") == "intercepted"


# ── waterfall mode ──────────────────────────────────────────


class TestWaterfall:
    """广播模式五：层层审批链——中间件模式，每个环节可以修改、拦截或传递。"""

    async def test_middleware_chain(self) -> None:
        """最基本的中间件链——放行到 terminal，返回 terminal 的结果。"""
        bus = EventBus()

        def middleware(next_cb):  # type: ignore[no-untyped-def]
            return next_cb()

        def terminal() -> int:
            return 100

        bus.on("o", "ev", middleware)
        result = await bus.waterfall("ev", terminal=terminal)
        assert result == 100

    async def test_short_circuit(self) -> None:
        """中间件短路——auth_gate 返回 403，后面的 listener 和 terminal 都不执行。"""
        bus = EventBus()
        calls: list[str] = []

        def auth_gate(next_cb):  # type: ignore[no-untyped-def]
            calls.append("auth")
            return 403

        def should_not_run(next_cb):  # type: ignore[no-untyped-def]
            calls.append("nope")
            return next_cb()

        def terminal() -> int:
            calls.append("terminal")
            return 200

        bus.on("o", "ev", auth_gate)
        bus.on("o", "ev", should_not_run)
        result = await bus.waterfall("ev", terminal=terminal)
        assert result == 403
        assert calls == ["auth"]

    async def test_mutation_passthrough_via_shared_state(self) -> None:
        """waterfall 审批链：每个 listener 可以修改共享状态后传递给下游。"""
        bus = EventBus()
        state: dict[str, int] = {"count": 0}

        def add_one(value, next_cb):  # type: ignore[no-untyped-def]
            value["count"] += 1
            return next_cb()

        def double(value, next_cb):  # type: ignore[no-untyped-def]
            value["count"] *= 2
            return next_cb()

        def terminal() -> int:
            return state["count"]

        bus.on("o", "ev", add_one)
        bus.on("o", "ev", double)
        result = await bus.waterfall("ev", state, terminal=terminal)
        # add_one: 0→1, double: 1→2
        assert result == 2

    async def test_next_passes_original_args(self) -> None:
        """next_cb() 会把原始参数原封不动传给下一个中间件。"""
        bus = EventBus()
        captured: list[tuple] = []

        def mw1(a, b, next_cb):  # type: ignore[no-untyped-def]
            return next_cb()

        def mw2(a, b, next_cb):  # type: ignore[no-untyped-def]
            captured.append((a, b))
            return next_cb()

        bus.on("o", "ev", mw1)
        bus.on("o", "ev", mw2)
        await bus.waterfall("ev", "x", "y", terminal=lambda: None)
        assert captured == [("x", "y")]

    async def test_no_listeners_calls_terminal(self) -> None:
        """没有中间件——直接调用 terminal 拿结果。"""
        bus = EventBus()
        result = await bus.waterfall("ev", terminal=lambda: 99)
        assert result == 99

    async def test_passes_args_to_each_middleware(self) -> None:
        """原始参数会传递给链条上的每一个中间件。"""
        bus = EventBus()
        captured: list[tuple] = []

        def mw1(a, b, next_cb):  # type: ignore[no-untyped-def]
            captured.append(("mw1", a, b))
            return next_cb()

        def mw2(a, b, next_cb):  # type: ignore[no-untyped-def]
            captured.append(("mw2", a, b))
            return next_cb()

        bus.on("o", "ev", mw1)
        bus.on("o", "ev", mw2)
        await bus.waterfall("ev", "x", "y", terminal=lambda: None)
        assert captured == [("mw1", "x", "y"), ("mw2", "x", "y")]

    async def test_async_middleware(self) -> None:
        """异步中间件也能正常工作——await next_cb() 一路传递。"""
        bus = EventBus()

        async def async_mw(next_cb):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0)
            return await next_cb()

        async def terminal() -> int:
            return 42

        bus.on("o", "ev", async_mw)
        result = await bus.waterfall("ev", terminal=terminal)
        assert result == 42


# ── prepend ordering ────────────────────────────────────────


class TestPrepend:
    """广播列表的排序——prepend=True 让新档口插到队列最前面。"""

    async def test_prepend_adds_before_existing(self) -> None:
        """后注册但 prepend=True——排到已有档口前面。"""
        bus = EventBus()
        order: list[str] = []
        bus.on("o", "ev", lambda: order.append("A"))
        bus.on("o", "ev", lambda: order.append("B"), prepend=True)
        await bus.emit("ev")
        assert order == ["B", "A"]

    async def test_multiple_prepends_reverse_order(self) -> None:
        """连续 prepend 两次——后来的排更前面，形成逆序。"""
        bus = EventBus()
        order: list[str] = []
        bus.on("o", "ev", lambda: order.append("A"))
        bus.on("o", "ev", lambda: order.append("P"), prepend=True)
        bus.on("o", "ev", lambda: order.append("Q"), prepend=True)
        await bus.emit("ev")
        assert order == ["Q", "P", "A"]

    async def test_mixed_prepend_and_append(self) -> None:
        """prepend 和 append 混用——prepend 插队到最前，append 排到末尾。"""
        bus = EventBus()
        order: list[str] = []
        bus.on("o", "ev", lambda: order.append("A"))
        bus.on("o", "ev", lambda: order.append("P"), prepend=True)
        bus.on("o", "ev", lambda: order.append("B"))
        bus.on("o", "ev", lambda: order.append("Q"), prepend=True)
        bus.on("o", "ev", lambda: order.append("C"))
        await bus.emit("ev")
        assert order == ["Q", "P", "A", "B", "C"]


# ── global filtering ────────────────────────────────────────


class TestGlobal:
    """全局监听标记——global_=True 的档口在广播分发中始终参与。"""

    async def test_global_listener_included_in_dispatch(self) -> None:
        """全局监听器和本地监听器一起参与 emit 分发。"""
        bus = EventBus()
        calls: list[str] = []
        bus.on("o", "ev", lambda: calls.append("global"), global_=True)
        bus.on("o", "ev", lambda: calls.append("local"))
        await bus.emit("ev")
        assert sorted(calls) == ["global", "local"]

    async def test_global_flag_stored_in_record(self) -> None:
        """global_ 标记被记录在 listener 内部——可以在 _events 里看到。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: None, global_=True)
        bus.on("o", "ev", lambda: None)
        listeners = bus._events["ev"]
        assert listeners[0].global_ is True
        assert listeners[1].global_ is False

    async def test_global_and_non_global_coexist(self) -> None:
        """全局和本地监听器共存——广播时都会收到通知。"""
        bus = EventBus()
        calls: list[str] = []
        bus.on("alice", "ev", lambda: calls.append("alice"))
        bus.on("bob", "ev", lambda: calls.append("bob"), global_=True)
        bus.on("carol", "ev", lambda: calls.append("carol"))
        await bus.emit("ev")
        assert sorted(calls) == ["alice", "bob", "carol"]


# ── Edge cases ──────────────────────────────────────────────


class TestEdgeCases:
    """广播系统的边界场景——多档口、多事件、异常传播、大批量注册等。"""

    async def test_multiple_owners_same_event(self) -> None:
        """多个档口监听同一事件——全部收到通知，按注册顺序执行。"""
        bus = EventBus()
        calls: list[str] = []
        bus.on("alice", "ev", lambda: calls.append("alice"))
        bus.on("bob", "ev", lambda: calls.append("bob"))
        bus.on("carol", "ev", lambda: calls.append("carol"))
        await bus.emit("ev")
        assert calls == ["alice", "bob", "carol"]

    async def test_different_events_isolated(self) -> None:
        """不同事件互不干扰——播 A 不会送达 B 的听众。"""
        bus = EventBus()
        calls_a: list[str] = []
        calls_b: list[str] = []
        bus.on("o", "a", lambda: calls_a.append("x"))
        bus.on("o", "b", lambda: calls_b.append("y"))
        await bus.emit("a")
        assert calls_a == ["x"]
        assert calls_b == []

    async def test_listener_raises_in_emit_propagates(self) -> None:
        """emit 模式下监听器抛异常——异常向上传播。"""
        bus = EventBus()

        def bad() -> None:
            raise ValueError("boom")

        bus.on("o", "ev", bad)
        with pytest.raises(ValueError, match="boom"):
            await bus.emit("ev")

    async def test_listener_raises_in_serial_propagates(self) -> None:
        """serial 模式下监听器抛异常——异常向上传播。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: None)

        def bad() -> None:
            raise RuntimeError("serial-boom")

        bus.on("o", "ev", bad)
        with pytest.raises(RuntimeError, match="serial-boom"):
            await bus.serial("ev")

    def test_listener_raises_in_bail_propagates(self) -> None:
        """bail 模式下监听器抛异常——异常向上传播。"""
        bus = EventBus()

        def bad() -> None:
            raise RuntimeError("bail-boom")

        bus.on("o", "ev", bad)
        with pytest.raises(RuntimeError, match="bail-boom"):
            bus.bail("ev")

    async def test_many_listeners(self) -> None:
        """500 个监听器——全部收到通知，顺序正确。"""
        bus = EventBus()
        calls: list[int] = []
        for i in range(500):
            bus.on("o", "ev", lambda n=i: calls.append(n))
        await bus.emit("ev")
        assert len(calls) == 500
        assert calls == list(range(500))

    async def test_remove_all_then_emit(self) -> None:
        """清空所有监听器后再广播——无事发生。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: None)
        bus.remove_all_for("o")
        await bus.emit("ev")

    def test_remove_all_for_then_sync_bail(self) -> None:
        """清空后同步 bail——返回 None，没有拦截者。"""
        bus = EventBus()
        bus.on("o", "ev", lambda: "value")
        bus.remove_all_for("o")
        assert bus.bail("ev") is None

    async def test_off_one_of_many(self) -> None:
        """注销其中一个——其余监听器照常工作。"""
        bus = EventBus()
        calls: list[str] = []
        t1 = bus.on("o", "ev", lambda: calls.append("a"))
        bus.on("o", "ev", lambda: calls.append("b"))
        bus.on("o", "ev", lambda: calls.append("c"))
        bus.off(t1)
        await bus.emit("ev")
        assert calls == ["b", "c"]
