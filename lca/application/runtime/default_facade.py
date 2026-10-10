"""Default ``RuntimeFacade`` — resolve + dispatch (PR-0199-P1-09 + P1-10).

The single Application Service that consumes a :class:`RunIntent` and
produces a plan-bound :class:`SessionActivation`, then dispatches it for
execution. Per ADR-0199 §2.2.3 ``RuntimeFacade`` is the unique L1 Port;
L0 adapters (CLI/HTTP/test) MUST NOT ``resolve_profile``, ``compile_plan``,
or call the lifecycle coordinator directly (I-HPC-1).

Invariants enforced here:

  I-HPC-1  入口薄 — only this facade consumes ``RunIntent`` and emits
            a ``RunHandle`` / ``SessionActivation`` pair.
  I-HPC-2  Plan 不可变 — ``CompiledRunPlan`` captured once from
            ``PlanResolutionService``, never re-bound; the activation's
            ``compiled_plan`` is a read-only reference forwarded as-is
            to the dispatcher.
  I-HPC-3  Activation 绑定 — ``activation_ref`` is stable across calls
            and durable events carry it.
  C9       幂等 — same intent + same ``session_id`` → same
            ``activation_ref``.
  C8       确定性 — ``session_id`` generation is the only side-effect;
            if ``RunIntent.session_id`` is set, no RNG is consulted.

Dispatch contract (PR-0199-P1-10):

  ``dispatch_run`` forwards the activation AND the originating
  ``RunIntent`` to an injected :class:`RunDispatcher`. The dispatcher
  is the single seam where K3 boot happens; the facade does NOT
  ``Session.append`` or boot a cordis ``Context``. Per ADR-0199 §2.2.3
  the existing :class:`RunLifecycleCoordinator` is delegated to
  (``不复制`` loop) — concrete dispatchers wrap the carrier seam.

.. note::

   ``lca.application`` is the composition root. Per ADR-0199 P1-06 the
   activation_ref hashing stays owned by the harness layer, and P1-07
   resolves profiles through harness K1/K2. The package contract in
   :file:`pyproject.toml` therefore allows ``lca.harness`` /
   ``lca.plugins`` and forbids only ``gateway``;
   ``scripts/check_package_contracts.py`` enforces the forbidden list
   against actual imports (``check_actual_forbidden_imports``).
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lca.application.runtime.plan_resolution import PlanResolutionService
from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.facade import RunHandle, RuntimeFacade
from lca.contracts.runtime.intent import RunIntent
from lca.contracts.runtime.trust import (
    RULE_DEFAULTS,
    PluginOrigin,
    TrustEnvelope,
    trust_envelope_scope,
)
from lca.harness.runtime.activation_ref import compute_activation_ref
from lca.infrastructure.assistant.io import load_grants
from lca.infrastructure.path.locator import get_lca_home

if TYPE_CHECKING:
    from lca.application.runtime.plan_resolution import PlanResolutionResult

# Default session id length — 16 hex chars (8 bytes of entropy).
# Per C9 the generated session_id must be deterministic for the same
# intent; when the intent already supplies one we never consult the RNG.
# ``secrets`` is the only allowed RNG for session_id generation per C8
# (no time / PID / env reads in ``compute_activation_ref`` — see
# ``tests/harness/runtime/test_activation_ref.py::TestDeterminismInvariants``).
_SESSION_ID_PREFIX: str = "sess_"
_SESSION_ID_BYTES: int = 8


def _new_session_id() -> str:
    """Return a freshly-minted session id (``"sess_" + 16 hex chars``).

    Length is 21 chars total. Uses ``secrets.token_hex`` so the id is
    crypto-quality and never reused. This is the only path that mints
    new session_ids from the facade; callers that pre-supply
    ``RunIntent.session_id`` skip the RNG entirely.
    """
    return f"{_SESSION_ID_PREFIX}{secrets.token_hex(_SESSION_ID_BYTES)}"


def _assistant_home(assistant_id: str) -> Path | None:
    """Resolve ``{lca_home}/assistants/{assistant_id}``; None when unbound."""
    if not assistant_id:
        return None
    return get_lca_home() / "assistants" / assistant_id


def _assistant_grants(assistant_id: str) -> frozenset[str]:
    """Read the assistant's ``grants.yaml`` grant set (ADR-0242 D13)."""
    home = _assistant_home(assistant_id)
    if home is None:
        return frozenset()
    return load_grants(home)


