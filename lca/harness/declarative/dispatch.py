"""Registry-backed effect and delta dispatch for declarative execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.command_envelope import CommandEnvelope, RunDelta
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeValidationError,
    DeltaReducer,
    EffectGateway,
    EffectPolicyPlan,
)
from lca.contracts.protocols.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.effect_handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.idempotency import IdempotencyStore
from lca.contracts.protocols.reducer import Reducer
from lca.layer0_infra.component_registry import RegistryKeyError


class RegistryEffectGateway(EffectGateway):
    """Execute plan-authorized effects through profile-provided handlers.

    The gateway owns policy enforcement and durable idempotency.  Concrete
    world operations remain behind the effect-handler registry, so new
    operations require registration rather than runtime changes.
    """

    def __init__(
        self,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> None:
        self._capabilities = capabilities
        self._effect_handler_registry = effect_handler_registry
        self._idempotency_store = idempotency_store

    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> object:
        metadata = envelope.metadata
        effect_class = _validated_effect_class(envelope, policy)

        cached_receipt = await _existing_effect_receipt(
            envelope=envelope,
            idempotency_store=self._idempotency_store,
        )
        if cached_receipt is not None:
            return cached_receipt

        _require_effect_approval(effect_class, metadata, policy)

        operation = metadata.get("operation")
        if not isinstance(operation, str) or not operation:
            raise DeclarativeValidationError(
                "PG-003", "effect operation must be a non-empty string"
            )
        try:
            handler = self._effect_handler_registry.resolve(operation)
        except (KeyError, RegistryKeyError) as exc:
            raise DeclarativeValidationError(
                "PG-003", f"undeclared effect operation: {operation}"
            ) from exc

        effect_output = await handler.handle(envelope, policy, self._capabilities)
        if not envelope.idempotency_key:
            return cast("object", effect_output)

        receipt: dict[str, object] = {
            "receipt": _receipt_name(handler, operation),
            "result": cast("object", effect_output),
            "plan_ref": envelope.plan_ref,
            "idempotency_key": envelope.idempotency_key,
            "operation": operation,
        }
        await self._idempotency_store.complete(
            envelope.plan_ref,
            envelope.idempotency_key,
            receipt,
        )
        return receipt


class RegistryDeltaReducer(DeltaReducer):
    """Fold deltas through profile-provided handlers and the sole Reducer seam."""

    def __init__(self, reducer: Reducer, delta_handler_registry: DeltaHandlerRegistry) -> None:
        self._reducer = reducer
        self._delta_handler_registry = delta_handler_registry

    def apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState:
        operation = _delta_operation(delta)

        try:
            handler = self._delta_handler_registry.resolve(operation)
        except (KeyError, RegistryKeyError) as exc:
            raise DeclarativeValidationError(
                "PG-003", f"undeclared delta operation: {operation}"
            ) from exc
        return handler.apply(state, delta, self._reducer)


def _require_effect_approval(
    effect_class: str, metadata: Mapping[str, object], policy: EffectPolicyPlan
) -> None:
    """Enforce approval policy before selecting a world operation handler."""
    if effect_class in policy.approval_required and not bool(metadata.get("approved", False)):
        raise DeclarativeValidationError("PS-006", f"effect requires approval: {effect_class}")


async def _existing_effect_receipt(
    *, envelope: CommandEnvelope, idempotency_store: IdempotencyStore
) -> object | None:
    """Claim idempotency before effects and return a completed receipt when present."""
    if not envelope.idempotency_key:
        return None
    claim = await idempotency_store.claim(envelope.plan_ref, envelope.idempotency_key)
    if claim.status == "completed":
        return claim.receipt
    if claim.status == "in_progress":
        raise DeclarativeValidationError(
            "RT-003",
            f"effect with idempotency_key {envelope.idempotency_key} was in_progress "
            "when previous execution crashed; effect outcome uncertain",
        )
    return None


def _delta_operation(delta: RunDelta) -> str:
    """Extract a validated operation before crossing the Reducer seam."""
    metadata = delta.metadata
    operation = metadata.get("operation") if isinstance(metadata, Mapping) else None
    if operation is None:
        raise DeclarativeValidationError("PG-003", "RunDelta has no operation")
    if not isinstance(operation, str) or not operation:
        raise DeclarativeValidationError("PG-003", f"invalid RunDelta operation: {operation!r}")
    return operation


def _validated_effect_class(envelope: CommandEnvelope, policy: EffectPolicyPlan) -> str:
    """Validate policy admission before entering idempotency or world effects."""
    metadata = envelope.metadata
    raw_effect_class = metadata.get("effect_class", envelope.grant.effect_class)
    if not isinstance(raw_effect_class, str) or not raw_effect_class:
        raise DeclarativeValidationError("PS-006", "effect class must be a non-empty string")
    effect_class = raw_effect_class
    if effect_class not in policy.allowed_effects:
        raise DeclarativeValidationError(
            "PS-006", f"effect class is denied by plan: {effect_class}"
        )
    if effect_class in policy.idempotency_required and not envelope.idempotency_key:
        raise DeclarativeValidationError("PS-006", "effect requires an idempotency key")
    return effect_class


def _receipt_name(handler: object, operation: str) -> str:
    """Resolve a handler-owned receipt label without operation dispatch here."""
    label = getattr(handler, "receipt_name", None)
    if isinstance(label, str) and label:
        return label
    return f"{operation}.completed"


__all__ = ["RegistryDeltaReducer", "RegistryEffectGateway"]
