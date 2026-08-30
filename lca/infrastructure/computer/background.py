"""Run-scoped background command registry (Manus / LobeHub runCommand background)."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from lca.contracts.atoms.ids import new_id


@dataclass
class BackgroundCommandRecord:
    command_id: str
    command: str
    running: bool = True


@dataclass
class BackgroundCommandRegistry:
    commands: dict[str, BackgroundCommandRecord] = field(default_factory=dict)

    def register(self, *, command: str, command_id: str | None = None) -> str:
        cid = command_id or new_id("cmd")
        self.commands[cid] = BackgroundCommandRecord(command_id=cid, command=command)
        return cid

    def get(self, command_id: str) -> BackgroundCommandRecord | None:
        return self.commands.get(command_id)

    def mark_stopped(self, command_id: str) -> None:
        rec = self.commands.get(command_id)
        if rec is not None:
            rec.running = False


_registry_var: contextvars.ContextVar[BackgroundCommandRegistry | None] = contextvars.ContextVar(
    "lca_background_cmd_registry", default=None
)


def get_background_registry() -> BackgroundCommandRegistry:
    reg = _registry_var.get()
    if reg is None:
        reg = BackgroundCommandRegistry()
        _registry_var.set(reg)
    return reg
