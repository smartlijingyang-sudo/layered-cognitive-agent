"""Adapter: legacy ``RunPort`` → ``RuntimeFacade.RunDispatcher`` (ADR-0199 P1-11).

# COMPAT(owner: ADR-0199, from: handler-direct-RunPort, to: RuntimeFacade,
#        delete_when: LCA_RUNTIME_FACADE flag removed + single-path test
#        + zero hits in scripts/route_legacy_patterns.py for "create_run",
#        forbidden_new_usage: handler-internal resolve_profile)

This is the COMPAT bridge that lets the :class:`RuntimeFacade` carrier path
use the existing :meth:`RunPort.create_and_dispatch` under the hood while
the transport handlers migrate to the facade one path at a time. Per
ADR-0199 §12.2 COMPAT template.

Production code MUST go through the facade directly with a real
:class:`~lca.application.runtime.default_facade.DefaultRuntimeFacade`;
this adapter exists only so the ``LCA_RUNTIME_FACADE=0`` legacy path can
be exercised during the dual-path window without a parallel handler
implementation.
"""

from __future__ import annotations

from lca.contracts.runtime.activation import SessionActivation
from lca.contracts.runtime.facade import RunHandle
from lca.contracts.runtime.intent import RunIntent
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
    RunPort,
    RunReceipt,
    RunRequest,
)


class LegacyRunDispatcher:
    """Adapt :meth:`RunPort.create_and_dispatch` to the ``RunDispatcher`` port.

    This is NOT production code — it's the COMPAT bridge that lets the
    facade route through the existing carrier while we transition handlers.
    Once ``LCA_RUNTIME_FACADE`` is removed and ``create_run`` has a single
    facade path, this adapter becomes unused and can be deleted.
    """

    def __init__(self, run_port: RunPort) -> None:
        self._port = run_port

    async def dispatch_run(
        self,
        activation: SessionActivation,
        intent: RunIntent,
    ) -> RunHandle:
        # Convert RunIntent → RunRequest for the legacy port.
        # Per ADR-0199 P1-11 spec: keep RunPort signature unchanged.
        request = RunRequest(
            profile=intent.profile_path,
            question=intent.user_text,
            user_text=intent.user_text,
            mode=str(intent.mode),
            attachment_ids=intent.attachment_ids,
            prior_turns=intent.prior_turns,
            agent=None,  # legacy field; RunIntent does not carry it
            device_id=intent.device_id,
            plane="",
            extra_plane="",
            execution_target=intent.execution_target,
            options=dict(intent.options),
            ctx=None,  # ctx is recovered via _run_port_of at the call site
            assistant_id=intent.assistant_id,
        )
        receipt: RunReceipt = await self._port.create_and_dispatch(request)
        if not receipt.accepted:
            raise RuntimeError(f"carrier rejected run: {receipt.rejection_reason or 'unknown'}")
        return RunHandle(receipt.run_id)

    async def dispatch_resume(
        self,
        activation: SessionActivation,
        run_id: str,
    ) -> RunHandle:
        # Legacy port doesn't expose a generic resume entry. ADR-0163 keeps
        # this responsibility in the carrier; until facade defines its own
        # resume surface, raise so callers fail loud.
        raise NotImplementedError(
            "facade.dispatch_resume not yet wired to legacy carrier — "
            "use carrier.resume path until P1-13."
        )


__all__ = ("LegacyRunDispatcher",)
