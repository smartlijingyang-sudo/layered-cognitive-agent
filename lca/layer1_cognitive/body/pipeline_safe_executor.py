"""Pipeline-based SafeExecutor — DSH-inspired 五阶段管线集成。

将 SafeExecutor 的执行流程重构为五阶段管线：
1. pre-execute: 权限检查、参数校验
2. guards: 单调守卫（如预算检查、频率限制）
3. execute: 实际工具执行（含重试逻辑）
4. post-execute: 结果处理、缓存更新
5. finalize: 纯函数变换（如日志脱敏）

这个实现展示了如何将 DSH 的 Tool Pipeline 模式集成到 LCA 的架构中，
同时保持原有的功能（权限、校验、重试、缓存、Journal 记录）。

关键设计决策：
- 保留原有的所有功能，只是重构为管线模式
- 每个阶段都是可插拔的，可以通过 add_pre_execute / add_guard 等方法扩展
- 单调守卫确保安全性（如预算检查不能被子sequent 阶段覆盖）
- Journal 记录作为 post-execute 阶段的一部分，确保每次执行都被记录
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

import structlog

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.result import ApprovalPendingError, ToolExecutionError
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.protocols import SafeExecutor, Tool
from lca.contracts.protocols.tool_pipeline import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolPreDecision,
    ToolProvider,
)
from lca.layer0_infra.tool_pipeline import DefaultToolExecutionPipeline
from lca.layer0_infra.tools.tool_invocation_scope import tool_invocation_scope
from lca.layer1_cognitive.body.tool_result_preview import (
    build_started_plugin_state,
    compact_args_preview,
    compact_payload_for_preview,
)

_log = structlog.get_logger("lca.safe_executor")

_PERF_COUNTER_SCALE = 1000

# Deterministic exceptions — retrying with the same args will never succeed.
_DETERMINISTIC_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    SyntaxError,
    IndexError,
    NameError,
    NotImplementedError,
    OverflowError,
    ZeroDivisionError,
)


def _tool_output_preview(obs: Observation) -> str:
    """工具结果预览（成功取紧凑 payload，失败取错误）。"""
    if obs.success:
        return json.dumps(
            compact_payload_for_preview(obs.payload),
            ensure_ascii=False,
            default=str,
        )
    return obs.error or ""


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)


class PipelineSafeExecutor(SafeExecutor):
    """基于五阶段管线的 SafeExecutor 实现。

    管线阶段：
    1. pre-execute: 权限检查、参数校验、Journal ToolStarted
    2. guards: 单调守卫（可扩展，如预算检查）
    3. execute: 实际执行（含重试、缓存）
    4. post-execute: 结果处理、Journal ToolInvoked、缓存更新
    5. finalize: 纯函数变换（当前为空操作）

    这个实现保持了与 SimpleSafeExecutor 相同的功能，但通过管线模式
    使得每个阶段都可以独立扩展和测试。
    """

    def __init__(self, permission_manifest: ToolPermissionManifest):
        self.permission_manifest = permission_manifest
        self._cache: dict[str, Observation] = {}

    def _pipeline_for(
        self, tool: Tool, retry_policy: RetryPolicy, cache_config: CacheConfig
    ) -> DefaultToolExecutionPipeline:
        """Bind one legacy Tool to the provider-based pipeline for this invocation.

        The legacy executor receives a concrete ``Tool`` at call time, while the
        new pipeline owns stable declarations and providers.  A fresh pipeline
        prevents concurrent calls of the same legacy tool from replacing each
        other's provider binding.
        """
        pipeline = DefaultToolExecutionPipeline()
        pipeline.register_tool(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                is_idempotent=tool.is_idempotent,
                default_timeout_ms=tool.default_timeout_s * 1000,
            ),
            _LegacyToolProvider(self, tool, retry_policy, cache_config),
        )
        pipeline.add_pre_execute(self._pre_execute_check(tool))
        return pipeline

    def _pre_execute_check(self, tool: Tool) -> Callable[[ToolExecutionContext], Awaitable[ToolPreDecision]]:
        async def check(ctx: ToolExecutionContext) -> ToolPreDecision:
            return self._check_permission_and_args(tool, ctx.args)

        return check

    def _check_permission_and_args(self, tool: Tool, args: dict[str, Any]) -> ToolPreDecision:
        """Stage 1: 权限检查和参数校验。"""
        from lca.layer1_cognitive.body.safe_executor import emit_tool_denied

        if tool.name not in self.permission_manifest.allowed_tools:
            emit_tool_denied(tool, "permission")
            return ToolPreDecision(
                kind="deny",
                reason=f"工具 {tool.name} 未在 ToolPermissionManifest.allowed_tools 中授权",
            )

        # 参数校验
        validation_error = self._validate_args(tool, args)
        if validation_error is not None:
            emit_tool_denied(tool, "validation")
            return ToolPreDecision(kind="deny", reason=validation_error)

        return ToolPreDecision(kind="allow")

    async def _execute_with_retry(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str,
    ) -> ToolExecutionResult:
        """Stage 3: 实际执行（含重试、缓存）。

        Note: ``ToolStarted`` is emitted by ``SimpleSafeExecutor`` (the
        canonical emitter per spec §9.1).  The pipeline executor reuses
        that emitter by routing through ``_LegacyToolProvider`` —
        duplicating the emit here would violate the single-emission
        boundary guard.
        """
        args_preview = compact_args_preview(args)
        started_state = build_started_plugin_state(tool.name, args)

        with tool_invocation_scope(invocation_id):
            # 缓存检查
            cache_key = f"{tool.name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            if cache_config.enabled and cache_key in self._cache:
                cached = self._cache[cache_key]
                # Journal: ToolInvoked（缓存命中）
                self._record_invoked(
                    tool,
                    args,
                    args_preview,
                    cached,
                    latency_ms=0,
                    attempt=0,
                    invocation_id=invocation_id,
                )
                return ToolExecutionResult(ok=True, output=cached)

            # 重试循环
            started = time.perf_counter()
            last_obs: Observation | None = None
            last_error: str = ""
            attempts_used = 0
            delay = retry_policy.backoff_base_s

            for attempt in range(retry_policy.max_retries + 1):
                attempts_used = attempt + 1
                obs = await self._execute_once(tool, args, attempt)

                if obs.success:
                    # 缓存更新
                    if cache_config.enabled:
                        self._cache[cache_key] = obs

                    # Journal: ToolInvoked（成功）
                    self._record_invoked(
                        tool,
                        args,
                        args_preview,
                        obs,
                        latency_ms=_elapsed_ms(started),
                        attempt=attempts_used,
                        invocation_id=invocation_id,
                    )
                    return ToolExecutionResult(ok=True, output=obs)

                failure_kind = obs.extra.get(FAILURE_KIND)
                # Only transient errors are retried
                if failure_kind != FAILURE_KIND_TRANSIENT:
                    # Journal: ToolInvoked（确定性失败）
                    self._record_invoked(
                        tool,
                        args,
                        args_preview,
                        obs,
                        latency_ms=_elapsed_ms(started),
                        attempt=attempts_used,
                        invocation_id=invocation_id,
                    )
                    return ToolExecutionResult(ok=False, output=obs, error=obs.error or "")

                last_obs = obs
                last_error = obs.error or ""
                if attempt < retry_policy.max_retries:
                    await asyncio.sleep(delay)
                    delay *= retry_policy.backoff_multiplier

            # 重试耗尽
            if last_obs is not None:
                self._record_invoked(
                    tool,
                    args,
                    args_preview,
                    last_obs,
                    latency_ms=_elapsed_ms(started),
                    attempt=attempts_used,
                    invocation_id=invocation_id,
                )

            detail = f"，最后错误: {last_error}" if last_error else ""
            raise ToolExecutionError(
                f"工具 {tool.name} 重试 {retry_policy.max_retries} 次后仍失败{detail}",
                last_obs,
            )

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str = "",
    ) -> Observation:
        """执行工具调用（通过管线）。"""
        invocation_id = invocation_id.strip() or new_id("inv")

        result = await self._pipeline_for(tool, retry_policy, cache_config).execute(
            tool.name, args, invocation_id=invocation_id
        )

        # 如果管线返回 deny，抛出异常
        if (
            not result.ok
            and result.error
            and ("未在 ToolPermissionManifest" in result.error or "validation" in result.error)
        ):
            raise ToolExecutionError(result.error)

        # 返回 Observation
        if result.ok and result.output:
            return cast("Observation", result.output)
        else:
            # 构造失败的 Observation
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=result.error or "Unknown error",
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )

    async def _execute_once(self, tool: Tool, args: dict[str, Any], attempt: int) -> Observation:
        """单次执行（不含重试）。"""
        try:
            return await tool.execute(args)
        except ApprovalPendingError:
            # Control-flow signal (HIL pause) — must propagate
            raise
        except ToolExecutionError as err:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
            )
        except Exception as err:
            _log.warning(
                "tool_execution_error",
                tool=tool.name,
                error_type=type(err).__name__,
                error=str(err),
                attempt=attempt,
            )
            failure_kind = (
                FAILURE_KIND_EXECUTION
                if isinstance(err, _DETERMINISTIC_EXCEPTIONS)
                else FAILURE_KIND_TRANSIENT
            )
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(err),
                extra={FAILURE_KIND: failure_kind},
            )

    @staticmethod
    def _validate_args(tool: Tool, args: dict[str, Any]) -> str | None:
        """参数校验。"""
        validator: Any = getattr(tool, "validate", None)
        if validator is None:
            return None
        result: str | None = validator(args)
        return result

    @staticmethod
    def _record_invoked(
        tool: Tool,
        args: dict[str, Any],
        args_preview: str,
        obs: Observation,
        *,
        latency_ms: int,
        attempt: int,
        invocation_id: str,
    ) -> None:
        """Journal: ToolInvoked。

        Per spec §9.1 the canonical emitter is ``safe_executor``; this
        delegate routes through it so the boundary guard sees one
        emission site per event.
        """
        from lca.layer1_cognitive.body.safe_executor import emit_tool_invoked

        emit_tool_invoked(
            tool,
            args,
            args_preview,
            obs,
            latency_ms=latency_ms,
            attempt=attempt,
            invocation_id=invocation_id,
        )


class _LegacyToolProvider(ToolProvider):
    """Adapts the legacy Tool/SafeExecutor call shape to ToolProvider."""

    provider_id = "legacy-safe-executor"

    def __init__(
        self,
        executor: PipelineSafeExecutor,
        tool: Tool,
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
    ) -> None:
        self._executor = executor
        self._tool = tool
        self._retry_policy = retry_policy
        self._cache_config = cache_config

    async def execute(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        return await self._executor._execute_with_retry(
            self._tool,
            ctx.args,
            self._retry_policy,
            self._cache_config,
            ctx.invocation_id,
        )
