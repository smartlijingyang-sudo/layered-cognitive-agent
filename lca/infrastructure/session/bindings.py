"""Run-scoped Session + checkpoint bindings for cognition hot paths."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.session.checkpoint_policy import (
    FlushableSession,
    SessionCheckpointPolicyProtocol,
)
from lca.contracts.protocols.session.model_context import (
    ModelContextAssembler,
    SessionReader,
)
from lca.infrastructure.session.model_context_assembler import (
    default_model_context_assembler,
)
from lca.plugins.events.publishers._session_publish import current_publish_session
from lca.plugins.session.runtime.bus_facade import SessionBusFacade
from lca.plugins.session.runtime.session import Session

_model_context_assembler: contextvars.ContextVar[ModelContextAssembler | None] = (
    contextvars.ContextVar("lca_model_context_assembler", default=None)
)
_checkpoint_policy_var: contextvars.ContextVar[SessionCheckpointPolicyProtocol | None] = (
    contextvars.ContextVar("lca_session_checkpoint_policy", default=None)
)
_default_checkpoint_policy: SessionCheckpointPolicyProtocol | None = None


def _resolve_runtime_session(target: object | None) -> Session | None:
    if target is None:
        return None
    if isinstance(target, Session):
        return target
    inner = getattr(target, "inner", None)
    if isinstance(inner, Session):
        return inner
    if isinstance(target, SessionBusFacade):
        return target.session
    session = getattr(target, "session", None)
    if isinstance(session, Session):
        return session
    return None


def resolve_session_reader() -> SessionReader | None:
    """Bound publish/observe Session as :class:`SessionReader`, or ``None``."""
    session = _resolve_runtime_session(current_publish_session())
    if session is None:
        return None
    return session


def resolve_flushable_session() -> FlushableSession | None:
    """Bound runtime Session for checkpoint ``flush()``, or ``None``."""
    return resolve_session_reader()


def resolve_session_for_emit(state: AgentState | None = None) -> Session | None:
    """Bound Session writer for cognitive fact emission, or ``None``.

    ``state`` is accepted for call-site symmetry (step metadata lives on
    state; session binding is always contextvar-based today).
    """
    _ = state
    return _resolve_runtime_session(current_publish_session())


def current_model_context_assembler() -> ModelContextAssembler:
    assembler = _model_context_assembler.get()
    if assembler is not None:
        return assembler
    return default_model_context_assembler()


def _resolve_checkpoint_policy() -> SessionCheckpointPolicyProtocol:
    policy = _checkpoint_policy_var.get()
    if policy is not None:
        return policy
    global _default_checkpoint_policy
    if _default_checkpoint_policy is None:
        from lca.plugins.session.checkpoint_policy.checkpoint_policy import (
            SessionCheckpointPolicy,
        )

        _default_checkpoint_policy = SessionCheckpointPolicy(enabled=True)
    return _default_checkpoint_policy


def assemble_model_history(*, step: int) -> list[dict[str, Any]]:
    """Model wire history from bound Session fold; unbound → empty list."""
    session = resolve_session_reader()
    if session is None:
        return []
    return current_model_context_assembler().assemble(session, step=step).messages


async def await_model_request_checkpoint() -> None:
    """DSH ``llm/stream`` boundary; no-op when Session is unbound."""
    session = resolve_flushable_session()
    if session is None:
        return
    await _resolve_checkpoint_policy().before_model_request(session)


async def await_tool_side_effect_checkpoint() -> None:
    """DSH ``tools/execute`` boundary; no-op when Session is unbound."""
    session = resolve_flushable_session()
    if session is None:
        return
    await _resolve_checkpoint_policy().before_tool_side_effect(session)


async def await_step_boundary_checkpoint() -> None:
    """DSH ``agent/pre-step`` boundary; no-op when Session is unbound."""
    session = resolve_flushable_session()
    if session is None:
        return
    await _resolve_checkpoint_policy().at_step_boundary(session)


@contextmanager
def set_model_context_assembler(
    assembler: ModelContextAssembler | None,
) -> Iterator[None]:
    token = _model_context_assembler.set(assembler)
    try:
        yield
    finally:
        _model_context_assembler.reset(token)


@contextmanager
def set_checkpoint_policy(
    policy: SessionCheckpointPolicyProtocol | None,
) -> Iterator[None]:
    token = _checkpoint_policy_var.set(policy)
    try:
        yield
    finally:
        _checkpoint_policy_var.reset(token)


__all__ = [
    "assemble_model_history",
    "await_model_request_checkpoint",
    "await_step_boundary_checkpoint",
    "await_tool_side_effect_checkpoint",
    "current_model_context_assembler",
    "resolve_flushable_session",
    "resolve_session_for_emit",
    "resolve_session_reader",
    "set_checkpoint_policy",
    "set_model_context_assembler",
]
