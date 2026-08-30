"""Run ledger and journal factory seam —— ADR-0065 L9.

The factory is the profile-selected entry point for both durable ledgers and
run-scoped journal projections.  Gateway supplies only a path already resolved
by ``RunLocator``; it no longer selects JSONL writers, live tails, or the
process-wide projection implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import RUN_LEDGER_FACTORY
from lca.contracts.observability.ledger import RunLedger, RunLedgerFactory
from lca.contracts.observability.run_journal import (
    ProcessJournalProjection,
    RunJournalComponents,
    RunJournalFactory,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = "traces/runs"
    fsync_each_append: bool = True


class FilesystemRunLedgerFactory(RunLedgerFactory, RunJournalFactory):
    """Create profile-selected durable ledgers and journal projections.

    ``create`` is the low-level ledger path used by replay and diagnostic
    callers.  ``create_run_components`` is the production run path: it keeps
    the existing journal-v2 writer format while centralizing all projection
    construction behind the same profile-selected factory.
    """

    def __init__(self, root: Path, *, fsync_each_append: bool) -> None:
        self._root = root
        self._fsync_each_append = fsync_each_append

    def create(self, *, run_id: str = "") -> RunLedger:
        from lca.infrastructure.observability.journal.backends.filesystem import (
            FilesystemJournalStore,
        )
        from lca.infrastructure.observability.journal.engine.engine import RunStore

        safe_run_id = run_id.strip() or "unbound"
        if Path(safe_run_id).name != safe_run_id:
            raise ValueError("run_id must be a single path component")
        backend = FilesystemJournalStore(
            self._root / safe_run_id,
            fsync_each_append=self._fsync_each_append,
        )
        return cast("RunLedger", RunStore(backend=backend, run_id=safe_run_id))

    def create_run_components(self, *, jsonl_path: Path) -> RunJournalComponents:
        """Create the durable writer and live tail for one resolved run path."""
        from lca.infrastructure.observability.journal.jsonl.projector import (
            JsonlJournalProjector,
        )
        from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        return RunJournalComponents(
            writer=JsonlJournalProjector(jsonl_path),
            tail=LiveTail(),
        )

    def create_process_journal(self) -> ProcessJournalProjection:
        """Create the process-wide live projection owned by the run registry."""
        from lca.infrastructure.observability.journal.engine.process import ProcessJournal

        return ProcessJournal()


@plugin(
    id="lca-run-ledger-factory-seam",
    provides=[RUN_LEDGER_FACTORY.key],
    requires=[],
    implements=[RunLedgerFactory, RunJournalFactory],
    layer="L0",
    effects="filesystem",
    description=(
        "Provide durable run ledgers and profile-selected run journal projections "
        "(writer, live tail, process projection; ADR-0065 L9)."
    ),
    test_suite="tests/test_run_ledger_factory.py",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Mount the profile-selected run ledger and journal factory."""
    ctx.provide(
        RUN_LEDGER_FACTORY.key,
        FilesystemRunLedgerFactory(
            Path(config.root),
            fsync_each_append=config.fsync_each_append,
        ),
    )


__all__ = ["Config", "FilesystemRunLedgerFactory", "setup"]
