"""Tool pipeline composition: definition, provider, policy, and renderer."""

from __future__ import annotations

from typing import ClassVar

import pytest

from lca.contracts.atoms.enums import ContentType
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.protocols.tool_pipeline import (
    ExecuteNextFn,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolPostDecision,
    ToolPreDecision,
)
from lca.layer0_infra.tool_pipeline import DefaultToolExecutionPipeline
from lca.layer1_cognitive.body.pipeline_safe_executor import PipelineSafeExecutor


class _EchoProvider:
    provider_id = "echo-v1"

    async def execute(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(ok=True, output=ctx.args["message"])


class _UppercaseProvider:
    provider_id = "echo-v2"

    async def execute(self, ctx: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(ok=True, output=ctx.args["message"].upper())


class _ModelRenderer:
    def render(self, definition: ToolDefinition) -> dict[str, object]:
        return {
            "name": definition.name,
            "description": definition.description,
            "parameters": definition.parameters,
        }


class _LegacyEchoTool:
    name = "legacy_echo"
    description = "Echo through the legacy SafeExecutor interface."
    parameters: ClassVar[dict[str, object]] = {"type": "object"}
    is_idempotent = True
    default_timeout_s = 30

    async def execute(self, args: dict[str, object]) -> Observation:
        return Observation(
            observation_id="obs-1",
            success=True,
            payload=args["message"],
            content_type=ContentType.TEXT,
        )

    def validate(self, args: dict[str, object]) -> str | None:
        return None if isinstance(args.get("message"), str) else "message is required"


@pytest.mark.asyncio
async def test_definition_provider_pipeline_and_renderer_are_independently_pluggable() -> None:
    pipeline = DefaultToolExecutionPipeline()
    definition = ToolDefinition(
        name="echo",
        description="Return the supplied message.",
        parameters={"type": "object", "required": ["message"]},
        result_schema={"type": "string"},
        version="1.0.0",
    )
    pipeline.register_tool(definition, _EchoProvider())
    pipeline.set_renderer(_ModelRenderer())

    assert pipeline.render("echo") == {
        "name": "echo",
        "description": "Return the supplied message.",
        "parameters": {"type": "object", "required": ["message"]},
    }

    first = await pipeline.execute("echo", {"message": "hello"})
    assert first.ok is True
    assert first.output == "hello"

    pipeline.register_provider("echo", _UppercaseProvider())
    second = await pipeline.execute("echo", {"message": "hello"})
    assert second.ok is True
    assert second.output == "HELLO"


@pytest.mark.asyncio
async def test_policy_and_extension_hooks_wrap_a_provider_execution() -> None:
    pipeline = DefaultToolExecutionPipeline()
    pipeline.register_tool(
        ToolDefinition(name="echo", description="Echo", parameters={}),
        _EchoProvider(),
    )
    calls: list[str] = []

    async def approval(ctx: ToolExecutionContext) -> ToolPreDecision:
        calls.append("approval")
        return ToolPreDecision(kind="allow")

    def sandbox(ctx: ToolExecutionContext) -> str | None:
        calls.append("sandbox")
        return None

    async def around(ctx: ToolExecutionContext, next_execute: ExecuteNextFn) -> ToolExecutionResult:
        calls.append("before-execute")
        result = await next_execute(ctx)
        calls.append("after-execute")
        return result

    async def post(ctx: ToolExecutionContext, result: ToolExecutionResult) -> ToolPostDecision:
        calls.append("post-execute")
        return ToolPostDecision(kind="accept", content=f"rendered:{result.output}")

    pipeline.add_approval_policy(approval)
    pipeline.add_sandbox_guard(sandbox)
    pipeline.add_execute(around)
    pipeline.add_post_execute(post)

    result = await pipeline.execute("echo", {"message": "hello"})

    assert result.ok is True
    assert result.output == "rendered:hello"
    assert calls == [
        "approval",
        "sandbox",
        "before-execute",
        "after-execute",
        "post-execute",
    ]


@pytest.mark.asyncio
async def test_denied_policy_prevents_provider_execution() -> None:
    pipeline = DefaultToolExecutionPipeline()
    pipeline.register_tool(
        ToolDefinition(name="echo", description="Echo", parameters={}),
        _EchoProvider(),
    )

    async def deny(ctx: ToolExecutionContext) -> ToolPreDecision:
        return ToolPreDecision(kind="deny", reason="approval required")

    pipeline.add_approval_policy(deny)

    result = await pipeline.execute("echo", {"message": "hello"})

    assert result.ok is False
    assert result.error == "pre-execute denied: approval required"


@pytest.mark.asyncio
async def test_legacy_safe_executor_uses_provider_pipeline_contract() -> None:
    # PR-7: mint_envelope requires plan_ref (V5 acceptance). Tests must wrap
    # the call in plan_ref_scope to inject a non-empty plan_ref.
    from lca.contracts.models.observability.plan_ref import plan_ref_scope

    executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=["legacy_echo"]))

    with plan_ref_scope("test_plan_ref_for_pipeline_test"):
        result = await executor.execute(
            _LegacyEchoTool(),
            {"message": "hello"},
            RetryPolicy(max_retries=0),
            CacheConfig(enabled=False),
        )

    assert result.success is True
    assert result.payload == "hello"
    assert result.extra["policy_verdict_refs"] == [
        "executor.permission:allow",
        "executor.reservation:valid",
        "executor.grant:valid",
        "executor.plan-boundary:valid",
        "executor.pipeline:completed",
    ]
    envelope = result.extra["command_envelope"]
    assert envelope["plan_ref"] == "test_plan_ref_for_pipeline_test"
    assert envelope["provider"] == "legacy-safe-executor"
    assert envelope["metadata"]["tool_name"] == "legacy_echo"


@pytest.mark.asyncio
async def test_legacy_safe_executor_requires_active_compiled_plan_ref() -> None:
    from lca.contracts.models.core.result import ToolExecutionError

    executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=["legacy_echo"]))

    with pytest.raises(ToolExecutionError, match="active compiled plan_ref"):
        await executor.execute(
            _LegacyEchoTool(),
            {"message": "must be plan bound"},
            RetryPolicy(max_retries=0),
            CacheConfig(enabled=False),
        )


@pytest.mark.asyncio
async def test_legacy_safe_executor_denies_before_provider_execution() -> None:
    from lca.contracts.models.core.result import ToolExecutionError
    from lca.contracts.models.observability.plan_ref import plan_ref_scope

    executor = PipelineSafeExecutor(ToolPermissionManifest(allowed_tools=[]))

    with (
        plan_ref_scope("denied_plan_ref"),
        pytest.raises(ToolExecutionError, match="未在 ToolPermissionManifest"),
    ):
        await executor.execute(
            _LegacyEchoTool(),
            {"message": "must not execute"},
            RetryPolicy(max_retries=0),
            CacheConfig(enabled=False),
        )
