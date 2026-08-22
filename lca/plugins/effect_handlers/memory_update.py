"""声明式 ``memory.update`` effect handler。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.protocols.command_envelope import CommandEnvelope
from lca.contracts.protocols.declarative_phase_graph import (
    CapabilityDeclaration,
    EvidenceDeclaration,
    LifecycleDeclaration,
    OwnershipDeclaration,
    PluginConfiguration,
    PluginImplementation,
    PluginSpec,
    PluginSpecKind,
    VerificationDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class MemoryUpdateHandlerConfig(BaseModel):
    """memory.update handler 的显式空配置。"""


class MemoryUpdateEffectHandler:
    async def execute(self, envelope: CommandEnvelope, capabilities: Any) -> Any:
        state = envelope.metadata.get("state")
        observation = envelope.metadata.get("observation")
        reflection = envelope.metadata.get("reflection")
        if state is None or observation is None or reflection is None:
            from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

            raise DeclarativeValidationError(
                "RT-002", "memory effect lacks admitted WriteSet inputs"
            )
        await capabilities.memory.update(state, observation, reflection)
        return {
            "receipt": "memory.updated",
            "idempotency_key": envelope.idempotency_key,
            "plan_ref": envelope.plan_ref,
        }


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="effect.handler.memory.update",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="effect-handler",
    implementation=PluginImplementation(
        module="lca.plugins.effect_handlers.memory_update",
        setup="setup",
        factory="create_handler",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.effect_handlers.memory_update.MemoryUpdateHandlerConfig"
    ),
    provides=(
        CapabilityDeclaration(
            key="effect.handler.memory.update",
            cardinality="one",
            protocol="EffectHandler",
            scope="run",
            grant=("memory.update",),
        ),
    ),
    requires=(),
    effects=("memory",),
    ownership=OwnershipDeclaration(reads=("command.envelope",), state_mutation="forbidden"),
    lifecycle=LifecycleDeclaration(scopes=("run",), activation="true", disposal="required"),
    relations=(),
    evidence=EvidenceDeclaration(emits=("EffectReceipt",), replay="required"),
    verification=VerificationDeclaration(
        test_suite="tests/declarative/test_effect_handler_binding.py",
        properties=("capability_bound_dispatch",),
    ),
    contributes=(),
)


@plugin(
    id="effect.handler.memory.update",
    Config=MemoryUpdateHandlerConfig,
    provides=("effect.handler.memory.update",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.MEMORY,
    test_suite="tests/declarative/test_effect_handler_binding.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, _config: MemoryUpdateHandlerConfig) -> None:
    ctx.provide("effect.handler.memory.update", MemoryUpdateEffectHandler())


def create_handler() -> MemoryUpdateEffectHandler:
    return MemoryUpdateEffectHandler()


__all__ = ["SPEC", "MemoryUpdateEffectHandler", "MemoryUpdateHandlerConfig", "create_handler"]
