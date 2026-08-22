"""声明式 ``body.act`` effect handler。"""

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


class BodyActHandlerConfig(BaseModel):
    """body.act handler 的显式空配置。"""


class BodyActEffectHandler:
    async def execute(self, envelope: CommandEnvelope, capabilities: Any) -> Any:
        state = envelope.metadata.get("state")
        decision = envelope.metadata.get("decision")
        if state is None or decision is None:
            from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError

            raise DeclarativeValidationError(
                "RT-002", "body effect lacks state or recorded Decision"
            )
        return await capabilities.body.act(decision, state)


SPEC = PluginSpec(
    api_version="lca/plugin-spec/v1",
    id="effect.handler.body.act",
    revision="1.0.0",
    kind=PluginSpecKind.PROVIDER,
    layer="L2",
    functional_group="effect-handler",
    implementation=PluginImplementation(
        module="lca.plugins.effect_handlers.body_act",
        setup="setup",
        factory="create_handler",
    ),
    configuration=PluginConfiguration(
        schema="lca.plugins.effect_handlers.body_act.BodyActHandlerConfig"
    ),
    provides=(
        CapabilityDeclaration(
            key="effect.handler.body.act",
            cardinality="one",
            protocol="EffectHandler",
            scope="run",
            grant=("body.act",),
        ),
    ),
    requires=(),
    effects=("tools",),
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
    id="effect.handler.body.act",
    Config=BodyActHandlerConfig,
    provides=("effect.handler.body.act",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.TOOLS,
    test_suite="tests/declarative/test_effect_handler_binding.py",
    spec=SPEC,
)
async def setup(ctx: PluginContext, _config: BodyActHandlerConfig) -> None:
    ctx.provide("effect.handler.body.act", BodyActEffectHandler())


def create_handler() -> BodyActEffectHandler:
    return BodyActEffectHandler()


__all__ = ["SPEC", "BodyActEffectHandler", "BodyActHandlerConfig", "create_handler"]
