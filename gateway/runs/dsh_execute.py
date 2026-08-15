"""Run a DSH turn inside an existing RunSession / Journal scope."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from gateway.runs.session import RunSession
from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.dsh.archive import JsonlEventArchive
from lca.layer0_infra.dsh.driver import DshTurnDriver, DshTurnSpec
from lca.layer0_infra.dsh.projector import DshJournalProjector
from lca.layer0_infra.dsh.runtime import DshUnavailableError, SdkDshRuntime
from lca.layer0_infra.dsh.settings import DshSettings
from lca.layer0_infra.dsh.sink import FacadeJournalSink
from lca.layer0_infra.plane.resolve import ref_of

_log = structlog.get_logger(__name__)


def default_runtime(settings: DshSettings) -> DshRuntime:
    return SdkDshRuntime(settings)


async def execute_dsh_session(session: RunSession) -> None:
    """Drive ``session`` through DSH. Caller owns run_scope / finalize."""
    settings = DshSettings()
    try:
        cwd = _cwd_for(session, settings)
    except DshUnavailableError as exc:
        session.error = str(exc)
        return

    archive_path = Path(session.jsonl_path).with_name(f"{session.run_id}.dsh.jsonl")
    session_root = str(archive_path.parent)
    driver = DshTurnDriver(
        runtime=default_runtime(settings),
        projector=DshJournalProjector(FacadeJournalSink()),
        archive=JsonlEventArchive(archive_path),
    )
    spec = DshTurnSpec(
        prompt=session.question,
        session_id=session.run_id,
        cwd=cwd,
        session_root=session_root,
    )
    try:
        result = await asyncio.to_thread(driver.run, spec)
    except DshUnavailableError as exc:
        session.error = str(exc)
        _log.warning("dsh_unavailable", run_id=session.run_id, error=str(exc))
        return
    except Exception as exc:
        session.error = f"{type(exc).__name__}: {exc}"
        _log.warning("dsh_turn_failed", run_id=session.run_id, exc_info=True)
        return
    if result.finish_reason not in {None, "completed"}:
        session.error = session.error or (result.finish_reason or "dsh error")


def _cwd_for(session: RunSession, settings: DshSettings) -> str:
    if settings.cwd.strip():
        return settings.cwd.strip()
    bindings = getattr(session, "bindings", None)
    if bindings is not None:
        machine = ref_of(bindings, PlaneKind.MACHINE)
        if machine is not None and machine.root:
            return machine.root
    raise DshUnavailableError("用 DSH 需要本机工作根（sidecar 在线或 DSH_CWD）")
