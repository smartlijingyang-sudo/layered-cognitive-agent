"""FilesystemRunLedgerFactory tests (ADR-0167 D11)。

覆盖:
- default profile exposes ledger factory + journal factory
- RunSessionBuilder 不选 journal writer/tail 自己, 而用 factory
- 两次 create_run_session 拿到不同 run_id, 共享 process journal
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lca.contracts.observability.ledger import RunLedgerFactory
from lca.contracts.observability.run_journal import (
    RunJournalComponents,
    RunJournalFactory,
)
from lca.harness.profile.boot import boot_profile
from lca.infrastructure.observability.backends.journal_backend import MemoryJournal
from lca.infrastructure.observability.backends.run_locator_fs import (
    FilesystemRunLocator,
)
from lca.infrastructure.observability.facade import BoundObservability
from lca.infrastructure.observability.journal.engine.process import ProcessJournal
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)
from lca.plugins.transport.webserver.handlers.runs.execute import (
    create_run_session,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry


def test_default_profile_exposes_ledger_factory() -> None:
    ctx = asyncio.run(boot_profile("profiles/web-standard.yaml"))

    factory = ctx.inject("run_ledger_factory")

    assert isinstance(factory, RunLedgerFactory)
    assert isinstance(factory, RunJournalFactory)


def test_run_session_consumes_profile_selected_journal_factory(tmp_path: Path) -> None:
    """Gateway 必须用 factory 选 writer / tail, 不自己构造 (ADR-0167 D11)。

    本测试不需要 boot 真实 profile,只验证 ``RunSessionBuilder`` 在
    factory + writable_face_registry 都 bind 的 ctx 下能正确生成 session。
    """

    class _SpyFactory:
        def __init__(self) -> None:
            self.paths: list[Path] = []
            self.process_creations = 0
            self.process = ProcessJournal()
            self.tails: list[LiveTail] = []

        def create_run_components(
            self,
            *,
            jsonl_path: Path,
        ) -> RunJournalComponents:
            self.paths.append(jsonl_path)
            tail = LiveTail()
            self.tails.append(tail)
            return RunJournalComponents(
                writer=LiveTail(),
                tail=tail,
                step_tree_writer=None,
            )

        def create_process_journal(self) -> ProcessJournal:
            self.process_creations += 1
            return self.process

    class _Context:
        def __init__(self, factory: _SpyFactory, registry_obj: WritableFaceRegistry) -> None:
            # event_spine 提供一个 stub (Mock SpineCore w/ event_spine.subscribe 接受)
            class _StubSpine:
                def subscribe(self, fn: object) -> object:
                    del fn
                    return lambda: None
                def close(self) -> None: ...

            self._services = {
                "observability": BoundObservability(journal=MemoryJournal()),
                "run_ledger_factory": factory,
                "writable_face_registry": registry_obj,
                "event_spine": _StubSpine(),
            }

        def inject(self, key: str, *, default: object = ...) -> object:
            if key in self._services:
                return self._services[key]
            if default is not ...:
                return default
            raise KeyError(key)

    registry_obj = WritableFaceRegistry()
    factory = _SpyFactory()
    ctx = _Context(factory, registry_obj)
    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))

    first = create_run_session(registry, question="first", user_text="first", ctx=ctx)
    second = create_run_session(registry, question="second", user_text="second", ctx=ctx)

    # factory 拿到两条路径 + 两个独立 tail
    assert factory.paths == [first.jsonl_path, second.jsonl_path]
    assert first.tail is factory.tails[0]
    assert second.tail is factory.tails[1]
    assert factory.process_creations == 1
    assert registry.journal is factory.process
    assert registry.live_totals()["journal_subscribers"] == 0

    # 每 run 独立的 StepCoordinator + 独立的 StepTreeAccumulatorderiver
    assert first.coordinator is not None
    assert second.coordinator is not None
    assert first.coordinator is not second.coordinator
    assert first.coordinator.run_id == first.run_id
    assert second.coordinator.run_id == second.run_id
    # deriver 是 None (RunSessionBuilder 不在 spy ctx 中构造 spine deriver;
    # 真实路径由 event_spine.subscribe 注入, 见 test_runtime_journal_binding_integration)
    # 在这个 stub factory 场景下,deriver 不会被 subscribe, journal.json 不会写
    # (符合"真实 wire 由 spine 装配"的设计)。