def _plugin_origins(result: PlanResolutionResult, profile_path: str) -> tuple[PluginOrigin, ...]:
    """Build envelope origins from the resolved profile's plugin specs.

    ``PluginSpec`` 不携带 source/trust（``PluginOrigin`` 的审计字段），统一按
    bundled/core 记录。origins 只用于审计闭包，不参与 ``grants()`` 判定。
    非 tuple（测试桩 / 未编译计划）时回退到单一 profile origin。
    """
    specs = getattr(result.compiled_plan, "plugin_specs", None)
    if not isinstance(specs, tuple) or not specs:
        return (
            PluginOrigin(
                source="bundled",
                trust="core",
                enabled_by=profile_path,
                discovered_at="resolve_activation",
            ),
        )
    return tuple(
        PluginOrigin(
            source="bundled",
            trust="core",
            enabled_by=profile_path,
            discovered_at="resolve_activation",
        )
        for _ in specs
    )


@runtime_checkable
class RunDispatcher(Protocol):
    """Application-side port the facade calls to actually execute a run.

    Per ADR-0199 I-HPC-2 + PR-0199-P1-10: the facade does NOT own loop
    execution. It produces a :class:`SessionActivation`, hands it (and
    the originating :class:`RunIntent`) to a :class:`RunDispatcher`, and
    gets back a :data:`RunHandle`. The dispatcher is the single seam
    where K3 boot happens (NOT in the facade).

    Implementations: HTTP path can wrap ``RunPort.create_and_dispatch``
    (delegating to ``RunLifecycleCoordinator``); CLI path can wrap the
    same with a stub ``ctx``; tests use a stub. Each implementation
    owns its own idempotency keys, run_id minting, and durable
    :meth:`Session.append` calls — the facade never reaches into the
    lifecycle seam.
    """

    async def dispatch_run(
        self,
        activation: SessionActivation,
        intent: RunIntent,
    ) -> RunHandle:
        """Dispatch a freshly-resolved activation for execution."""
        ...

    async def dispatch_resume(
        self,
        activation: SessionActivation,
        run_id: str,
    ) -> RunHandle:
        """Resume an existing run using a previously-bound activation."""
        ...


