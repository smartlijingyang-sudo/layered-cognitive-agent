"""Architecture contracts for ActionHandler / EffectHandler / DeltaHandler seams.

Handler registries expose a single, explicit owner for each operation. Profile
composition chooses which Provider contributes that owner; a later registration
must fail instead of silently redefining runtime behavior. These tests also
ensure the core execution path discovers handlers only through injected seams.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from lca.contracts.protocols.action_handler import ActionHandlerRegistry
from lca.contracts.protocols.command_envelope import CapabilityGrant, CommandEnvelope
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeValidationError,
    EffectPolicyPlan,
)
from lca.contracts.protocols.delta_handler import DeltaHandler, DeltaHandlerRegistry
from lca.contracts.protocols.effect_handler import EffectHandler, EffectHandlerRegistry
from lca.harness.declarative.dispatch import RegistryEffectGateway
from lca.cognition.body.tool_batch_execution import SafeToolBatchExecutionPolicy
from lca.runtime.declarative_runtime import RuntimePhaseCapabilities
from lca.runtime.idempotency_fixtures import InMemoryFixtureIdempotencyStore
from lca.plugins.providers.action_handlers import (
    DefaultActionHandlerRegistry,
    InMemoryActionHandlerRegistry,
    register_default_action_handlers,
)
from lca.plugins.providers.delta_handlers import (
    DefaultDeltaHandlerRegistry,
    InMemoryDeltaHandlerRegistry,
    register_default_delta_handlers,
)
from lca.plugins.providers.effect_handlers import (
    InMemoryEffectHandlerRegistry,
)

REPO = Path(__file__).resolve().parents[2]

# Forbidden direct constructions in the runtime gateway and other core paths.
FORBIDDEN_HANDLER_TYPES: frozenset[str] = frozenset(
    {
        "BodyActEffectHandler",
        "MemoryUpdateEffectHandler",
        "InMemoryEffectHandlerRegistry",
        "DefaultDeltaHandlerRegistry",
        "InMemoryDeltaHandlerRegistry",
        "DefaultActionHandlerRegistry",
    }
)


# ── ActionHandler substitutability ────────────────────────────────────


def test_action_handler_registry_rejects_duplicate_owner_and_keeps_first() -> None:
    """ActionType 所有权在接缝处唯一，不能由后续 Provider 静默覆盖。"""

    class _FirstHandler:
        def create(self, tool_registry, safe_executor, transport_registry):
            return None

    class _ReplacementHandler:
        def create(self, tool_registry, safe_executor, transport_registry):
            return None

    registry = InMemoryActionHandlerRegistry()
    first = _FirstHandler()
    registry.register("use_tool", first)

    with pytest.raises(KeyError, match="action handler: operation 'use_tool' already registered"):
        registry.register("use_tool", _ReplacementHandler())

    assert registry.resolve("use_tool") is first


def test_action_handler_seam_is_neutral_until_provider_installs_defaults() -> None:
    """The seam must not silently own the provider's default behavior."""

    seam_registry = InMemoryActionHandlerRegistry()
    assert seam_registry.registered() == ()

    register_default_action_handlers(
        seam_registry,
        batch_execution_policy=SafeToolBatchExecutionPolicy(),
    )
    assert seam_registry.registered() == DefaultActionHandlerRegistry().registered()


def test_action_handler_registry_registered_lists_all_keys() -> None:
    """The ``registered`` snapshot must cover every key inserted."""

    registry = DefaultActionHandlerRegistry()
    keys = registry.registered()
    assert "respond" in keys
    assert "use_tool" in keys
    assert "delegate" in keys
    assert "handoff" in keys


def test_action_handler_registry_protocol_exposes_registered() -> None:
    """The :class:`ActionHandlerRegistry` Protocol must declare ``registered`` (ADR-0076 §五)."""

    assert hasattr(ActionHandlerRegistry, "registered")


# ── EffectHandler substitutability ────────────────────────────────────


def test_effect_handler_registry_rejects_duplicate_owner_and_keeps_first() -> None:
    """Effect operation 所有权在接缝处唯一，避免注册顺序改变执行行为。"""

    class _FirstHandler:
        async def handle(self, envelope, policy, capabilities):
            return None

    class _ReplacementHandler:
        async def handle(self, envelope, policy, capabilities):
            return None

    registry: EffectHandlerRegistry = InMemoryEffectHandlerRegistry()
    first = _FirstHandler()
    registry.register("body.act", first)

    with pytest.raises(KeyError, match=r"effect handler: operation 'body\.act' already registered"):
        registry.register("body.act", _ReplacementHandler())

    assert registry.resolve("body.act") is first
    assert registry.registered_effect_operations() == ("body.act",)


