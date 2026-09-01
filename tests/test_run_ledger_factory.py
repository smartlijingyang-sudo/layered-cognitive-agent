from __future__ import annotations

import asyncio
from pathlib import Path

from lca.contracts.observability.ledger import RunLedgerFactory
from lca.contracts.observability.run_journal import RunJournalFactory
from lca.harness.profile.boot import boot_profile
from lca.plugins.seams.observability.run_ledger import (
    FilesystemRunLedgerFactory,
)


def test_factory_creates_isolated_ledger(tmp_path: Path) -> None:
    factory = FilesystemRunLedgerFactory(tmp_path / "runs", fsync_each_append=True)

    first = factory.create(run_id="run-a")
    second = factory.create(run_id="run-b")

    assert isinstance(factory, RunLedgerFactory)
    assert first.run_id == "run-a"
    assert second.run_id == "run-b"
    assert first.run_id != second.run_id
    assert (tmp_path / "runs" / "run-a").is_dir()
    assert (tmp_path / "runs" / "run-b").is_dir()

    first.close()
    second.close()


def test_factory_rejects_path_traversal(tmp_path: Path) -> None:
    factory = FilesystemRunLedgerFactory(tmp_path / "runs", fsync_each_append=True)

    try:
        factory.create(run_id="../escape")
    except ValueError as error:
        assert "single path component" in str(error)
    else:
        raise AssertionError("path traversal run_id must be rejected")


def test_default_profile_exposes_ledger_factory() -> None:
    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))

    factory = ctx.inject("run_ledger_factory")

    assert isinstance(factory, RunLedgerFactory)
    assert isinstance(factory, RunJournalFactory)


def test_run_session_consumes_profile_selected_journal_factory(tmp_path: Path) -> None:
    """Gateway must not select journal writer, tail, or process projection itself."""
    from lca.contracts.observability.run_journal import RunJournalComponents
    from lca.infrastructure.observability.backends.journal_backend import MemoryJournal
    from lca.infrastructure.observability.backends.run_locator_fs import FilesystemRunLocator
    from lca.infrastructure.observability.facade import BoundObservability
    from lca.infrastructure.observability.journal.engine.process import ProcessJournal
    from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
    from lca.plugins.transport.webserver.handlers.runs.execute import create_run_session
    from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry

    class _SpyFactory:
        def __init__(self) -> None:
            self.paths: list[Path] = []
            self.process_creations = 0
            self.process = ProcessJournal()
            self.tails: list[LiveTail] = []

        def create_run_components(self, *, jsonl_path: Path) -> RunJournalComponents:
            self.paths.append(jsonl_path)
            tail = LiveTail()
            self.tails.append(tail)
            # ADR-0164 Phase 7: 不再创建 JsonlJournalProjector(主路径不写 jsonl)
            # writer 字段需 JournalProjector, LiveTail 占位(SSE 投影)。
            return RunJournalComponents(
                writer=LiveTail(),
                tail=tail,
            )

        def create_process_journal(self) -> ProcessJournal:
            self.process_creations += 1
            return self.process

    class _Context:
        entries: tuple[object, ...] = ()

        def __init__(self, factory: _SpyFactory) -> None:
            self._services = {
                "observability": BoundObservability(journal=MemoryJournal()),
                "run_ledger_factory": factory,
            }

        def inject(self, key: str, *, default: object = ...) -> object:
            if key in self._services:
                return self._services[key]
            if default is not ...:
                return default
            raise KeyError(key)

    factory = _SpyFactory()
    ctx = _Context(factory)
    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))

    first = create_run_session(registry, question="first", user_text="first", ctx=ctx)
    second = create_run_session(registry, question="second", user_text="second", ctx=ctx)

    assert factory.paths == [first.jsonl_path, second.jsonl_path]
    assert first.tail is factory.tails[0]
    assert second.tail is factory.tails[1]
    assert factory.process_creations == 1
    assert registry.journal is factory.process
    assert registry.live_totals()["journal_subscribers"] == 0
