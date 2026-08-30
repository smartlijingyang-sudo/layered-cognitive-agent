"""EffectHandler Provider plugin — Tier-2 (ADR-0074).

The registry is a neutral container.  The provider plugin is the sole place
that installs the standard ``body.act`` and ``memory.update`` implementations,
so a profile can replace or omit them without a seam definition silently
reintroducing behavior.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.declarative_phase_graph import (
    CommandEnvelope,
    EffectPolicyPlan,
)
from lca.contracts.protocols.effect_handler import (
    EffectCapabilities,
    EffectHandler,
    EffectHandlerRegistry,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.handler_registry import UniqueOperationRegistry


class Config(BaseModel):
    """EffectHandler provider configuration (reserved for future options)."""

    model_config = {"extra": "forbid"}


class BodyActEffectHandler(EffectHandler):
    """Handle the plan-declared ``body.act`` effect operation.

    The handler extracts state and decision from the immutable command envelope
    and delegates world execution to the Body capability.  It does not mutate
    ``AgentState``; a subsequent delta handler remains the only state writer.
    """

    receipt_name = "body.acted"

    async def handle(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        capabilities: EffectCapabilities,
    ) -> Observation:
        """Execute the Body operation described by an authorized envelope."""
        del policy
        metadata = envelope.metadata
        state: AgentState = metadata["state"]
        decision: Decision = metadata["decision"]
        return await capabilities.body.act(decision, state)


class MemoryUpdateEffectHandler(EffectHandler):
    """Handle the plan-declared ``memory.update`` effect operation."""

    receipt_name = "memory.updated"

    async def handle(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        capabilities: EffectCapabilities,
    ) -> dict[str, Any]:
        """Commit memory without directly mutating ``AgentState``."""
        del policy
        metadata = envelope.metadata
        state: AgentState = metadata["state"]
        observation: Observation = metadata["observation"]
        reflection: Reflection = metadata["reflection"]
        await capabilities.memory.update(state, observation, reflection)
        return {"admitted": True}


class InMemoryEffectHandlerRegistry(UniqueOperationRegistry[EffectHandler], EffectHandlerRegistry):
    """效果处理器接缝的空容器。

    接缝定义只提供容器，明确启用的 Provider 才能注册 handler。同一 operation
    的第二个所有者会在此失败，避免装配顺序重新定义运行时行为。
    """

    def __init__(self) -> None:
        super().__init__("effect handler")

    def register(self, operation: str, handler: EffectHandler) -> None:
        """注册一个 effect operation 的唯一 handler 所有者。"""
        self._register(operation, handler)

    def resolve(self, operation: str) -> EffectHandler | None:
        """解析 effect operation 对应的 handler。"""
        return self._resolve(operation)

    def registered_effect_operations(self) -> tuple[str, ...]:
        """返回稳定的已注册 effect operation 快照。"""
        return self._registered_operations()


def register_default_effect_handlers(registry: EffectHandlerRegistry) -> None:
    """Install the standard handlers through the same provider-owned seam.

    Production activation calls this function from :func:`setup`.  Dedicated
    fixture adapters may call it explicitly, which keeps their conveniences
    visible without making them reachable from a production seam definition.
    """

    registry.register("body.act", BodyActEffectHandler())
    registry.register("memory.update", MemoryUpdateEffectHandler())


@plugin(
    id="lca-effect-handler-provider",
    requires=["effect_handler_registry"],
    implements=[EffectHandlerRegistry],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description="Register the standard body and memory EffectHandler implementations.",
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Install the provider-owned standard handlers into the declared seam."""
    del config
    registry: EffectHandlerRegistry = ctx.require("effect_handler_registry")
    register_default_effect_handlers(registry)


__all__ = [
    "BodyActEffectHandler",
    "InMemoryEffectHandlerRegistry",
    "MemoryUpdateEffectHandler",
    "register_default_effect_handlers",
    "setup",
]
