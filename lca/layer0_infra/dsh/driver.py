"""Orchestrate one DSH turn: runtime → archive + journal projection."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols import DshRuntime
from lca.layer0_infra.dsh.models import DshNotification, DshTurnResult
from lca.layer0_infra.dsh.ports import DshEventArchive
from lca.layer0_infra.dsh.projector import DshJournalProjector


@dataclass(frozen=True)
class DshTurnSpec:
    prompt: str
    session_id: str
    cwd: str
    session_root: str
    harness_env: dict[str, str] | None = None


class DshTurnDriver:
    """Template method: notify → persist raw → project → return result."""

    def __init__(
        self,
        runtime: DshRuntime,
        projector: DshJournalProjector,
        archive: DshEventArchive,
    ) -> None:
        self._runtime = runtime
        self._projector = projector
        self._archive = archive

    def run(self, spec: DshTurnSpec) -> DshTurnResult:
        def on_event(notification: DshNotification) -> None:
            self._archive.append(notification)
            self._projector.feed(notification)

        result = self._runtime.run_turn(spec, on_event)
        status = "completed" if result.finish_reason in {None, "completed"} else "failed"
        self._projector.emit_terminal_event(
            status=status,
            output=result.final_response,
            error="" if status == "completed" else (result.finish_reason or "error"),
        )
        return result
