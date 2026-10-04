"""Execute a due CronJob and return its report (ADR-0268 §3.4).

The worker does not deliver. It resolves the job behind the assembled context
text, runs it, and hands back a ``worker_message``. Runtime wraps that into a
:class:`~lca.contracts.models.cron.models.ScheduledHandoff` and injects it into
a parent turn, and the parent's own reply is the visible bubble (ADR-0268 §6,
§12). Receipts therefore stay empty here: empty means the handoff turn still
owes a delivery decision.
"""

from __future__ import annotations

import logging
import re

from lca.contracts.models.cron.models import CronJob, TargetReceipt
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import CronWorkerResult

_log = logging.getLogger(__name__)

_JOB_ID_RE = re.compile(r"- job_id:\s*([^\s\n]+)")

#: Returned when the worker cannot resolve a job at all, so no parent turn will
#: ever exist to close the receipts. ``chat_id=None`` matches the scheduler's
#: ``superseded`` record, the other case with no parent turn.
_UNRESOLVED = CronWorkerResult(
    outcome="runtime_failure",
    receipts=(TargetReceipt(chat_id=None, state="not_sent"),),
)

_NO_PARENT_TURN = (TargetReceipt(chat_id=None, state="not_sent"),)


class CronWorkerRunner:
    """Runs one due CronJob occurrence and reports what it produced."""

    def __init__(self, *, store: CronStore) -> None:
        self._store = store

    async def __call__(self, arg: CronJob | str) -> CronWorkerResult:
        """Accept a CronJob directly, or the assembled context text from the scheduler."""
        if isinstance(arg, CronJob):
            return await self.execute_job(arg)

        match = _JOB_ID_RE.search(arg)
        if not match:
            _log.warning("cron.worker_runner: cannot extract job_id from text")
            return _UNRESOLVED
        job_id = match.group(1).strip()
        job = self._store.get_job(job_id)
        if job is None:
            _log.warning("cron.worker_runner: job %s not found in store", job_id)
            return _UNRESOLVED
        return await self.execute_job(job)

    async def execute_job(self, job: CronJob) -> CronWorkerResult:
        if job.execution.kind == "space_action":
            # ADR-0268 §6: a successful space_action updates an artifact and
            # produces no handoff, so its receipt is written at append time.
            return CronWorkerResult(outcome="completed", receipts=_NO_PARENT_TURN)

        # No agent runner is wired yet, so the job's own body is the report.
        # A reminder's body already is the text the parent has to decide on.
        return CronWorkerResult(outcome="completed", worker_message=job.body)