@pytest.mark.asyncio
async def test_replacement_handler_owns_receipt_label() -> None:
    """A replacement operation carries its receipt semantics through the seam."""

    class _CustomHandler:
        receipt_name = "custom.effect.completed"

        async def handle(self, envelope, policy, capabilities):
            del envelope, policy, capabilities
            return {"accepted": True}

    registry: EffectHandlerRegistry = InMemoryEffectHandlerRegistry()
    registry.register("custom.effect", _CustomHandler())
    gateway = RegistryEffectGateway(
        RuntimePhaseCapabilities({}),
        registry,
        InMemoryFixtureIdempotencyStore(),
    )
    envelope = CommandEnvelope(
        plan_ref="plan-custom",
        decision_ref="decision-custom",
        provider="custom-provider",
        grant=CapabilityGrant(capability="custom.effect", scope="run", effect_class="tools"),
        idempotency_key="custom-key",
        metadata={"operation": "custom.effect"},
    )

    result = await gateway.execute(
        envelope,
        EffectPolicyPlan(allowed_effects=("tools",), idempotency_required=("tools",)),
    )

    assert result["receipt"] == "custom.effect.completed"
    assert result["operation"] == "custom.effect"


def test_effect_handler_protocol_exposes_handle() -> None:
    """The :class:`EffectHandler` Protocol must declare ``handle``."""

    assert hasattr(EffectHandler, "handle")


# ── DeltaHandler substitutability ──────────────────────────────────────


def test_delta_handler_registry_rejects_duplicate_owner_and_keeps_first() -> None:
    """Reducer operation 所有权在接缝处唯一，避免 Provider 顺序重写状态折叠。"""

    class _FirstHandler:
        def apply(self, state, delta, reducer):
            return state

    class _ReplacementHandler:
        def apply(self, state, delta, reducer):
            return state

    registry: DeltaHandlerRegistry = InMemoryDeltaHandlerRegistry()
    first = _FirstHandler()
    registry.register("step", first)

    with pytest.raises(KeyError, match="delta handler: operation 'step' already registered"):
        registry.register("step", _ReplacementHandler())

    assert registry.resolve("step") is first
    assert registry.registered_delta_operations() == ("step",)


def test_delta_handler_seam_is_neutral_until_provider_installs_defaults() -> None:
    """The seam must not silently own the provider's default behavior."""
    seam_registry = InMemoryDeltaHandlerRegistry()
    assert seam_registry.resolve("step") is None

    register_default_delta_handlers(seam_registry)
    assert seam_registry.resolve("step") is not None


def test_delta_handler_protocol_exposes_apply_and_delta_snapshot() -> None:
    """Delta contracts expose both handler execution and delta discovery."""

    assert hasattr(DeltaHandler, "apply")
    assert hasattr(DeltaHandlerRegistry, "registered_delta_operations")


def test_effect_handler_registry_protocol_exposes_effect_snapshot() -> None:
    """Effect contracts expose effect discovery for boot diagnostics."""

    assert hasattr(EffectHandlerRegistry, "registered_effect_operations")


# ── Static guard: core paths must not construct handlers by name ───────


def test_runtime_gateway_requires_explicit_effect_registry() -> None:
    """Missing effect bindings must fail at construction, not at side effect time."""

    parameter = inspect.signature(RegistryEffectGateway).parameters["effect_handler_registry"]
    assert parameter.default is inspect.Parameter.empty


def test_runtime_gateway_requires_explicit_idempotency_store() -> None:
    """The gateway must not silently fall back to process-local idempotency."""

    parameter = inspect.signature(RegistryEffectGateway).parameters["idempotency_store"]
    assert parameter.default is inspect.Parameter.empty


def test_runtime_gateway_does_not_construct_handlers_by_name() -> None:
    """Static scan: the gateway must only resolve handlers from its registry.

    The gateway is an execution boundary. Allowing it to create a default
    registry would make missing production bindings silently executable and
    would violate ADR-0075's fail-closed rule. Every concrete handler and
    registry must therefore be assembled by the profile/bundle seam.
    """

    gateway_path = REPO / "lca" / "harness" / "declarative" / "dispatch.py"
    if not gateway_path.exists():
        return
    source = gateway_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RegistryEffectGateway":
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if isinstance(func, ast.Name) and func.id in FORBIDDEN_HANDLER_TYPES:
                    raise AssertionError(
                        f"{gateway_path.relative_to(REPO)}:{sub.lineno} "
                        f"directly constructs {func.id} — register the "
                        "handler through EffectHandlerRegistry instead "
                        "(ADR-0075/0076 strict production binding)."
                    )


