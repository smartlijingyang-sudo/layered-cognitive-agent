"""五阶段工具执行管线实现。

管线阶段：
    pre-execute → monotonic guards → execute → post-execute → finalize

关键设计：
- 单调守卫：只 deny 或 abstain（返回 None），第一个 deny 赢，顺序无关。
- around-dispatch：execute 阶段支持 timeout/retry 包装。
- post-execute：可 accept / block 结果。
- finalize：纯函数，异常隔离（只记日志不传播）。
- 信号融合：cancel_scope 保证调用方取消传播不被切断。
"""

from __future__ import annotations

import structlog

from lca.contracts.protocols.act.tool_pipeline import (
    ExecuteFn,
    ExecuteMiddlewareFn,
    ExecuteNextFn,
    FinalizeFn,
    GuardFn,
    PostExecuteFn,
    PreExecuteFn,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionResult,
    ToolProvider,
    ToolRenderer,
)

_log = structlog.get_logger("lca.tool_pipeline")


class DefaultToolExecutionPipeline(ToolExecutionPipeline):
    """五阶段工具执行管线的默认实现。"""

    def __init__(self) -> None:
        self._executor: ExecuteFn | None = None
        self._definitions: dict[str, ToolDefinition] = {}
        self._providers: dict[str, ToolProvider] = {}
        self._renderer: ToolRenderer | None = None
        self._pre_execute_fns: list[PreExecuteFn] = []
        self._guard_fns: list[GuardFn] = []
        self._execute_fns: list[ExecuteMiddlewareFn] = []
        self._post_execute_fns: list[PostExecuteFn] = []
        self._finalize_fns: list[FinalizeFn] = []

    def set_executor(self, executor: ExecuteFn) -> None:
        self._executor = executor

    def register_tool(self, definition: ToolDefinition, provider: ToolProvider) -> None:
        """Register a stable declaration with its selected execution provider."""
        self._definitions[definition.name] = definition
        self._providers[definition.name] = provider

    def register_provider(self, tool_name: str, provider: ToolProvider) -> None:
        """Swap only the execution binding, preserving model/UI identity."""
        if tool_name not in self._definitions:
            raise KeyError(f"tool definition is not registered: {tool_name}")
        self._providers[tool_name] = provider

    def set_renderer(self, renderer: ToolRenderer) -> None:
        self._renderer = renderer

    def render(self, tool_name: str) -> object:
        """Render the declaration; concrete provider details never leak here."""
        if self._renderer is None:
            raise RuntimeError("no renderer set")
        try:
            definition = self._definitions[tool_name]
        except KeyError as err:
            raise KeyError(f"tool definition is not registered: {tool_name}") from err
        return self._renderer.render(definition)

    async def execute(
        self,
        tool_name: str,
        args: dict[str, object],
        *,
        invocation_id: str = "",
        agent_role: str = "",
    ) -> ToolExecutionResult:
        """Execute a registered provider through all policy stages."""
        try:
            definition = self._definitions[tool_name]
            provider = self._providers[tool_name]
        except KeyError:
            return ToolExecutionResult(ok=False, error=f"tool is not registered: {tool_name}")
        context = ToolExecutionContext(
            tool_name=tool_name,
            args=args,
            invocation_id=invocation_id,
            agent_role=agent_role,
            definition=definition,
            provider_id=provider.provider_id,
        )
        return await self._run(context, provider.execute)

    def add_pre_execute(self, fn: PreExecuteFn) -> None:
        self._pre_execute_fns.append(fn)

    def add_guard(self, fn: GuardFn) -> None:
        self._guard_fns.append(fn)

    def add_approval_policy(self, fn: PreExecuteFn) -> None:
        self.add_pre_execute(fn)

    def add_sandbox_guard(self, fn: GuardFn) -> None:
        self.add_guard(fn)

    def add_execute(self, fn: ExecuteMiddlewareFn) -> None:
        self._execute_fns.append(fn)

    def add_post_execute(self, fn: PostExecuteFn) -> None:
        self._post_execute_fns.append(fn)

    def add_finalize(self, fn: FinalizeFn) -> None:
        self._finalize_fns.append(fn)

    async def run(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        """走完整管线：pre → guards → execute → post → finalize。"""
        if self._executor is None:
            return ToolExecutionResult(ok=False, error="no executor set")
        return await self._run(ctx, self._executor)

    async def _run(self, ctx: ToolExecutionContext, executor: ExecuteFn) -> ToolExecutionResult:
        """Run the policy stages around one concrete executor."""
        # ── Stage 1: pre-execute ──
        for pre_execute in self._pre_execute_fns:
            pre_decision = await pre_execute(ctx)
            if pre_decision.kind == "deny":
                return ToolExecutionResult(
                    ok=False, error=f"pre-execute denied: {pre_decision.reason}"
                )
            if pre_decision.kind == "ask":
                return ToolExecutionResult(
                    ok=False, error=f"pre-execute ask: {pre_decision.reason}"
                )

        # ── Stage 2: monotonic guards ──
        # 单调性：第一个 deny 赢，不能翻回 allow
        for guard in self._guard_fns:
            reason = guard(ctx)
            if reason is not None:
                return ToolExecutionResult(ok=False, error=f"guard denied: {reason}")

        # ── Stage 3: execute ──
        result = await self._run_execute(ctx, executor)

        # ── Stage 4: post-execute ──
        for post_execute in self._post_execute_fns:
            post_decision = await post_execute(ctx, result)
            if post_decision.kind == "block":
                return ToolExecutionResult(
                    ok=False,
                    error=f"post-execute blocked: {post_decision.content}",
                )
            if post_decision.kind == "accept" and post_decision.content is not None:
                result = ToolExecutionResult(
                    ok=result.ok,
                    output=post_decision.content,
                    error=result.error,
                    latency_ms=result.latency_ms,
                )

        # ── Stage 5: finalize（纯函数，异常隔离）──
        for finalize in self._finalize_fns:
            try:
                result = finalize(result)
            except Exception:
                _log.warning(
                    "tool_pipeline_finalize_failed",
                    tool_name=ctx.tool_name,
                    exc_info=True,
                )

        return result

    async def _run_execute(
        self, ctx: ToolExecutionContext, executor: ExecuteFn
    ) -> ToolExecutionResult:
        """Compose ``tools.execute`` middleware as a conventional onion chain."""
        next_execute: ExecuteNextFn = executor
        for middleware in reversed(self._execute_fns):
            downstream = next_execute

            async def wrapped(
                current_ctx: ToolExecutionContext,
                *,
                _middleware: ExecuteMiddlewareFn = middleware,
                _downstream: ExecuteNextFn = downstream,
            ) -> ToolExecutionResult:
                return await _middleware(current_ctx, _downstream)

            next_execute = wrapped
        return await next_execute(ctx)
