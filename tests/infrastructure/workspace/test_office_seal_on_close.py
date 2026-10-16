from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.contracts.models.core.execution.sandbox import SandboxFile, SandboxResult
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeclarativeRunOutcome,
    PhaseRunCursor,
)
from lca.contracts.protocols.runtime.infra.infra import Sandbox
from lca.framework.graph.host_wiring import LegacyResultShim
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.sandbox.runtime.runtime import RunBoundSandboxRuntime
from lca.infrastructure.workspace.deliverable import visible_generated_files
from lca.infrastructure.workspace.office_works import seal_office_works
from lca.infrastructure.workspace.scope import run_workspace_scope
from lca.plugins.loop.reducer.plugin import DefaultReducer
from lca.runtime.projection.result_finalizer import RuntimeResultFinalizer

_NOTE = b"PK\x03\x04new"


class _Terminal:
    def __init__(self, *, stdout: str = "", success: bool = False) -> None:
        self.stdout = stdout
        self.success = success


class _Runtime:
    def __init__(
        self,
        store: LocalFileStore,
        files: tuple[SandboxFile, ...],
        *,
        stdout: str = "",
        success: bool = False,
    ) -> None:
        self._store = store
        self._files = files
        self._stdout = stdout
        self._success = success
        self.invocations: list[str] = []
        self.terminal_for: Any = None

    @property
    def store(self) -> LocalFileStore:
        return self._store

    async def flush_office_residents(self, *, timeout_s: int = 30) -> None:
        return None

    async def outputs_changed_since_baseline(
        self, *, invocation_id: str = ""
    ) -> tuple[SandboxFile, ...]:
        self.invocations.append(invocation_id)
        return self._files

    async def scan_output_files(
        self,
        *,
        invocation_id: str = "",
        timeout_s: int | None = None,
    ) -> tuple[SandboxFile, ...]:
        return ()

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = 30,
        invocation_id: str = "",
        harvest_outputs: bool = False,
    ) -> _Terminal:
        if self.terminal_for is not None:
            return self.terminal_for(command)
        return _Terminal(stdout=self._stdout, success=self._success)


class _IdleSandbox:
    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        return SandboxResult()

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return SandboxResult()

    async def create_session(self, config: Any = None) -> None:
        return None

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return SandboxResult()

    async def destroy_session(self, session_id: str) -> None:
        return None

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return SandboxResult()


class _ScanRuntime(RunBoundSandboxRuntime):
    def __init__(self, store: LocalFileStore, run_id: str, files: tuple[SandboxFile, ...]) -> None:
        sandbox: Sandbox = _IdleSandbox()
        super().__init__(sandbox=sandbox, store=store, run_id=run_id)
        self._files = files

    async def scan_output_files(
        self,
        *,
        invocation_id: str = "",
        timeout_s: int | None = None,
    ) -> tuple[SandboxFile, ...]:
        return self._files


class _Hooks:
    async def trigger(self, event_name: str, state: AgentState) -> None:
        return None


class _ArtifactClosure:
    def synthesize(self) -> str | None:
        return None


class _StateStore:
    async def save(self, state: AgentState) -> str:
        return "state://saved"


def _note() -> SandboxFile:
    return SandboxFile(name="note.docx", mime_type="application/octet-stream", data=_NOTE)


def _bind(monkeypatch: pytest.MonkeyPatch, runtime: _Runtime) -> None:
    monkeypatch.setattr(
        "lca.infrastructure.workspace.office_works.get_sandbox_runtime",
        lambda run_id=None: runtime,
    )


def _cursor() -> PhaseRunCursor:
    return PhaseRunCursor(
        plan_ref="plan-1",
        node_id="think.standard",
        visit_counts=(("think.standard", 1),),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )


@pytest.mark.asyncio
async def test_seal_without_store_ledgers_new_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _Runtime(LocalFileStore(tmp_path), (_note(),))
    _bind(monkeypatch, runtime)
    with run_workspace_scope("run-new-docx") as workspace:
        await seal_office_works()
        artifacts = workspace.artifacts.snapshot().artifacts

    assert runtime.invocations == ["office_works_scan"]
    assert len(artifacts) == 1
    assert artifacts[0].name == "note.docx"
    assert artifacts[0].url.startswith("/files/")
    assert artifacts[0].size_bytes == len(_NOTE)