def test_declarative_execution_uses_registry_dispatch() -> None:
    """The production Turn module must route effects and deltas through dispatch."""

    runtime_path = REPO / "lca" / "runtime" / "declarative_runtime.py"
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"))
    execution = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DeclarativeExecution"
    )
    called_names = {
        call.func.id
        for call in ast.walk(execution)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    called_attributes = {
        call.func.attr
        for call in ast.walk(execution)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }
    assert "GraphAssembler" in called_names
    assert "new_interpreter" in called_attributes


def test_runtime_binding_has_one_declarative_driver_construction_path() -> None:
    """Fresh and resumed Turns must share one closed runtime assembly seam."""

    binding_path = REPO / "lca" / "runtime" / "runtime_bindings.py"
    tree = ast.parse(binding_path.read_text(encoding="utf-8"))
    binding_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DeclarativeRuntimeBindings"
    )
    driver_constructions = [
        call
        for call in ast.walk(binding_class)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "DeclarativeRuntimeDriver"
    ]

    assert len(driver_constructions) == 1, (
        "DeclarativeRuntimeBindings must construct DeclarativeRuntimeDriver in one shared "
        "factory so fresh and resumed Turns cannot drift."
    )

    runtime_path = REPO / "lca" / "runtime" / "runtime_loop.py"
    assert "DeclarativeRuntimeDriver" not in runtime_path.read_text(encoding="utf-8")


def test_runtime_loop_does_not_construct_handlers_by_name() -> None:
    """The runtime loop must only consume its injected handler registries.

    Fixture defaults belong to the explicit fixture adapter, not to the L2
    execution module.  This preserves one runtime interface for every plan.
    """

    runtime_path = REPO / "lca" / "runtime" / "runtime_loop.py"
    if not runtime_path.exists():
        return
    source = runtime_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    runtime_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "CognitiveRuntime"
        ),
        None,
    )
    assert runtime_class is not None, "CognitiveRuntime must remain defined"
    for sub in ast.walk(runtime_class):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_HANDLER_TYPES:
            raise AssertionError(
                f"{runtime_path.relative_to(REPO)}:{sub.lineno} "
                f"directly constructs {func.id} — substitution test fails "
                "(ADR-0076 §二 / P2)."
            )


__all__ = [
    "test_action_handler_registry_protocol_exposes_registered",
    "test_action_handler_registry_registered_lists_all_keys",
    "test_action_handler_registry_rejects_duplicate_owner_and_keeps_first",
    "test_declarative_execution_uses_registry_dispatch",
    "test_delta_handler_protocol_exposes_apply_and_delta_snapshot",
    "test_delta_handler_registry_rejects_duplicate_owner_and_keeps_first",
    "test_effect_handler_protocol_exposes_handle",
    "test_effect_handler_registry_protocol_exposes_effect_snapshot",
    "test_effect_handler_registry_rejects_duplicate_owner_and_keeps_first",
    "test_replacement_handler_owns_receipt_label",
    "test_runtime_binding_has_one_declarative_driver_construction_path",
    "test_runtime_gateway_does_not_construct_handlers_by_name",
    "test_runtime_gateway_requires_explicit_idempotency_store",
    "test_runtime_loop_does_not_construct_handlers_by_name",
]


@pytest.mark.asyncio
async def test_effect_class_rejects_non_string_metadata_before_handler() -> None:
    """Policy admission must not coerce untrusted metadata into an effect class."""

    class _ShouldNotRun:
        async def handle(self, envelope, policy, capabilities):
            raise AssertionError("handler must not run")

    registry: EffectHandlerRegistry = InMemoryEffectHandlerRegistry()
    registry.register("custom.effect", _ShouldNotRun())
    gateway = RegistryEffectGateway(
        RuntimePhaseCapabilities({}),
        registry,
        InMemoryFixtureIdempotencyStore(),
    )
    envelope = CommandEnvelope(
        plan_ref="plan-typed-effect",
        decision_ref="decision-typed-effect",
        provider="custom-provider",
        grant=CapabilityGrant(capability="custom.effect", scope="run", effect_class="tools"),
        idempotency_key="typed-effect-key",
        metadata={"operation": "custom.effect", "effect_class": 7},
    )

    with pytest.raises(DeclarativeValidationError, match="effect class must be a non-empty string"):
        await gateway.execute(
            envelope,
            EffectPolicyPlan(allowed_effects=("tools",), idempotency_required=("tools",)),
        )


@pytest.mark.parametrize("operation", ["", 7, None])
def test_delta_reducer_rejects_invalid_operation_before_registry_lookup(operation) -> None:
    """Delta operation names are typed inputs at the reducer seam."""
    from lca.contracts.models.core.state import AgentState, Budget
    from lca.contracts.protocols.command_envelope import RunDelta
    from lca.harness.declarative.dispatch import RegistryDeltaReducer

    class _Reducer:
        pass

    reducer = RegistryDeltaReducer(_Reducer(), DefaultDeltaHandlerRegistry())  # type: ignore[arg-type]
    delta = RunDelta(plan_ref="plan-delta", metadata={"operation": operation})

    with pytest.raises(
        DeclarativeValidationError,
        match=r"(RunDelta has no operation|invalid RunDelta operation)",
    ):
        reducer.apply_delta(AgentState(trace_id="t", task="t", budget=Budget()), delta)
