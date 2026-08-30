"""Run one DSH turn on the machine plane — driver + harvest, no gateway types."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import structlog

from lca.contracts.models.core.conversation import ConversationTurn
from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols import DshRuntime
from lca.infrastructure.comparison.dsh_driver.archive import JsonlEventArchive
from lca.infrastructure.comparison.dsh_driver.driver import DshTurnDriver, DshTurnSpec
from lca.infrastructure.comparison.dsh_driver.harvest import (
    harvest_machine_outputs,
    record_dsh_harvest,
)
from lca.infrastructure.comparison.dsh_driver.launch import build_harness_env
from lca.infrastructure.comparison.dsh_driver.machine_runtime import MachineDshRuntime
from lca.infrastructure.comparison.dsh_driver.models import DshTurnResult
from lca.infrastructure.comparison.dsh_driver.projector import DshJournalProjector
from lca.infrastructure.comparison.dsh_driver.prompt import compose_dsh_prompt
from lca.infrastructure.comparison.dsh_driver.runtime import DshUnavailableError
from lca.infrastructure.comparison.dsh_driver.settings import DshSettings
from lca.infrastructure.comparison.dsh_driver.sink import HandleJournalSink
from lca.infrastructure.computer.machine import MachineTransport
from lca.infrastructure.file_store import FileStore, LocalFileStore

_log = structlog.get_logger(__name__)


def resolve_dsh_cwd(machine: PlaneRef, settings: DshSettings | None = None) -> str:
    """DSH ``cwd`` matches machine tools — ``DSH_CWD`` is dev-only override."""
    cfg = settings if settings is not None else DshSettings()
    override = cfg.cwd.strip()
    if override:
        return override
    root = (machine.root or "").strip()
    if root:
        return root
    raise DshUnavailableError("用 DSH 需要本机工作根（sidecar 在线或 DSH_CWD）")


async def run_dsh_machine_turn(
    *,
    run_id: str,
    question: str,
    prior_turns: Sequence[ConversationTurn],
    machine: PlaneRef,
    transport: MachineTransport,
    runs_dir: Path,
    attachment_ids: Sequence[str] = (),
    store: FileStore | None = None,
    runtime: DshRuntime | None = None,
    settings: DshSettings | None = None,
    projector: DshJournalProjector | None = None,
    archive: JsonlEventArchive | None = None,
) -> DshTurnResult:
    """Drive DSH on ``machine`` and harvest ``outputs_dir`` like ``MachineComputer``.

    ``projector`` and ``archive`` are optional: callers that own the DSH
    session lifecycle (e.g. ``execute_dsh_session``) pass them in so they
    can manage finish/error semantics.  When omitted, this function creates
    them internally (backward-compat for tests and standalone callers).
    """
    cfg = settings if settings is not None else DshSettings()
    cwd = resolve_dsh_cwd(machine, cfg)
    active_store = store if store is not None else LocalFileStore()
    prompt = compose_dsh_prompt(question, prior_turns)
    harness_env = build_harness_env(
        machine,
        run_id=run_id,
        session_root=runs_dir,
        settings=cfg,
        attachment_ids=attachment_ids,
        store=active_store,
    )

    effective_projector = (
        projector if projector is not None else DshJournalProjector(HandleJournalSink())
    )
    effective_archive = (
        archive if archive is not None else JsonlEventArchive(runs_dir / f"{run_id}.dsh.jsonl")
    )
    driver = DshTurnDriver(
        runtime=runtime if runtime is not None else MachineDshRuntime(transport, machine, cfg),
        projector=effective_projector,
        archive=effective_archive,
    )
    spec = DshTurnSpec(
        prompt=prompt,
        session_id=run_id,
        cwd=cwd,
        session_root=str(runs_dir),
        harness_env=harness_env,
    )
    result = await driver.run_async(spec)
    try:
        parts = await harvest_machine_outputs(
            machine=machine,
            transport=transport,
            store=active_store,
        )
        await record_dsh_harvest(parts)
    except Exception:
        _log.warning("dsh_harvest_failed", run_id=run_id, exc_info=True)
    return result
