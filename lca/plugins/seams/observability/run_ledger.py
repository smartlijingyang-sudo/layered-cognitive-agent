"""Run ledger and journal factory seam —— ADR-0065 L9.

The factory is the profile-selected entry point for both durable ledgers and
run-scoped journal projections.  Gateway supplies only a path already resolved
by ``RunLocator``; it no longer selects JSONL writers, live tails, or the
process-wide projection implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import RUN_LEDGER_FACTORY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.ledger import RunLedger, RunLedgerFactory
from lca.contracts.observability.run_journal import (
    ProcessJournalProjection,
    RunJournalComponents,
    RunJournalFactory,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
        """Create the durable writer and live tail for one resolved run path.

        ADR-0164 Phase 7 端到端:
            - 不再创建 JsonlJournalProjector(主路径不再写 jsonl stream)
            - jsonl_path 仍被 rename 到 ``journal.raw.jsonl``(旧 run 数据保留)
            - step-tree backend 写到 ``journal.json`` (lca.journal/3)
            - narrative writer 写到 ``journal.narrative.md``(terminalize 时)
            - RunJournalComponents.writer 改成 LiveTail( SSE 投影需要 JournalProjector)
        """
        from lca.infrastructure.observability.journal.step.backend import (
            StepGroupedBackend,
        )
        from lca.infrastructure.observability.journal.step.narrative_writer import (
            StepNarrativeWriter,
        )
        from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
        from lca.runtime import step_lifecycle

        # 旧 jsonl 文件 rename 到 journal.raw.jsonl(回放兜底, 不删)
        raw_path = jsonl_path.with_name("journal.raw.jsonl")
        if jsonl_path.exists() and not raw_path.exists():
            jsonl_path.rename(raw_path)
        raw_path.parent.mkdir(parents=True, exist_ok=True)

        # step-tree 主存储
        step_tree_backend: StepGroupedBackend | None = None
        lifecycle_store = step_lifecycle.get_lifecycle_store()
        if lifecycle_store is not None:
            journal_step_path = raw_path.parent / "journal.json"
            step_tree_backend = StepGroupedBackend(
                output_path=journal_step_path,
                lifecycle_store=lifecycle_store,
            )

        narrative_writer = StepNarrativeWriter(raw_path.parent / "journal.narrative.md")

        return RunJournalComponents(
            writer=LiveTail(),  # 仍需 JournalProjector 占位;SSE 投影消费
            tail=LiveTail(),
            step_tree_writer=_StepTreeBundle(
                backend=step_tree_backend,
                narrative_writer=narrative_writer,
            ),
        )

    def create_process_journal(self) -> ProcessJournalProjection:
        """Create the process-wide live projection owned by the run registry."""
        from lca.infrastructure.observability.journal.engine.process import ProcessJournal

        return ProcessJournal()


@dataclass(frozen=True)
class _StepTreeBundle:
    """ADR-0164 step-tree 写入 bundle(boot 装好, terminalizer 时调用)。"""

    backend: object | None  # StepGroupedBackend | None
    narrative_writer: object  # StepNarrativeWriter

    def flush(self) -> None:
        """写 step-tree journal.json + narrative.md。"""
        if self.backend is not None and hasattr(self.backend, "flush"):
            self.backend.flush()


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
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-run-ledger-factory-seam.checked",
                "lca-run-ledger-factory-seam.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
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
