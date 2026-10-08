"""Unit tests for the registry-backed declarative dispatch seam.

Covers the guard branches of ``RegistryEffectDispatcher.execute`` (ADR-0235 /
PR-5) and ``RegistryDeltaReducer.apply_delta`` — the dispatch leg of the core
dispatch -> assemble -> run chain. The happy-path idempotency flow (claim /
replay / RT-003 fail-closed) is already covered by
``tests/e2e/test_declarative_long_horizon_recovery.py``; these tests pin the
guard rails instead: policy admission (PS-006), the approval gate, operation
dispatch errors (PG-003), receipt naming, and delta dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.exceptions.registry import RegistryKeyError
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import (
    CapabilityGrant,
    CommandEnvelope,
    RunDelta,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    EffectPolicyPlan,
)
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyClaim
from lca.harness.declarative.execute.dispatch import (
    RegistryDeltaReducer,
    RegistryEffectDispatcher,
)


class _FakeEffectHandler:
    """Minimal EffectHandler: records calls, returns a canned result."""

    def __init__(self, result: Any = None, *, receipt_name: str | None = None) -> None:
        self._result = result
        self.calls: list[tuple[Any, Any, Any]] = []
        if receipt_name is not None:
            self.receipt_name = receipt_name

    async def handle(self, envelope: Any, policy: Any, capabilities: Any, **_: Any) -> Any:
        self.calls.append((envelope, policy, capabilities))
        return self._result


class _DictEffectRegistry:
    """EffectHandlerRegistry backed by a plain dict."""

    def __init__(self, handlers: dict[str, _FakeEffectHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, operation: str, handler: _FakeEffectHandler) -> None:
        self._handlers[operation] = handler

    def resolve(self, operation: str) -> _FakeEffectHandler | None:
        return self._handlers.get(operation)


class _RaisingEffectRegistry(_DictEffectRegistry):
    """Registry whose resolve() always raises (KeyError / RegistryKeyError path)."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def resolve(self, operation: str) -> _FakeEffectHandler | None:
        raise self._exc


@dataclass
class _FakeClaimStore:
    """IdempotencyStore with scripted claim outcomes; records complete() calls."""

    claims: dict[tuple[str, str], IdempotencyClaim] = field(default_factory=dict)
    completed: list[tuple[str, str, object]] = field(default_factory=list)

    async def claim(self, plan_ref: str, idempotency_key: str) -> IdempotencyClaim:
        return self.claims.get(
            (plan_ref, idempotency_key), IdempotencyClaim(status="new")
        )

    async def complete(
        self, plan_ref: str, idempotency_key: str, receipt: object
    ) -> None:
        self.completed.append((plan_ref, idempotency_key, receipt))


