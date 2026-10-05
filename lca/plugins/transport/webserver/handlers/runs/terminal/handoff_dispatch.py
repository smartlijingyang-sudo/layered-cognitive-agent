"""Start a real run for one cron handoff (ADR-0268 §6, §8.1).

The scheduler owns the tick and the run record. This owns the one side effect
that can put a bubble in a conversation, which is starting a run bound to that
conversation. It goes through the same ``RunPort`` the HTTP route uses and
registers with the gateway afterwards, so the browser can resolve the topic to
the run and attach to its stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from lca.cognition.team.modes_catalog import SOLO_ROLE
from lca.contracts.models.cron.models import ChatDelivery, ScheduledHandoff
from lca.domain.cron.handoff_dispatch import ReceiptState, render_handoff_text
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.gateway_lifecycle import (
    register_gateway_run,
)
from lca.plugins.transport.webserver.read.runs.identity.identity import AgentRef

_log = logging.getLogger(__name__)

__all__ = ["LcaRunHandoffDispatcher"]

NOTHING_TO_DO = "lca.nothing_to_do"

_PROFILE = "web-assistant"
"""Both existing in-process dispatchers hardcode this. Resolving it per assistant
is a separate change; see the module's follow-up note."""


class LcaRunHandoffDispatcher:
    """Implements ``ScheduledHandoffDispatcher`` over ``RunPort``."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def dispatch(self, handoff: ScheduledHandoff, *, target: ChatDelivery) -> str:
        run_port = getattr(self._app.state, "run_port", None)
        registry = getattr(self._app.state, "registry", None)
        if run_port is None or registry is None:
            raise RuntimeError("handoff dispatch needs run_port and registry on app.state")

        text = render_handoff_text(handoff)
        owner = handoff.task_context.owner
        request = RunRequest(
            profile=_PROFILE,
            question=text,
            # Unique per occurrence on purpose. run_dedup_key is built from
            # user_text, mode, attachment_ids and agent_id and omits the
            # conversation, so a recurring job sending identical text would
            # otherwise coalesce into a live run and the handoff would vanish
            # (ADR-0268 §8.1). The loop appends no user message for a seeded
            # run, so this never becomes a bubble.
            user_text=f"[cron-handoff {handoff.run_id}]",
            mode="solo",
            attachment_ids=(),
            # The handoff turn sees the report and not the conversation. §6 lets
            # the parent decide from the report; giving it prior turns is a
            # follow-up, not a silent gap.
            prior_turns=(),
            agent=AgentRef(agent_id=owner, name=SOLO_ROLE),
            device_id="",
            plane="",
            extra_plane="",
            execution_target="",
            options={},
            ctx=getattr(self._app.state, "ctx", None),
            assistant_id=owner,
            topic_id=target.chat_id,
            origin="handoff",
            developer_seed=text,
            developer_seed_job_id=handoff.job_id,
        )

        receipt = await run_port.create_and_dispatch(request)
        if not receipt.accepted:
            raise RuntimeError(receipt.rejection_reason or "handoff run rejected")

        await register_gateway_run(
            self._app,
            run_id=receipt.run_id,
            topic_id=target.chat_id,
            agent_id=str(owner),
            assistant_id=owner,
        )
        _log.info(
            "cron.handoff_dispatched job_id=%s occurrence=%s run_id=%s chat_id=%s",
            handoff.job_id,
            handoff.run_id,
            receipt.run_id,
            target.chat_id,
        )
        return str(receipt.run_id)

    async def await_receipt(self, run_id: str) -> ReceiptState:
        registry = getattr(self._app.state, "registry", None)
        session = registry.get(run_id) if registry is not None else None
        if session is None:
            return "failed"
        task = getattr(session, "task", None)
        if task is not None:
            # The run's own budget terminates it, so this does not need a second
            # timeout. A run that never ends is a budget defect, not a cron one.
            with contextlib.suppress(Exception):
                await asyncio.shield(task)
        output = getattr(session, "output", "") or ""
        if isinstance(output, str) and output.strip():
            return "delivered"
        if _turn_called_nothing_to_do(run_id):
            return "silent"
        _log.warning("cron.handoff_turn_produced_nothing run_id=%s", run_id)
        return "failed"


def _turn_called_nothing_to_do(run_id: str) -> bool:
    """Read the run's spine for a ``lca.nothing_to_do`` call.

    The spine is the durable record of what the model emitted, and reading it is
    already how an in-process caller introspects a run it started.
    """
    path = Path("traces") / "runs" / run_id / f"{run_id}.spine.jsonl"
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if NOTHING_TO_DO not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                payload = event.get("payload") or {}
                if (
                    event.get("execution_point") == "step.tool_call.record"
                    and payload.get("tool_name") == NOTHING_TO_DO
                ):
                    return True
    except OSError:
        return False
    return False
