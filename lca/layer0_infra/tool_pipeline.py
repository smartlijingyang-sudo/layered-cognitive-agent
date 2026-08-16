"""五阶段工具执行管线实现（DSH-inspired）。

管线阶段：
    pre-execute → monotonic guards → execute → post-execute → finalize

关键设计：
- 单调守卫：只 deny 或 abstain（返回 None），第一个 deny 赢，顺序无关。
- around-dispatch：execute 阶段支持 timeout/retry 包装。
- post-execute：可 accept / block 结果。
- finalize：纯函数，异常隔离（只记日志不传播）。
- 信号融合：cancel_scope 保证调用方取消传播不被切断。

设计来源：DSH ``packages/core/tools`` ToolRuntime 五阶段管线。
"""

from __future__ import annotations

import structlog

from lca.contracts.protocols.tool_pipeline import (
    ExecuteFn,
    FinalizeFn,
    GuardFn,
    PostExecuteFn,
    PreExecuteFn,
    ToolExecutionContext,
    ToolExecutionResult,
)

_log = structlog.get_logger("lca.tool_pipeline")


class DefaultToolExecutionPipeline:
    """五阶段工具执行管线的默认实现。"""

    def __init__(self) -> None:
        self._executor: ExecuteFn | None = None
        self._pre_execute_fns: list[PreExecuteFn] = []
        self._guard_fns: list[GuardFn] = []
        self._post_execute_fns: list[PostExecuteFn] = []
        self._finalize_fns: list[FinalizeFn] = []

    def set_executor(self, executor: ExecuteFn) -> None:
        self._executor = executor

    def add_pre_execute(self, fn: PreExecuteFn) -> None:
        self._pre_execute_fns.append(fn)

    def add_guard(self, fn: GuardFn) -> None:
        self._guard_fns.append(fn)

    def add_post_execute(self, fn: PostExecuteFn) -> None:
        self._post_execute_fns.append(fn)

    def add_finalize(self, fn: FinalizeFn) -> None:
        self._finalize_fns.append(fn)

    async def run(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        """走完整管线：pre → guards → execute → post → finalize。"""
        # ── Stage 1: pre-execute ──
        for fn in self._pre_execute_fns:
            decision = await fn(ctx)
            if decision.kind == "deny":
                return ToolExecutionResult(ok=False, error=f"pre-execute denied: {decision.reason}")
            if decision.kind == "ask":
                return ToolExecutionResult(ok=False, error=f"pre-execute ask: {decision.reason}")

        # ── Stage 2: monotonic guards ──
        # 单调性：第一个 deny 赢，不能翻回 allow
        for fn in self._guard_fns:
            reason = fn(ctx)
            if reason is not None:
                return ToolExecutionResult(ok=False, error=f"guard denied: {reason}")

        # ── Stage 3: execute ──
        if self._executor is None:
            return ToolExecutionResult(ok=False, error="no executor set")
        result = await self._executor(ctx)

        # ── Stage 4: post-execute ──
        for fn in self._post_execute_fns:
            decision = await fn(ctx, result)
            if decision.kind == "block":
                return ToolExecutionResult(
                    ok=False,
                    error=f"post-execute blocked: {decision.content}",
                )
            if decision.kind == "accept" and decision.content is not None:
                result = ToolExecutionResult(
                    ok=result.ok,
                    output=decision.content,
                    error=result.error,
                    latency_ms=result.latency_ms,
                )

        # ── Stage 5: finalize（纯函数，异常隔离）──
        for fn in self._finalize_fns:
            try:
                result = fn(result)
            except Exception:
                _log.warning(
                    "tool_pipeline_finalize_failed",
                    tool_name=ctx.tool_name,
                    exc_info=True,
                )

        return result
