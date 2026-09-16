"""Registry-backed effect and delta dispatch for declarative execution.

ADR-0235 / PR-5: the previous module-level helpers
``_existing_effect_receipt`` (idempotency claim) and
``_validated_effect_class`` (policy admission) were inlined into
:meth:`RegistryEffectDispatcher.execute`. They did not smuggle
``state`` / ``decision`` from ``envelope.metadata`` (those were never
their concern), but they added a layer of indirection that obscured
the typed-contract surface. After PR-5 the dispatcher is the single
typed Contract for the effect gateway; the policy + idempotency steps
are visible inline.
"""

from __future__ import annotations

from typing import cast

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.act.command.envelope import CommandEnvelope, RunDelta
from lca.contracts.protocols.act.effect.handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    DeltaReducer,
    EffectDispatcher,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    EffectPolicyPlan,
)
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer
from lca.infrastructure.component.registry import RegistryKeyError


class RegistryEffectDispatcher(EffectDispatcher):
    """Execute plan-authorized effects through profile-provided handlers.

    The gateway owns policy enforcement and durable idempotency.  Concrete
    world operations remain behind the effect-handler registry, so new
    operations require registration rather than runtime changes.

    ADR-0235 / PR-5: ``state`` and ``decision`` are typed keyword-only
    parameters (per ADR-0195 §1.4 C13). They replace the previous
    ``envelope.metadata`` smuggle path. The dispatcher does **not** read
    them off metadata; consumers pass them as typed kwargs from their own
    typed ports (``effect.execute`` typed ports ``decision`` /
    ``state``).
    """

    def __init__(
        self,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._effect_handler_registry = effect_handler_registry
        self._idempotency_store = idempotency_store
        self._state = state
        self._decision = decision

    async def execute(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        *,
        state: AgentState | None = None,
        decision: Decision | None = None,
    ) -> object:
        # typed kwargs take precedence over the constructor-captured values
        del state  # state is accepted for typed-Contract symmetry; admission
        # / dispatch do not read it. Handlers that need state must read it
        # from the typed envelope / CapabilityGrant (not from the dispatcher's
        # constructor state).
        active_decision = decision if decision is not None else self._decision

        # --- policy admission (was _validated_effect_class) ---------------
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

        # --- idempotency claim (was _existing_effect_receipt) -------------
        if envelope.idempotency_key:
            claim = await self._idempotency_store.claim(envelope.plan_ref, envelope.idempotency_key)
            if claim.status == "completed":
                return claim.receipt
            if claim.status == "in_progress":
                raise DeclarativeValidationError(
                    "RT-003",
                    f"effect with idempotency_key {envelope.idempotency_key} was in_progress "
                    "when previous execution crashed; effect outcome uncertain",
                )

        # --- approval gate (typed Contract via Decision.needs_approval) --
        if effect_class in policy.approval_required:
            approved = bool(
                active_decision is not None
                and not getattr(active_decision, "needs_approval", False)
            )
            if not approved:
                raise DeclarativeValidationError(
                    "PS-006", f"effect requires approval: {effect_class}"
                )

        # --- dispatch ----------------------------------------------------
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
        if handler is None:
            raise DeclarativeValidationError("PG-003", f"undeclared effect operation: {operation}")

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
        if handler is None:
            raise DeclarativeValidationError("PG-003", f"undeclared delta operation: {operation}")
        return handler.apply(state, delta, self._reducer)


def _delta_operation(delta: RunDelta) -> str:
    """Extract a validated operation before crossing the Reducer seam."""
    metadata = delta.metadata
    operation = metadata.get("operation") if isinstance(metadata, dict) else None
    if operation is None:
        raise DeclarativeValidationError("PG-003", "RunDelta has no operation")
    if not isinstance(operation, str) or not operation:
        raise DeclarativeValidationError("PG-003", f"invalid RunDelta operation: {operation!r}")
    return operation


def _receipt_name(handler: object, operation: str) -> str:
    """Resolve a handler-owned receipt label without operation dispatch here."""
    label = getattr(handler, "receipt_name", None)
    if isinstance(label, str) and label:
        return label
    return f"{operation}.completed"


__all__ = ["RegistryDeltaReducer", "RegistryEffectDispatcher"]
