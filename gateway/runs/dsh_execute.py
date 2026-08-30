"""Gateway adapter: DSH driver on the same machine plane as use-computer."""

from __future__ import annotations

import structlog

from gateway.device_gateway.bind import device_hub
from gateway.device_gateway.streaming_dsh_runtime import StreamingDshRuntime
from gateway.runs.session import RunSession
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.observability.journal import AgentRunFinished
from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.computer.machine import MachineTransport
from lca.layer0_infra.dsh.archive import JsonlEventArchive
from lca.layer0_infra.dsh.models import DshTurnResult
from lca.layer0_infra.dsh.projector import DshJournalProjector
from lca.layer0_infra.dsh.run import run_dsh_machine_turn
from lca.layer0_infra.dsh.runtime import DshUnavailableError
from lca.layer0_infra.dsh.settings import DshSettings
from lca.layer0_infra.dsh.sink import HandleJournalSink
from lca.layer0_infra.plane.machine import resolve_machine_transport
from lca.layer0_infra.plane.resolve import ref_of

_log = structlog.get_logger(__name__)


def default_runtime(
    settings: DshSettings,
    *,
    transport: MachineTransport,
    machine: PlaneRef,
) -> DshRuntime:
    """DSH on machine: stream notifications via daemon WebSocket when hub is bound."""
    hub = device_hub()
    if hub is not None:
        return StreamingDshRuntime(hub, machine.id, settings)
    from lca.layer0_infra.dsh.machine_runtime import MachineDshRuntime

    return MachineDshRuntime(transport, machine, settings)


async def execute_dsh_session(session: RunSession) -> None:
    """Replace Agent/Team loop only — caller owns staging, scopes, finalize.

    Lifecycle contract: always emit AgentRunStarted + AgentRunFinished so the
    LiveTail/SSE stream has feedback for the frontend, even on early failure.

    终态通过 store.append(AgentRunFinished) 写入，不通过独立状态路径——
    消灭双 owner（ADR-0055 不变量 N3）。
    """
    from lca.layer0_infra.observability.facade import current_bound

    hub = current_bound()  # type: ignore[assignment]
    sink = HandleJournalSink(hub=hub)  # type: ignore[call-arg]
    projector = DshJournalProjector(sink)
    projector.ensure_open()
    # ADR-0065 §七: DSH archive 与 live journal 同目录(都是 run 平面内的 driver 制品)。
    archive = JsonlEventArchive(session.jsonl_path.parent / "dsh.jsonl")
    result: DshTurnResult | None = None

    try:
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
                runs_dir=session.jsonl_path.parent,  # ADR-0065 §七: = <run_id>/
                attachment_ids=session.attachment_ids,
                runtime=default_runtime(settings, transport=transport, machine=machine),
                settings=settings,
                projector=projector,
                archive=archive,
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
        elif not result.final_response:
            session.error = "DSH 返回了空响应，请检查 SDK 配置（API key、模型）和日志"
            _log.warning(
                "dsh_empty_response",
                run_id=session.run_id,
                finish_reason=result.finish_reason,
            )
    finally:
        # 终态通过 sink → store.append 写入（单一 owner）
        _emit_dsh_terminal_event(hub, session, result)


def _emit_dsh_terminal_event(
    hub: object, session: RunSession, result: DshTurnResult | None
) -> None:
    """通过 store.append 写入 AgentRunFinished——唯一终态路径。"""
    if hub is None:
        return
    status = "failed" if session.error else "completed"
    output = result.final_response if result and not session.error else ""
    # 通过 sink 发射（走 store.append 路径）
    sink = HandleJournalSink(hub=hub)  # type: ignore[call-arg]
    sink.emit(
        AgentRunFinished(
            status=status,
            output_text=output,
            error=session.error or "",
        )
    )