def _envelope(
    *,
    operation: str | None = "body.act",
    effect_class: str = "body.act",
    idempotency_key: str = "",
    metadata_extra: dict[str, Any] | None = None,
) -> CommandEnvelope:
    metadata: dict[str, Any] = {}
    if operation is not None:
        metadata["operation"] = operation
    metadata.update(metadata_extra or {})
    return CommandEnvelope(
        plan_ref="plan_v1",
        decision_ref="dec_1",
        provider="test-provider",
        grant=CapabilityGrant(
            capability="body.act", scope="run", effect_class=effect_class
        ),
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


def _policy(**overrides: Any) -> EffectPolicyPlan:
    kwargs: dict[str, Any] = {"allowed_effects": ("body.act",)}
    kwargs.update(overrides)
    return EffectPolicyPlan(**kwargs)


def _dispatcher(
    registry: Any, store: _FakeClaimStore, **kwargs: Any
) -> RegistryEffectDispatcher:
    return RegistryEffectDispatcher(
        object(), registry, idempotency_store=store, **kwargs
    )


def _decision(*, needs_approval: bool = False) -> Decision:
    return Decision(
        decision_id="dec_1",
        action_type="act",
        rationale="test",
        confidence=1.0,
        needs_approval=needs_approval,
    )


class TestPolicyAdmission:
    """PS-006: the gateway rejects envelopes the plan does not authorize."""

    async def test_empty_effect_class_rejected(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        envelope = _envelope(metadata_extra={"effect_class": ""})
        with pytest.raises(
            DeclarativeValidationError,
            match="effect class must be a non-empty string",
        ):
            await gateway.execute(envelope, _policy())

    async def test_effect_class_denied_by_plan_rejected(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        policy = _policy(allowed_effects=("memory.update",))
        with pytest.raises(
            DeclarativeValidationError, match="effect class is denied by plan"
        ):
            await gateway.execute(_envelope(), policy)

    async def test_idempotency_required_without_key_rejected(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        policy = _policy(idempotency_required=("body.act",))
        with pytest.raises(
            DeclarativeValidationError, match="effect requires an idempotency key"
        ):
            await gateway.execute(_envelope(), policy)


class TestApprovalGate:
    """PS-006: approval-gated effects need a decision that cleared approval."""

    async def test_approval_required_denied_without_decision(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        policy = _policy(approval_required=("body.act",))
        with pytest.raises(
            DeclarativeValidationError, match="effect requires approval"
        ):
            await gateway.execute(_envelope(), policy)

    async def test_approval_required_denied_when_decision_still_needs_approval(
        self,
    ) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        policy = _policy(approval_required=("body.act",))
        with pytest.raises(
            DeclarativeValidationError, match="effect requires approval"
        ):
            await gateway.execute(
                _envelope(), policy, decision=_decision(needs_approval=True)
            )

    async def test_approval_cleared_by_decision_allows_execution(self) -> None:
        handler = _FakeEffectHandler(result="ok")
        gateway = _dispatcher(_DictEffectRegistry({"body.act": handler}), _FakeClaimStore())
        policy = _policy(approval_required=("body.act",))
        result = await gateway.execute(
            _envelope(), policy, decision=_decision(needs_approval=False)
        )
        assert result == "ok"
        assert len(handler.calls) == 1

    async def test_constructor_captured_kwargs_reach_handler(self) -> None:
        """RA-043: the documented precedence (per-call kwarg wins,
        constructor-captured values are the fallback) must hold at the
        handler.handle seam — not just at the approval gate. Previously the
        resolved active_decision was computed but the raw kwargs were
        forwarded, silently dropping constructor-captured values."""
        seen: dict[str, Any] = {}

        class _KwargRecordingHandler(_FakeEffectHandler):
            async def handle(
                self, envelope: Any, policy: Any, capabilities: Any, **kwargs: Any
            ) -> Any:
                seen.update(kwargs)
                return await super().handle(envelope, policy, capabilities, **kwargs)

        handler = _KwargRecordingHandler(result="ok")
        constructed_decision = _decision(needs_approval=False)
        constructed_state = object()
        gateway = _dispatcher(
            _DictEffectRegistry({"body.act": handler}),
            _FakeClaimStore(),
            decision=constructed_decision,
            state=constructed_state,
        )
        result = await gateway.execute(_envelope(), _policy())
        assert result == "ok"
        assert seen["decision"] is constructed_decision
        assert seen["state"] is constructed_state

    async def test_per_call_kwarg_still_wins_over_constructor(self) -> None:
        """RA-043: per-call kwargs keep precedence over constructor values
        at the handler seam."""
        seen: dict[str, Any] = {}

        class _KwargRecordingHandler(_FakeEffectHandler):
            async def handle(
                self, envelope: Any, policy: Any, capabilities: Any, **kwargs: Any
            ) -> Any:
                seen.update(kwargs)
                return await super().handle(envelope, policy, capabilities, **kwargs)

        handler = _KwargRecordingHandler(result="ok")
        gateway = _dispatcher(
            _DictEffectRegistry({"body.act": handler}),
            _FakeClaimStore(),
            decision=_decision(needs_approval=False),
            state=object(),
        )
        call_decision = _decision(needs_approval=False)
        call_state = object()
        result = await gateway.execute(
            _envelope(), _policy(), decision=call_decision, state=call_state
        )
        assert result == "ok"
        assert seen["decision"] is call_decision
        assert seen["state"] is call_state

    async def test_typed_decision_kwarg_overrides_constructor_decision(self) -> None:
        handler = _FakeEffectHandler(result="ok")
        gateway = _dispatcher(
            _DictEffectRegistry({"body.act": handler}),
            _FakeClaimStore(),
            decision=_decision(needs_approval=True),
        )
        policy = _policy(approval_required=("body.act",))
        result = await gateway.execute(
            _envelope(), policy, decision=_decision(needs_approval=False)
        )
        assert result == "ok"
        assert len(handler.calls) == 1


class TestOperationDispatch:
    """PG-003: unknown or malformed operations fail at the dispatch seam."""

    async def test_missing_operation_rejected(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        with pytest.raises(
            DeclarativeValidationError,
            match="effect operation must be a non-empty string",
        ):
            await gateway.execute(_envelope(operation=None), _policy())

    async def test_undeclared_operation_key_error_rejected(self) -> None:
        gateway = _dispatcher(
            _RaisingEffectRegistry(KeyError("body.act")), _FakeClaimStore()
        )
        with pytest.raises(
            DeclarativeValidationError, match="undeclared effect operation"
        ):
            await gateway.execute(_envelope(), _policy())

    async def test_undeclared_operation_registry_key_error_rejected(self) -> None:
        gateway = _dispatcher(
            _RaisingEffectRegistry(
                RegistryKeyError("body.act", "effect_handler", [])
            ),
            _FakeClaimStore(),
        )
        with pytest.raises(
            DeclarativeValidationError, match="undeclared effect operation"
        ):
            await gateway.execute(_envelope(), _policy())

    async def test_none_handler_rejected(self) -> None:
        gateway = _dispatcher(_DictEffectRegistry(), _FakeClaimStore())
        with pytest.raises(
            DeclarativeValidationError, match="undeclared effect operation"
        ):
            await gateway.execute(_envelope(), _policy())


class TestReceiptShape:
    """The gateway returns raw output without a key, a receipt dict with one."""

    async def test_no_idempotency_key_returns_raw_handler_output(self) -> None:
        sentinel = object()
        handler = _FakeEffectHandler(result=sentinel)
        store = _FakeClaimStore()
        gateway = _dispatcher(_DictEffectRegistry({"body.act": handler}), store)
        result = await gateway.execute(_envelope(), _policy())
        assert result is sentinel
        assert store.completed == []

    async def test_receipt_uses_handler_receipt_name(self) -> None:
        handler = _FakeEffectHandler(result="done", receipt_name="body.act.v2")
        store = _FakeClaimStore()
        gateway = _dispatcher(_DictEffectRegistry({"body.act": handler}), store)
        result = await gateway.execute(_envelope(idempotency_key="k1"), _policy())
        assert isinstance(result, dict)
        assert result["receipt"] == "body.act.v2"
        assert result["result"] == "done"
        assert result["plan_ref"] == "plan_v1"
        assert result["idempotency_key"] == "k1"
        assert result["operation"] == "body.act"
        assert len(store.completed) == 1

    async def test_receipt_falls_back_to_operation_completed_label(self) -> None:
        handler = _FakeEffectHandler(result="done")
        store = _FakeClaimStore()
        gateway = _dispatcher(_DictEffectRegistry({"body.act": handler}), store)
        result = await gateway.execute(_envelope(idempotency_key="k1"), _policy())
        assert isinstance(result, dict)
        assert result["receipt"] == "body.act.completed"


class _FakeDeltaHandler:
    def __init__(self, new_state: AgentState) -> None:
        self._new_state = new_state
        self.calls: list[tuple[AgentState, RunDelta, Any]] = []

    def apply(
        self, state: AgentState, delta: RunDelta, reducer: Any
    ) -> AgentState:
        self.calls.append((state, delta, reducer))
        return self._new_state


class _DictDeltaRegistry:
    def __init__(self, handlers: dict[str, _FakeDeltaHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def resolve(self, operation: str) -> _FakeDeltaHandler | None:
        return self._handlers.get(operation)


class _RaisingDeltaRegistry(_DictDeltaRegistry):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def resolve(self, operation: str) -> _FakeDeltaHandler | None:
        raise self._exc


def _agent_state() -> AgentState:
    return AgentState(trace_id="trace_1", task="task_1", budget=Budget())


def _delta(operation: Any = "step") -> RunDelta:
    return RunDelta(
        plan_ref="plan_v1",
        run_id="run_1",
        metadata={"operation": operation},
    )


class TestDeltaDispatch:
    """PG-003: delta dispatch resolves the operation before the Reducer seam."""

    def test_apply_delta_delegates_to_registered_handler(self) -> None:
        state = _agent_state()
        new_state = _agent_state()
        handler = _FakeDeltaHandler(new_state)
        fake_reducer = object()
        reducer = RegistryDeltaReducer(fake_reducer, _DictDeltaRegistry({"step": handler}))
        delta = _delta("step")
        result = reducer.apply_delta(state, delta)
        assert result is new_state
        assert len(handler.calls) == 1
        recorded_state, recorded_delta, recorded_reducer = handler.calls[0]
        assert recorded_state is state
        assert recorded_delta is delta
        assert recorded_reducer is fake_reducer

    def test_apply_delta_missing_operation_rejected(self) -> None:
        reducer = RegistryDeltaReducer(object(), _DictDeltaRegistry())
        delta = RunDelta(plan_ref="plan_v1", run_id="run_1", metadata={})
        with pytest.raises(
            DeclarativeValidationError, match="RunDelta has no operation"
        ):
            reducer.apply_delta(_agent_state(), delta)

    def test_apply_delta_empty_operation_rejected(self) -> None:
        reducer = RegistryDeltaReducer(object(), _DictDeltaRegistry())
        with pytest.raises(
            DeclarativeValidationError, match="invalid RunDelta operation"
        ):
            reducer.apply_delta(_agent_state(), _delta(""))

    def test_apply_delta_undeclared_operation_rejected(self) -> None:
        reducer = RegistryDeltaReducer(object(), _DictDeltaRegistry())
        with pytest.raises(
            DeclarativeValidationError, match="undeclared delta operation"
        ):
            reducer.apply_delta(_agent_state(), _delta("nope"))

    def test_apply_delta_registry_key_error_rejected(self) -> None:
        reducer = RegistryDeltaReducer(
            object(), _RaisingDeltaRegistry(KeyError("nope"))
        )
        with pytest.raises(
            DeclarativeValidationError, match="undeclared delta operation"
        ):
            reducer.apply_delta(_agent_state(), _delta("nope"))
