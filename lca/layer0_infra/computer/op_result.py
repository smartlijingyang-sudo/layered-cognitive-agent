"""Computer operation result — shared by MachineComputer and SandboxComputer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxExecResult,
    SandboxFile,
)
from lca.contracts.protocols import Sandbox


@runtime_checkable
class TerminalCapableSandbox(Sandbox, Protocol):
    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> Any: ...


@dataclass(frozen=True)
class ComputerOpResult:
    success: bool
    content: str
    state: dict[str, Any]
    error: str = ""
    exec_result: SandboxExecResult | None = None
    generated_files: tuple[SandboxFile, ...] = ()
