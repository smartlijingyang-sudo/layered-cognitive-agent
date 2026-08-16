"""DSH-fusion 四模式测试：waterfall 分发 / tool pipeline / journal 增量投影 / branded IDs。

覆盖：
1. SimpleEventBus waterfall 链式分发 + 短路
2. SimpleEventBus serial 串行分发
3. DefaultToolExecutionPipeline 五阶段管线
4. RunStore append 边界验证 + derive_events 增量投影
5. Branded IDs 工厂
6. assert_never 穷尽检查
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.exhaustive import assert_never
from lca.contracts.atoms.ids import (
    new_delegation_id,
    new_run_id,
    new_trace_id,
)
from lca.contracts.models.observability.journal import (
    DecisionMade,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.protocols.tool_pipeline import (
    ToolExecutionContext,
    ToolExecutionResult,
    ToolPostDecision,
    ToolPreDecision,
)
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer0_infra.tool_pipeline import DefaultToolExecutionPipeline
from lca.layer1_cognitive.event_bus import SimpleEventBus

# ── 1. Waterfall 事件分发 ─────────────────────────────────────


class TestWaterfallDispatch:
    """waterfall around-middleware 链：listener 收到 (payload, next)。"""

    @pytest.mark.asyncio
    async def test_waterfall_chain_passes_through(self) -> None:
        bus = SimpleEventBus()
        log: list[str] = []

        async def listener_a(payload: dict, next_fn: any) -> dict:
            log.append("a:before")
            result = await next_fn(payload)
            log.append("a:after")
            return result

        async def listener_b(payload: dict, next_fn: any) -> dict:
            log.append("b:before")
            result = await next_fn(payload)
            log.append("b:after")
            return result

        bus.on_waterfall("test", listener_a)
        bus.on_waterfall("test", listener_b)

        result = await bus.waterfall("test", {"value": 1})
        assert result == {"value": 1}
        assert log == ["a:before", "b:before", "b:after", "a:after"]

    @pytest.mark.asyncio
    async def test_waterfall_short_circuit(self) -> None:
        """不调用 next() = 短路，后续 listener 不执行。"""
        bus = SimpleEventBus()
        log: list[str] = []

        async def deny_listener(payload: dict, next_fn: any) -> dict:
            log.append("deny")
            return {"denied": True}  # 不调用 next_fn

        async def should_not_run(payload: dict, next_fn: any) -> dict:
            log.append("should_not_run")
            return await next_fn(payload)

        bus.on_waterfall("auth", deny_listener)
        bus.on_waterfall("auth", should_not_run)

        result = await bus.waterfall("auth", {"value": 1})
        assert result == {"denied": True}
        assert log == ["deny"]

    @pytest.mark.asyncio
    async def test_waterfall_mutation(self) -> None:
        """listener 可以修改 payload 后传递给下游。"""
        bus = SimpleEventBus()

        async def add_header(payload: dict, next_fn: any) -> dict:
            payload["header_added"] = True
            return await next_fn(payload)

        async def add_footer(payload: dict, next_fn: any) -> dict:
            payload["footer_added"] = True
            return await next_fn(payload)

        bus.on_waterfall("enrich", add_header)
        bus.on_waterfall("enrich", add_footer)

        result = await bus.waterfall("enrich", {"value": 1})
        assert result == {"value": 1, "header_added": True, "footer_added": True}

    @pytest.mark.asyncio
    async def test_waterfall_no_listeners(self) -> None:
        """无 listener 时直接返回初始值。"""
        bus = SimpleEventBus()
        result = await bus.waterfall("empty", {"value": 42})
        assert result == {"value": 42}


# ── 2. Serial 分发 ─────────────────────────────────────────────


class TestSerialDispatch:
    """serial 串行决策链：最后一个 listener 的值胜出。"""

    @pytest.mark.asyncio
    async def test_serial_chain(self) -> None:
        bus = SimpleEventBus()

        async def add_one(value: int) -> int:
            return value + 1

        async def double(value: int) -> int:
            return value * 2

        bus.on_serial("calc", add_one)
        bus.on_serial("calc", double)

        # add_one(10) → 11, double(11) → 22
        result = await bus.serial("calc", 10)
        assert result == 22

    @pytest.mark.asyncio
    async def test_serial_no_listeners(self) -> None:
        bus = SimpleEventBus()
        result = await bus.serial("empty", 99)
        assert result == 99


# ── 3. Tool Execution Pipeline ─────────────────────────────────


class TestToolExecutionPipeline:
    """五阶段管线：pre → guards → execute → post → finalize。"""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self) -> None:
        pipeline = DefaultToolExecutionPipeline()
        log: list[str] = []

        async def pre(ctx: ToolExecutionContext) -> ToolPreDecision:
            log.append("pre")
            return ToolPreDecision(kind="allow")

        def guard(ctx: ToolExecutionContext) -> str | None:
            log.append("guard")
            return None  # abstain

        async def executor(ctx: ToolExecutionContext) -> ToolExecutionResult:
            log.append("execute")
            return ToolExecutionResult(ok=True, output="done", latency_ms=10)

        async def post(ctx: ToolExecutionContext, result: ToolExecutionResult) -> ToolPostDecision:
            log.append("post")
            return ToolPostDecision(kind="accept")

        def finalize(result: ToolExecutionResult) -> ToolExecutionResult:
            log.append("finalize")
            return result

        pipeline.add_pre_execute(pre)
        pipeline.add_guard(guard)
        pipeline.set_executor(executor)
        pipeline.add_post_execute(post)
        pipeline.add_finalize(finalize)

        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is True
        assert result.output == "done"
        assert log == ["pre", "guard", "execute", "post", "finalize"]

    @pytest.mark.asyncio
    async def test_pre_execute_deny(self) -> None:
        """pre-execute deny 短路，不执行 tool body。"""
        pipeline = DefaultToolExecutionPipeline()

        async def deny(ctx: ToolExecutionContext) -> ToolPreDecision:
            return ToolPreDecision(kind="deny", reason="forbidden")

        pipeline.add_pre_execute(deny)
        pipeline.set_executor(lambda ctx: ToolExecutionResult(ok=True, output="should_not_run"))

        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is False
        assert "forbidden" in result.error

    @pytest.mark.asyncio
    async def test_monotonic_guard_deny(self) -> None:
        """单调守卫 deny 短路，且不能翻回 allow。"""
        pipeline = DefaultToolExecutionPipeline()

        def guard_deny(ctx: ToolExecutionContext) -> str | None:
            return "sandbox violation"

        def guard_allow(ctx: ToolExecutionContext) -> str | None:
            return None  # 试图翻回 allow

        pipeline.add_guard(guard_deny)
        pipeline.add_guard(guard_allow)
        pipeline.set_executor(lambda ctx: ToolExecutionResult(ok=True, output="should_not_run"))

        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is False
        assert "sandbox violation" in result.error

    @pytest.mark.asyncio
    async def test_post_execute_block(self) -> None:
        """post-execute block 阻止结果。"""
        pipeline = DefaultToolExecutionPipeline()

        async def executor(ctx: ToolExecutionContext) -> ToolExecutionResult:
            return ToolExecutionResult(ok=True, output="sensitive_data")

        async def block_sensitive(
            ctx: ToolExecutionContext, result: ToolExecutionResult
        ) -> ToolPostDecision:
            return ToolPostDecision(kind="block", content="contains sensitive data")

        pipeline.set_executor(executor)
        pipeline.add_post_execute(block_sensitive)

        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is False
        assert "sensitive" in result.error

    @pytest.mark.asyncio
    async def test_finalize_exception_isolated(self) -> None:
        """finalize 异常被隔离，不影响结果。"""
        pipeline = DefaultToolExecutionPipeline()

        async def executor(ctx: ToolExecutionContext) -> ToolExecutionResult:
            return ToolExecutionResult(ok=True, output="good")

        def broken_finalize(result: ToolExecutionResult) -> ToolExecutionResult:
            raise RuntimeError("finalize exploded")

        pipeline.set_executor(executor)
        pipeline.add_finalize(broken_finalize)

        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is True
        assert result.output == "good"

    @pytest.mark.asyncio
    async def test_no_executor(self) -> None:
        pipeline = DefaultToolExecutionPipeline()
        ctx = ToolExecutionContext(tool_name="test_tool", args={})
        result = await pipeline.run(ctx)
        assert result.ok is False
        assert "no executor" in result.error


# ── 4. Journal 增量投影 + append 边界验证 ─────────────────────


class TestJournalAppendBoundary:
    """Append 边界验证：frozen 断言 + 深拷贝隔离。"""

    def test_frozen_dataclass_isolation(self) -> None:
        """frozen dataclass 通过 append 边界验证。"""
        store = RunStore()
        event = DecisionMade(step=1, action_type="use_tool", tool_name="calculator")
        stamped = store.append(event)
        assert stamped.event.step == 1
        assert stamped.event.tool_name == "calculator"

    def test_deep_copy_isolation(self) -> None:
        """append 后调用方修改原始对象不影响 log 内副本。"""
        store = RunStore()
        event = DecisionMade(step=1, action_type="use_tool", tool_name="calculator")
        stamped = store.append(event)
        # log 内的事件与原始对象是独立的
        assert stamped.event.tool_name == "calculator"
        # 原始对象被深拷贝隔离，stamped.event 是独立副本
        assert stamped.event is not event


class TestJournalIncrementalProjection:
    """derive_events 增量投影：首次全量，后续增量扩展。"""

    def test_derive_events_first_call(self) -> None:
        store = RunStore()
        store.append(TeamRunStarted(team_id="t1", strategy_key="board"))
        store.append(DecisionMade(step=1, action_type="respond"))
        store.append(TeamRunFinished(status="completed"))

        # 只投影容器事件
        def is_container(e: any) -> bool:
            return isinstance(e.event, (TeamRunStarted, TeamRunFinished))

        result = store.derive_events(is_container)
        assert len(result) == 2
        assert isinstance(result[0].event, TeamRunStarted)
        assert isinstance(result[1].event, TeamRunFinished)

    def test_derive_events_incremental(self) -> None:
        """append 新事件后，derive_events 只扫描新增部分。"""
        store = RunStore()
        store.append(DecisionMade(step=1, action_type="respond"))

        call_count = 0

        def counting_predicate(e: any) -> bool:
            nonlocal call_count
            call_count += 1
            return isinstance(e.event, DecisionMade)

        # 首次调用
        result1 = store.derive_events(counting_predicate)
        assert len(result1) == 1
        first_call_count = call_count

        # 追加新事件
        store.append(DecisionMade(step=2, action_type="use_tool"))

        # 再次调用：只扫描新增事件
        result2 = store.derive_events(counting_predicate)
        assert len(result2) == 2
        # 增量扫描：调用次数 = 新增事件数（1），不是全量（3）
        assert call_count == first_call_count + 1

    def test_derive_events_cache_invalidation(self) -> None:
        """不同 predicate 各自独立缓存。"""
        store = RunStore()
        store.append(TeamRunStarted(team_id="t1"))
        store.append(DecisionMade(step=1))

        def is_team(e: any) -> bool:
            return isinstance(e.event, TeamRunStarted)

        def is_decision(e: any) -> bool:
            return isinstance(e.event, DecisionMade)

        team_result = store.derive_events(is_team)
        decision_result = store.derive_events(is_decision)
        assert len(team_result) == 1
        assert len(decision_result) == 1


# ── 5. Branded IDs ────────────────────────────────────────────


class TestBrandedIds:
    """品牌化 ID：类型层面防混传，运行时零成本。"""

    def test_new_run_id(self) -> None:
        rid = new_run_id()
        assert isinstance(rid, str)
        assert rid.startswith("run_")
        assert len(rid) > 4

    def test_new_trace_id(self) -> None:
        tid = new_trace_id()
        assert isinstance(tid, str)
        assert tid.startswith("trace_")

    def test_new_delegation_id(self) -> None:
        did = new_delegation_id()
        assert isinstance(did, str)
        assert did.startswith("delegation_")

    def test_ids_are_unique(self) -> None:
        ids = {new_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_newtype_is_str_at_runtime(self) -> None:
        """NewType 在运行时就是 str——类型检查在 mypy 层。"""
        rid = new_run_id()
        assert isinstance(rid, str)
        # 可以当 str 用
        assert rid.upper().startswith("RUN_")


# ── 6. assert_never 穷尽检查 ─────────────────────────────────


class TestAssertNever:
    """assert_never：match 未覆盖时抛异常。"""

    def test_assert_never_raises(self) -> None:
        with pytest.raises(AssertionError, match="未覆盖"):
            assert_never("unhandled_type")  # type: ignore[arg-type]

    def test_match_exhaustive_pattern(self) -> None:
        """完整的 match + assert_never 模式。"""

        def classify(event_type: str) -> str:
            match event_type:
                case "TeamRunStarted":
                    return "container"
                case "TeamRunFinished":
                    return "container"
                case "DecisionMade":
                    return "cognitive"
                case _:
                    assert_never(event_type)  # type: ignore[arg-type]

        assert classify("TeamRunStarted") == "container"
        assert classify("DecisionMade") == "cognitive"
        # 未覆盖的类型会抛异常
        with pytest.raises(AssertionError):
            classify("UnknownEvent")  # type: ignore[arg-type]