@pytest.mark.asyncio
async def test_outputs_changed_since_baseline_drops_unchanged_bytes(tmp_path: Path) -> None:
    same = b"same-bytes"
    stale = SandboxFile(name="stale.docx", mime_type="application/octet-stream", data=same)
    fresh = SandboxFile(
        name="fresh.docx",
        mime_type="application/octet-stream",
        data=b"PK\x03\x04fresh",
    )
    edited = SandboxFile(
        name="edited.docx", mime_type="application/octet-stream", data=b"new-bytes"
    )
    runtime = _ScanRuntime(LocalFileStore(tmp_path), "baseline-compare", (stale, fresh, edited))
    runtime._ready = True
    runtime._baseline_captured = True
    runtime._baseline_digests = {
        "stale.docx": sha256_hex(same),
        "edited.docx": sha256_hex(b"old-bytes"),
    }
    changed = await runtime.outputs_changed_since_baseline(invocation_id="office_works_scan")
    names = [item.name for item in changed]
    assert names == ["fresh.docx", "edited.docx"]
    assert "stale.docx" not in names


@pytest.mark.asyncio
async def test_uncaptured_baseline_does_not_publish_history(tmp_path: Path) -> None:
    stale = SandboxFile(name="stale.docx", mime_type="application/octet-stream", data=b"old")
    runtime = _ScanRuntime(LocalFileStore(tmp_path), "baseline-missing", (stale,))
    runtime._ready = True
    changed = await runtime.outputs_changed_since_baseline()
    assert changed == ()


@pytest.mark.asyncio
async def test_second_seal_keeps_one_ledger_row_with_second_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _Runtime(LocalFileStore(tmp_path), (_note(),))
    _bind(monkeypatch, runtime)
    with run_workspace_scope("run-twice") as workspace:
        first = await seal_office_works()
        second = await seal_office_works()
        artifacts = workspace.artifacts.snapshot().artifacts

    assert len(artifacts) == 1
    assert artifacts[0].name == "note.docx"
    assert artifacts[0].url == second[0]["url"]
    assert first[0]["url"] != second[0]["url"]
    assert artifacts[0].url.startswith("/files/")


@pytest.mark.asyncio
async def test_empty_outline_does_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = SandboxFile(
        name="empty.docx", mime_type="application/octet-stream", data=b"PK\x03\x04empty"
    )
    runtime = _Runtime(LocalFileStore(tmp_path), (empty, _note()))

    def terminal_for(command: str) -> _Terminal:
        if "empty.docx" in command:
            return _Terminal(stdout='{"data":{"paragraphs":0}}', success=True)
        return _Terminal(stdout="", success=False)

    runtime.terminal_for = terminal_for
    _bind(monkeypatch, runtime)
    with run_workspace_scope("run-empty") as workspace:
        await seal_office_works()
        names = [item.name for item in workspace.artifacts.snapshot().artifacts]
    assert names == ["note.docx"]


def test_rebind_keeps_the_ledger_closure_will_snapshot() -> None:
    with run_workspace_scope("run-keep") as first:
        first.artifacts.record_file(
            name="note.docx",
            mime_type="application/octet-stream",
            url="/files/file_keep",
            size_bytes=4,
        )
    with run_workspace_scope("run-keep", workspace=first) as second:
        assert second is first
        names = [item.name for item in second.artifacts.snapshot().artifacts]
    assert names == ["note.docx"]


def test_officecli_create_hides_pptx_close_keeps_it() -> None:
    deck = SandboxFile(name="deck.pptx", mime_type="application/octet-stream", data=b"PK")
    created = visible_generated_files((deck,), command="officecli create deck.pptx")
    closed = visible_generated_files((deck,), command="officecli close deck.pptx")
    assert created == ()
    assert tuple(item.name for item in closed) == ("deck.pptx",)


@pytest.mark.asyncio
async def test_finalizer_seals_note_onto_ledger_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _Runtime(LocalFileStore(tmp_path), (_note(),))
    _bind(monkeypatch, runtime)
    cursor = _cursor()
    interpretation = LegacyResultShim(
        state=AgentState(trace_id="trace-seal", task="write the note", budget=Budget()),
        terminal_node="think.standard",
        cursor=cursor,
        outcome=DeclarativeRunOutcome(
            kind=ExecutionOutcome.COMPLETED,
            cursor=cursor,
            stop=StopDecision(reason=StopReason.CONTINUE, final_output="done"),
            approval_request={},
        ),
    )
    finalizer = RuntimeResultFinalizer(
        reducer=DefaultReducer(),
        hooks=_Hooks(),
        artifact_closure=_ArtifactClosure(),
        state_store=_StateStore(),
    )
    with run_workspace_scope("run-close") as workspace:
        await finalizer.finalize(
            interpretation=interpretation,
            plan_ref="plan-1",
            journal_sequence=4,
        )
        artifacts = workspace.artifacts.snapshot().artifacts

    assert len(artifacts) == 1
    assert artifacts[0].name == "note.docx"
    assert artifacts[0].url.startswith("/files/")
