"""Run ledger and journal factory seam —— ADR-0065 L9 + ADR-0167 D11。

ADR-0167 D11 简化: spine ``<run_id>.spine.jsonl`` 是 SSOT, journal.json 由
:class:`StepTreeAccumulatorDeriver` 累积 events 后落盘,
journal.narrative.md 由 :class:`NarrativeDeriver` 从同一 events
推导。

职责: profile-selected factory 装配每个 run 的:
  - LiveTail (SSE 投影)
  - RunJournalComponents(step_tree_writer 现在是 ``_StepTreeBundle``)
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
    """Profile-selected durable ledgers + per-run journal projections."""

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

    def create_run_components(
        self,
        *,
        spine_path: Path,
    ) -> RunJournalComponents:
        """Create the live tail for one resolved run path.

        ADR-0167 D11: 删除 StepGroupedBackend 适配。journal.json 由
        ``StepTreeAccumulatorDeriver``(已 subscribe 到 spine)落盘,
        narrative.md 由 ``NarrativeDeriver`` 落盘。 factory 只提供
        LiveTail(SSE 投影)+ step_tree_writer bundle 引用。
        """
        from lca.infrastructure.observability.journal.step.narrative_writer import (
            StepNarrativeWriter,
        )
        from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

        spine_path.parent.mkdir(parents=True, exist_ok=True)

        narrative_writer = StepNarrativeWriter(spine_path.parent / "journal.narrative.md")

        # step_tree_writer 是 _StepTreeBundle 的 placeholder —— deriver 与
        # narrative_writer 由 transport 在 RunSessionBuilder.build 阶段
        # 真正构造 + subscribe, 然后 session.step_tree_bundle 持有。
        return RunJournalComponents(
            writer=LiveTail(),
            tail=LiveTail(),
            step_tree_writer=_StepTreeBundle(
                deriver=None,
                narrative_writer=narrative_writer,
            ),
        )

    def create_process_journal(self) -> ProcessJournalProjection:
        """Create the process-wide live projection owned by the run registry."""
        from lca.infrastructure.observability.journal.engine.process import ProcessJournal

        return ProcessJournal()


@dataclass(frozen=True)
class _StepTreeBundle:
    """ADR-0167 D11 简化: bundle 只持 deriver + narrative_writer。

    flush() 调用顺序(都 idempotent):
      1. ``deriver.flush()`` —— 写 journal.json(累积 events → JournalDocument)
      2. ``deriver.document`` —— 拿到 closed JournalDocument
      3. ``narrative_writer.write(document)`` —— 写 journal.narrative.md

    失败语义: deriver 内部 try/except 兜底, 不抛到 bundle 这一层;
    bundle.flush() 仅在 narrative_writer.write() 异常时抛。
    """

    deriver: object | None  # StepTreeAccumulatorDeriver
    narrative_writer: object  # StepNarrativeWriter

    def flush(self, *, outcome: str = "stopped") -> None:
        """写 journal.json + narrative.md。"""
        if self.deriver is None:
            return
        self.deriver.flush()
        document = getattr(self.deriver, "document", None)
        if document is not None and hasattr(self.narrative_writer, "write"):
            self.narrative_writer.write(document)


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
    """Provide filesystem RunLedger + RunJournalFactory."""
    root = Path(config.root)
    root.mkdir(parents=True, exist_ok=True)
    factory = FilesystemRunLedgerFactory(root=root, fsync_each_append=config.fsync_each_append)
    ctx.provide(RUN_LEDGER_FACTORY.key, factory)


__all__ = [
    "Config",
    "FilesystemRunLedgerFactory",
    "_StepTreeBundle",
    "setup",
]
