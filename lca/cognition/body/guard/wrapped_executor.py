"""Guarded SafeExecutor — applies ToolGuardService around an inner executor (ADR-0197)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.cognition.body.guard.service import ToolGuardService
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.protocols.act.tool.pipeline import ToolDefinition, ToolExecutionContext
from lca.contracts.protocols.runtime.infra.infra import SafeExecutor, Tool


def guarded_executor_factory(
    inner_factory: Callable[[ToolPermissionManifest], SafeExecutor],
    guards: ToolGuardService,
) -> Callable[[ToolPermissionManifest], SafeExecutor]:
    """Return a SafeExecutor factory that wraps ``inner_factory`` with act guards."""

    def factory(permission_manifest: ToolPermissionManifest) -> SafeExecutor:
        inner = inner_factory(permission_manifest)
        manifest = permission_manifest

        class _Guarded(SafeExecutor):
            permission_manifest = manifest

            async def execute(
                self,
                tool: Tool,
                args: dict[str, Any],
                retry_policy: RetryPolicy,
                cache_config: CacheConfig,
                invocation_id: str = "",
            ) -> Observation:
                ctx = ToolExecutionContext(
                    tool_name=tool.name,
                    args=args,
                    invocation_id=invocation_id,
                    definition=ToolDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                        is_idempotent=tool.is_idempotent,
                        default_timeout_ms=max(1, tool.default_timeout_s) * 1000,
                    ),
                )

                async def run_inner() -> Observation:
                    return await inner.execute(
                        tool,
                        args,
                        retry_policy=retry_policy,
                        cache_config=cache_config,
                        invocation_id=invocation_id,
                    )

                observation = await guards.execute_with_guards(tool, args, run_inner)
                return await guards.apply_post_execute(ctx, observation)

        return _Guarded()

    return factory


__all__ = ["guarded_executor_factory"]
