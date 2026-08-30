"""Session-Spine adapter for continuous-control-plane work items.

The adapter contains no queue or cognitive-loop policy.  It turns one already
leased work item into idempotent session commands, so retrying a worker after a
crash cannot create a second Session or enqueue the same activation twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.harness.act.command import AgentRegistryFacade
from lca.contracts.harness.tasks.continuous import (
    SessionWorkActivator,
    WorkActivationReceipt,
    WorkItem,
)


@dataclass(frozen=True, slots=True)
class AgentRegistryWorkActivator(SessionWorkActivator):
    """Activate continuous work exclusively through the command-level registry facade."""

    registry: AgentRegistryFacade

    async def activate(self, item: WorkItem) -> WorkActivationReceipt:
        """Create or reuse a deterministic Session and enqueue one stable message.

        The deterministic Session ID makes creation replay-safe across process
        restarts.  The message ID is derived from ``work_id`` and is checked by
        the command router against durable inbox facts before it can be appended
        again.
        """

        session_id = item.session_id or f"ses-work-{item.work_id}"
        if item.session_id is None:
            created = await self.registry.create_session(
                idempotency_key=f"continuous:create:{item.work_id}",
                profile=item.profile or "",
                preset=item.preset,
                options=item.options or None,
                session_id=session_id,
            )
            if not created.accepted:
                return WorkActivationReceipt(
                    accepted=False,
                    session_id=created.session_id,
                    detail=created.rejection_reason or "session_create_rejected",
                )
            session_id = created.session_id
        dispatched = await self.registry.dispatch_message(
            session_id=session_id,
            idempotency_key=f"continuous:dispatch:{item.work_id}",
            content=item.message,
            role="user",
            message_id=f"msg-work-{item.work_id}",
        )
        return WorkActivationReceipt(
            accepted=dispatched.accepted,
            session_id=dispatched.session_id,
            detail=dispatched.rejection_reason or "work_dispatched",
        )


__all__ = ["AgentRegistryWorkActivator"]
