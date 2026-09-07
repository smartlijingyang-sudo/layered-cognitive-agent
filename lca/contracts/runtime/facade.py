"""L1 Port — RuntimeFacade (ADR-0199 §2.2.3).

The unique consumer of :class:`~lca.contracts.runtime.intent.RunIntent`
that produces :class:`~lca.contracts.runtime.activation.SessionActivation`.
L0 adapters (CLI/HTTP/test) must NOT call ``resolve_profile`` or
``compile_run_plan`` directly — they go through this facade (I-HPC-1:
入口薄 — surface is thin and only emits ``RunIntent``).

Dependencies:
    - This module lives in ``lca.contracts`` and therefore must not import
      from ``lca.harness``, ``lca.application``, ``lca.infrastructure``,
      ``lca.cognition``, ``lca.runtime``, ``lca.agent``, or ``lca.plugins``
      (enforced by ``importlinter``).
    - Forward references to ``RunIntent`` and ``SessionActivation`` are
      resolved lazily by ``from __future__ import annotations`` so the
      parallel PRs (P1-01, P1-03) landing in this same package do not
      create a circular import at module-load time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.runtime.activation import SessionActivation
    from lca.contracts.runtime.intent import RunIntent

# RunHandle — minimal placeholder for P1-04. Per P1-10 it gets replaced
# with the real ``run_id`` type. We define it as a ``NewType`` so downstream
# code can carry a typed handle without runtime overhead (NewType erases to
# ``str`` at runtime; see ``tests/contracts/runtime/test_runtime_facade_protocol.py::test_run_handle_is_str_subtype``).
RunHandle = NewType("RunHandle", str)

__all__ = ("FORBIDDEN_UPPER_LAYER_IMPORTS", "RunHandle", "RuntimeFacade")

# Upper-layer modules this contract must NEVER depend on. Mirrors
# ``pyproject.toml`` importlinter contract #3 (contracts purity).
# Exposed for the import-isolation test in
# ``tests/contracts/runtime/test_runtime_facade_protocol.py``.
FORBIDDEN_UPPER_LAYER_IMPORTS: tuple[str, ...] = (
    "lca.infrastructure",
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
    "lca.harness",
    "lca.plugins",
)


@runtime_checkable
class RuntimeFacade(Protocol):
    """L1 Port — the single public entry point for any surface.

    Per ADR-0199 §2.2.3: ``RuntimeFacade`` is the unique consumer of
    :class:`~lca.contracts.runtime.intent.RunIntent` that produces
    :class:`~lca.contracts.runtime.activation.SessionActivation`. L0
    adapters (CLI/HTTP/test) must NOT ``resolve_profile`` or
    ``compile_run_plan`` directly (I-HPC-1).
    """

    def resolve_activation(self, intent: RunIntent) -> SessionActivation:
        """Resolve a ``RunIntent`` into a plan-bound ``SessionActivation``.

        Pure K1+K2: resolve profile → compile plan → derive ``activation_ref``
        from the resulting refs. Does NOT boot a cordis ``Context`` and
        does NOT start a run (I-HPC-2: ``CompiledRunPlan`` is immutable —
        resolve must not mutate it; I-HPC-3: activation binds the resulting
        refs so durable events can be correlated).

        Failure modes: rejected ``RunIntent`` (empty profile / user_text) is
        a caller error and must raise ``ValueError``; profile resolution
        or compile failures propagate as the underlying exception — the
        facade does not invent a parallel fallback (I-HPC-4).
        """
        ...

    def dispatch_run(self, activation: SessionActivation, intent: RunIntent) -> RunHandle:
        """Dispatch a session activation for execution.

        ``intent`` is forwarded because the dispatcher needs the
        surface-level request (user_text, mode, attachment_ids, etc.)
        that the facade already validated (PR-0199-P1-10): the facade is
        the single boundary that converts an intent into a plan-bound
        activation AND the request payload an executor needs to drive
        the run.

        Returns a :data:`RunHandle`. Caller may poll via existing run
        status APIs. The activation is read-only and its ``activation_ref``
        must appear on every durable event produced by the resulting run
        (I-HPC-3). Idempotency follows the existing ADR-0163 contract —
        duplicate dispatch with the same ``activation_ref`` is a
        no-op-or-replay decision delegated to the implementation.
        """
        ...

    def dispatch_resume(self, activation: SessionActivation, run_id: str) -> RunHandle:
        """Resume an existing run using a previously-bound activation.

        Used for HIL / approval resume paths (ADR-0163 idempotency).
        ``activation`` must reference the same ``plan_ref`` /
        ``graph_ref`` / ``plugin_set_ref`` as the original run so the
        resume stays inside the original compiled closure (I-HPC-2:
        a resume must not switch plans; I-HPC-4: the implementation must
        not fall back to a different profile mid-resume).
        """
        ...
