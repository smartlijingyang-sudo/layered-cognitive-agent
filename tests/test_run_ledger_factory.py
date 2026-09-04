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


def _install_observability_seams(services: dict[str, object]) -> None:
    """Bind ObservabilityRuntime seam registries for stub ctx."""
    from lca.infrastructure.observability import NamedRegistry
    from lca.infrastructure.observability.loop_cursor.close_barrier_impl import (
        StdCloseBarrier,
    )
    from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
    from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
        NullPersistenceCoordinator,
    )
    from lca.infrastructure.observability.loop_cursor.projection_host import (
        StdProjectionHost,
    )

    loop_cursor = NamedRegistry()
    projection_host = NamedRegistry()
    close_barrier = NamedRegistry()
    persistence = NamedRegistry()
    loop_cursor.register("standard", LoopCursorFactory.from_profile)
    projection_host.register(
        "standard", lambda initial=None, **_: StdProjectionHost(initial=initial)
    )
    close_barrier.register(
        "standard",
        lambda persistence, host, close_emitter, **_: StdCloseBarrier(
            persistence=persistence, host=host, close_emitter=close_emitter
        ),
    )
    persistence.register("null", lambda **_: NullPersistenceCoordinator())
    services["observability.loop_cursor"] = loop_cursor
    services["observability.projection_host"] = projection_host
    services["observability.close_barrier"] = close_barrier
    services["observability.persistence"] = persistence


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
            spine_path: Path,
        ) -> RunJournalComponents:
            self.paths.append(spine_path)
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
            # event_spine stub:cursor 仍经 SpineWritePortAdapter 写 spine;
            # step_tree 走 fold,不再 subscribe。
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
            _install_observability_seams(self._services)

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
    assert factory.paths == [first.spine_path, second.spine_path]
    assert first.tail is factory.tails[0]
    assert second.tail is factory.tails[1]
    assert factory.process_creations == 1
    assert registry.journal is factory.process
    assert registry.live_totals()["journal_subscribers"] == 0

    # 每 run 独立的 StepCoordinator + 独立的 StepTreeFoldDeriver
    assert first.coordinator is not None
    assert second.coordinator is not None
    assert first.coordinator is not second.coordinator
    assert first.coordinator.run_id == first.run_id
    assert second.coordinator.run_id == second.run_id
    from lca.plugins.session.derivers.step_tree import StepTreeFoldDeriver

    assert isinstance(first.thread_tree_writer, StepTreeFoldDeriver)
    assert isinstance(second.thread_tree_writer, StepTreeFoldDeriver)
    assert first.thread_tree_writer is not second.thread_tree_writer


def test_session_step_tree_bundle_is_wired_for_terminalizer_flush(tmp_path: Path) -> None:
    """Regression: ``RunSession.step_tree_bundle`` must be the bundle that owns
    ``StepTreeFoldDeriver.flush()``.

    Without this, ``materialization._flush_step_tree`` early-returns on
    ``bundle is None`` and ``journal.json`` never gets written.

    ADR-0167 D11 / ADR-0186 PR-3g: terminalize flushes via
    ``session.step_tree_bundle.flush()``; the bundle is constructed by the
    factory and ``RunSessionBuilder.build`` must propagate it into the session.
    """

    class _BundleSpyFactory:
        def __init__(self) -> None:
            self.process = ProcessJournal()
            self.bundles_passed: list[object] = []

        def create_run_components(self, *, spine_path: Path) -> RunJournalComponents:
            # factory 真实给 _StepTreeBundle(dataclass frozen); spy 用
            # 一个同形 dataclass 让 builder._dc_replace 能跑。
            from dataclasses import dataclass as _dc

            @_dc(frozen=True)
            class _StubBundle:
                deriver: object | None = None
                narrative_writer: object | None = None

            bundle = _StubBundle(narrative_writer=object())
            self.bundles_passed.append(bundle)
            return RunJournalComponents(
                writer=LiveTail(),
                tail=LiveTail(),
                step_tree_writer=bundle,  # type: ignore[arg-type]
            )

        def create_process_journal(self) -> ProcessJournal:
            return self.process

    class _Ctx:
        def __init__(self, factory: _BundleSpyFactory, wfr: WritableFaceRegistry) -> None:
            class _StubSpine:
                def subscribe(self, fn: object) -> object:
                    del fn
                    return lambda: None

                def close(self) -> None: ...

            self._services = {
                "observability": BoundObservability(journal=MemoryJournal()),
                "run_ledger_factory": factory,
                "writable_face_registry": wfr,
                "event_spine": _StubSpine(),
            }
            _install_observability_seams(self._services)

        def inject(self, key: str, *, default: object = ...) -> object:
            if key in self._services:
                return self._services[key]
            if default is not ...:
                return default
            raise KeyError(key)

    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))
    session = create_run_session(
        registry,
        question="q",
        user_text="u",
        ctx=_Ctx(_BundleSpyFactory(), WritableFaceRegistry()),
    )

    # session.step_tree_bundle 必须是 factory 给的那个 bundle —— 否则
    # materialization._flush_step_tree 的 ``bundle = getattr(session, ...)``
    # 拿 None 早退,deriver 永不 flush,journal.json 永不写。
    assert session.step_tree_bundle is not None, (
        "session.step_tree_bundle must be wired by RunSessionBuilder; "
        "otherwise materialization._flush_step_tree early-returns and "
        "StepTreeFoldDeriver.flush() never produces journal.json"
    )
