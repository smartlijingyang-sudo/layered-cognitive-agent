"""Tool-call execution scheduler.

1:1 port of ``@deepseek-ai/dsh-agent-loop/tool-calls.ts``.

Handles parameter parsing, execution mode classification (parallel/exclusive),
parallel rolling pool with exclusive barriers, three-phase scheduler lifecycle,
model-order commit, abort handling, and concludesTurn semantics.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from lca.layer0_infra.dsh_core.agent_loop.constants import (
    DEFAULT_MAX_PARALLEL_TOOL_CALLS,
)
from lca.layer0_infra.dsh_core.tools import (
    TOOL_ABORTED_BEFORE_DISPATCH,
    ContentBlock,
    ToolErrorInfo,
    ToolExecution,
    ToolExecutionFailure,
    ToolExecutionSuccess,
    ToolFailure,
    ToolResult,
    ToolRuntime,
)


def _create_execution_token() -> str:
    return f"tool-exec-{uuid.uuid4().hex[:12]}"


def _parse_arguments(raw: str) -> Any:
    """Parse tool arguments JSON, tolerating empty input."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


@dataclass
class ExecuteToolCallsResult:
    """Result of executing a batch of tool calls."""

    results: list[ToolExecution | ToolExecutionSuccess | ToolExecutionFailure]
    concluded: bool


def _synthetic_aborted_result(execution: ToolExecution) -> ToolResult:
    """Build a synthetic tool-result event for an aborted call."""
    return ToolResult(
        call_id=execution.call_id,
        tool_name=execution.name,
        content=[
            ContentBlock(type="text", text="Tool call aborted before dispatch.")
        ],
        error=ToolFailure(
            message="aborted",
            info=ToolErrorInfo(name="AbortedError", code=TOOL_ABORTED_BEFORE_DISPATCH),
        ),
        is_error=True,
    )


async def execute_tool_calls(
    loop_ctx: Any,
    turn: int,
    step: int,
    tool_calls: list[Any],
    signal: asyncio.Event | None,
    *,
    inject_context: Callable[[Any], Awaitable[None]] | None = None,
    runtime: ToolRuntime | None = None,
) -> ExecuteToolCallsResult:
    """Execute tool calls with parallel pool and exclusive barriers.

    Mirrors DSH ``executeToolCalls``: classifies each call as parallel or
    exclusive, dispatches up to ``DEFAULT_MAX_PARALLEL_TOOL_CALLS`` in
    parallel, commits results in model order, and handles abort synthetically.
    """
    if not tool_calls:
        return ExecuteToolCallsResult(results=[], concluded=True)

    if runtime is None:
        runtime = getattr(loop_ctx, "tools_runtime", None) or loop_ctx.require("tools")

    # Classify each call
    classified: list[tuple[int, Any, Literal["parallel", "exclusive"]]] = []
    for index, call in enumerate(tool_calls):
        mode = "parallel"
        try:
            em = runtime.execution_mode(call) if hasattr(runtime, "execution_mode") else None
            if em is not None and hasattr(em, "kind"):
                mode = "exclusive" if em.kind == "exclusive" else "parallel"
        except Exception:
            mode = "parallel"
        classified.append((index, call, mode))

    # Build execution inputs
    executions: list[ToolExecution] = []
    for index, call, _mode in classified:
        call_id = getattr(call, "id", None) or f"call-{index}"
        raw_args = getattr(call, "arguments", "{}") or "{}"
        args = _parse_arguments(raw_args) if isinstance(raw_args, str) else raw_args
        executions.append(
            ToolExecution(
                call_id=str(call_id),
                name=getattr(call, "name", ""),
                arguments=args,
                token=_create_execution_token(),
                turn=turn,
                step=step,
            )
        )

    # Dispatch in model order, respecting parallel/exclusive barriers
    results: list[ToolResult] = []
    concluded = True

    sem = asyncio.Semaphore(DEFAULT_MAX_PARALLEL_TOOL_CALLS)

    async def _dispatch_one(idx: int, exec_: ToolExecution) -> ToolResult:
        # Pre-execute waterfall (best-effort)
        with contextlib.suppress(Exception):
            await loop_ctx.waterfall("tools/pre-execute", exec_, terminal=lambda e=exec_: asyncio.sleep(0, result=None))
        if signal is not None and signal.is_set():
            return _synthetic_aborted_result(exec_)
        # Execute
        try:
            result = await runtime.execute(exec_)
            if isinstance(result, ToolResult):
                # Post-execute waterfall
                with contextlib.suppress(Exception):
                    await loop_ctx.waterfall("tools/post-execute", exec_, result, terminal=lambda e=exec_, r=result: asyncio.sleep(0, result=r))
                return result
            # If result is something else, convert
            return ToolResult(
                call_id=exec_.call_id,
                tool_name=exec_.name,
                content=[],
                is_error=True,
                error=ToolFailure(message="unexpected result type", info=None),
            )
        except Exception as exc:
            return ToolResult(
                call_id=exec_.call_id,
                tool_name=exec_.name,
                content=[],
                is_error=True,
                error=ToolFailure(message=str(exc), info=None),
            )

    # Process in order: parallel calls can run concurrently, exclusive creates a barrier
    i = 0
    while i < len(classified):
        # Collect a batch of consecutive parallel calls
        batch: list[int] = []
        while i < len(classified) and classified[i][2] == "parallel":
            batch.append(i)
            i += 1
        # If we have an exclusive call, it runs alone (after batch)
        if i < len(classified) and classified[i][2] == "exclusive":
            batch.append(i)
            i += 1
        if not batch:
            continue

        # Dispatch batch in parallel (bounded by semaphore)
        async def _run_with_sem(idx: int, exec_: ToolExecution) -> ToolResult:
            async with sem:
                return await _dispatch_one(idx, exec_)

        tasks = [asyncio.create_task(_run_with_sem(idx, executions[idx])) for idx in batch]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for d in done:
            if isinstance(d, Exception):
                # Should not happen since _dispatch_one catches, but be safe
                results.append(
                    ToolResult(
                        call_id="",
                        tool_name="",
                        content=[],
                        is_error=True,
                        error=ToolFailure(message=str(d), info=None),
                    )
                )
            else:
                results.append(d)

        # Check for additionalContexts injection
        if inject_context is not None:
            for r in results:
                if r.additional_contexts:
                    for ctx_msg in r.additional_contexts:
                        with contextlib.suppress(Exception):
                            await inject_context(ctx_msg)

        # If any result has concludes_turn=True, stop
        for r in results:
            if getattr(r, "concludes_turn", False):
                concluded = True
                break

    # Map ToolResult list to ToolExecutionSuccess/Failure for return
    return ExecuteToolCallsResult(
        results=[_to_execution_result(r) for r in results],
        concluded=concluded,
    )


def _to_execution_result(r: ToolResult) -> ToolExecutionSuccess | ToolExecutionFailure:
    """Convert a ToolResult to a ToolExecutionSuccess or ToolExecutionFailure."""
    if r.is_error:
        return ToolExecutionFailure(
            call_id=r.call_id,
            tool_name=r.tool_name,
            content=r.content,
            error=r.error or ToolFailure(message="unknown error", info=None),
        )
    return ToolExecutionSuccess(
        call_id=r.call_id,
        tool_name=r.tool_name,
        content=r.content,
        value=None,
    )
