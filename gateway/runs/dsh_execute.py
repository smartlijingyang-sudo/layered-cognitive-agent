"""Gateway adapter: DSH driver on the same machine plane as use-computer."""

from __future__ import annotations

import structlog

from gateway.runs.session import RunSession
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.computer.machine import MachineTransport
from lca.layer0_infra.dsh.machine_runtime import MachineDshRuntime
from lca.layer0_infra.dsh.run import run_dsh_machine_turn
from lca.layer0_infra.dsh.runtime import DshUnavailableError
from lca.layer0_infra.dsh.settings import DshSettings
from lca.layer0_infra.plane.machine import resolve_machine_transport
from lca.layer0_infra.plane.resolve import ref_of

_log = structlog.get_logger(__name__)


def default_runtime(
    settings: DshSettings,
    *,
    transport: MachineTransport,
    machine: PlaneRef,
) -> DshRuntime:
    """DSH runs on the machine — SDK lives in sandbox-user's environment."""
    return MachineDshRuntime(transport, machine, settings)


async def execute_dsh_session(session: RunSession) -> None:
    """Replace Agent/Team loop only — caller owns staging, scopes, finalize."""
    bindings = session.bindings
    if bindings is None:
        session.error = "plane bindings missing for DSH"
        return
    machine = ref_of(bindings, PlaneKind.MACHINE)
    if machine is None:
        session.error = "用 DSH 需要本机执行面（sandbox-user sidecar 在线）"
        return
    transport = resolve_machine_transport(machine.id)
    if transport is None:
        session.error = f"machine {machine.label} offline; cannot run DSH"
        return

    settings = DshSettings()
    try:
        result = await run_dsh_machine_turn(
            run_id=session.run_id,
            question=session.question,
            prior_turns=session.prior_turns,
            machine=machine,
            transport=transport,
            runs_dir=session.jsonl_path.parent,
            attachment_ids=session.attachment_ids,
            runtime=default_runtime(settings, transport=transport, machine=machine),
            settings=settings,
        )
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