class DefaultRuntimeFacade(RuntimeFacade):
    """Reference :class:`RuntimeFacade` implementation (P1-09 + P1-10).

    Per ADR-0199 §2.2.3:

      * Constructor-injected :class:`PlanResolutionService` and
        :class:`RunDispatcher` (no global lookup, no Service Locator —
        I-HPC-9).
      * ``resolve_activation`` is pure K1+K2 — no K3 boot, no
        ``Session.append``, no ``ctx`` creation. The facade returns a
        value object that downstream code may pass to dispatch.
      * ``dispatch_run`` / ``dispatch_resume`` forward the activation
        verbatim to the dispatcher; they do NOT mutate the activation
        (I-HPC-2 read-only transmission) and do NOT inspect plan
        internals. The dispatcher is the seam where the
        ``RunLifecycleCoordinator`` / ``Session.append`` /
        ``cordis.Context`` boot happens.
    """

    def __init__(
        self,
        plan_resolution_service: PlanResolutionService,
        run_dispatcher: RunDispatcher,
    ) -> None:
        # Constructor injection — I-HPC-9 forbids global mutable lookups.
        self._plans = plan_resolution_service
        self._dispatcher = run_dispatcher

    # ── K1+K2 surface (P1-09) ──────────────────────────────────────────

    def resolve_activation(self, intent: RunIntent) -> SessionActivation:
        """Resolve a :class:`RunIntent` into a plan-bound :class:`SessionActivation`.

        Flow (ADR-0199 P1-09):

          1. ``session_id`` = ``intent.session_id`` OR ``_new_session_id()``
             when absent (C9 — idempotent given the same intent).
          2. ``plan_refs`` = ``PlanResolutionService.resolve_refs(
             intent.profile_path, session_id=session_id)`` — does not
             boot a fiber, does not write the journal.
          3. ``activation_ref`` = ``compute_activation_ref(plan_ref,
             graph_ref, plugin_set_ref, session_id)`` — deterministic
             sha256 per C8.
          4. Return ``SessionActivation(activation_ref=..., plan_ref=...,
             graph_ref=..., plugin_set_ref=..., profile_path=...,
             session_id=..., trust_envelope=<真实 grant 集>, compiled_plan=plan)``.

        The trust envelope carries the assistant's grants plus rule defaults
        (ADR-0292 §10 P3): ``load_grants(home) | RULE_DEFAULTS``.
        """
        session_id = intent.session_id or _new_session_id()

        result: PlanResolutionResult = self._plans.resolve_refs(
            intent.profile_path,
            session_id=session_id,
            # ADR-0242 D10: facade 路径透传 assistant_id；PlanResolutionService
            # 在 composition root 注入 catalog 解析器时据此走 per-agent 缓存。
            # 无 assistant_id / 无 provider 时行为与启用前一致（I-B8）。
            assistant_id=intent.assistant_id or "",
        )

        activation_ref = compute_activation_ref(
            plan_ref=result.plan_ref,
            graph_ref=result.graph_ref,
            plugin_set_ref=result.plugin_set_ref,
            session_id=session_id,
        )

        return SessionActivation(
            activation_ref=activation_ref,
            plan_ref=result.plan_ref,
            graph_ref=result.graph_ref,
            plugin_set_ref=result.plugin_set_ref,
            profile_path=str(intent.profile_path),
            session_id=session_id,
            trust_envelope=self._build_trust_envelope(intent, result),
            compiled_plan=result.compiled_plan,
        )

    def _build_trust_envelope(
        self, intent: RunIntent, result: PlanResolutionResult
    ) -> TrustEnvelope:
        """ADR-0292 §10 P3: 构造带真实 grant 的 TrustEnvelope。

        ``granted_privileges = assistant grants.yaml ∪ RULE_DEFAULTS``；
        ``origins`` 取 resolved profile 的插件集（PluginSpec 不携带
        source/trust，统一按 bundled/core 记录）。origins 只用于审计闭包，
        不参与 ``grants()`` 判定。
        """
        granted = _assistant_grants(intent.assistant_id) | RULE_DEFAULTS
        origins = _plugin_origins(result, str(intent.profile_path))
        return TrustEnvelope(origins=origins, granted_privileges=granted)

    # ── Dispatch surface (P1-10) ───────────────────────────────────────

    async def dispatch_run(
        self,
        activation: SessionActivation,
        intent: RunIntent,
    ) -> RunHandle:
        """Dispatch a session activation for execution (PR-0199-P1-10).

        Per ADR-0199 §2.2.3 ``dispatch_run`` delegates to the
        application-side :class:`RunDispatcher` (which in turn wraps
        ``RunLifecycleCoordinator.execute`` — the facade does NOT
        call the coordinator directly). The activation is forwarded
        read-only (I-HPC-2); the originating ``intent`` is forwarded
        because the dispatcher needs the user-facing request payload
        (user_text, mode, attachment_ids) to drive the run.

        Returns a :data:`RunHandle` straight from the dispatcher. The
        facade does not mint or rewrite the handle.

        Binds ``activation.trust_envelope`` as the ambient TrustEnvelope
        for the dispatch (ADR-0292 section 10): downstream gates (e.g.
        ``act.approve.gate``) read grants via ``get_current_trust_envelope``.
        The scope resets on return — no envelope leaks across dispatches.
        """
        with trust_envelope_scope(activation.trust_envelope):
            return await self._dispatcher.dispatch_run(activation, intent)

    async def dispatch_resume(
        self,
        activation: SessionActivation,
        run_id: str,
    ) -> RunHandle:
        """Resume an existing run using a previously-bound activation.

        Per ADR-0163 idempotency: a resume must keep the original
        ``plan_ref`` / ``graph_ref`` / ``plugin_set_ref`` triple so
        the resume stays inside the original compiled closure (I-HPC-2).
        The ``run_id`` is forwarded as-is — the dispatcher / lifecycle
        coordinator owns durable identity (it lives in ``Session``).

        Binds ``activation.trust_envelope`` as the ambient TrustEnvelope
        for the resume (ADR-0292 section 10) — same contract as
        ``dispatch_run``.
        """
        with trust_envelope_scope(activation.trust_envelope):
            return await self._dispatcher.dispatch_resume(activation, run_id)


__all__ = ("DefaultRuntimeFacade", "RunDispatcher")
