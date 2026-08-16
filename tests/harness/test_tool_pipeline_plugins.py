"""Tool pipeline composition: definition, provider, policy, and renderer."""

from __future__ import annotations

import pytest

from lca.contracts.protocols.tool_pipeline import (
    ExecuteNextFn,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolPostDecision,
    ToolPreDecision,
)
from lca.layer0_infra.tool_pipeline import DefaultToolExecutionPipeline


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
