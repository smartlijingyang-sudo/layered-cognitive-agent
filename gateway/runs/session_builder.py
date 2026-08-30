"""Build one coherent legacy RunSession from request and runtime bindings."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, cast

from gateway.runs.identity import default_agent_ref
from gateway.runs.observability_binding import assemble_run_hub
from gateway.runs.session import RunRegistry, RunSession
from gateway.runs.session_setup_types import RunSessionRequest
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.observability.run_journal import RunJournalFactory


class RunSessionBuilder:
    """Own identity allocation, carrier normalization, and run-local assembly.

    The builder does not register sessions or emit diagnostics. Those are
    lifecycle concerns owned by the setup coordinator and its collaborators.
    """

    def __init__(self, registry: RunRegistry, *, ctx: Any) -> None:
        self._registry = registry
        self._ctx = ctx

    def build(self, request: RunSessionRequest) -> RunSession:
        """Build a journal-enabled session without publishing it to the registry."""
        run_id = new_id("run")
        trace_id = new_id("trace")
        journal_factory = cast(
            "RunJournalFactory", require_capability(self._ctx, "run_ledger_factory")
        )
        components = journal_factory.create_run_components(
            jsonl_path=self._registry.jsonl_path_for(run_id)
        )
        hub = assemble_run_hub(
            jsonl_writer=components.writer,
            tail=components.tail,
            ctx=self._ctx,
            extra_projectors=(self._registry.bind_process_journal(journal_factory),),
        )
        return RunSession(
            run_id=run_id,
            trace_id=trace_id,
            jsonl_path=self._registry.jsonl_path_for(run_id),
            tail=components.tail,
            hub=hub,
            question=request.question,
            user_text=request.user_text,
            mode=request.mode,
            prior_turns=tuple(request.prior_turns),
            attachment_ids=_clean_attachment_ids(request.attachment_ids),
            agent=request.agent if request.agent is not None else default_agent_ref(),
            device_id=request.device_id.strip(),
            plane=request.plane.strip(),
            extra_plane=request.extra_plane.strip(),
            execution_target=request.execution_target.strip(),
            started_at=time.time(),
            locator=self._registry.locator(),
        )


def _clean_attachment_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize attachment carriers at the edge of session construction."""
    return tuple(str(item).strip() for item in values if str(item).strip())


__all__ = ["RunSessionBuilder"]
