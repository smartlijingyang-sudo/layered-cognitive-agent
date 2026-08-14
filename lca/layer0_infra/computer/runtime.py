"""ComputerRuntime — backward-compatible alias for SandboxComputer."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.computer.op_result import ComputerOpResult, TerminalCapableSandbox
from lca.layer0_infra.computer.sandbox_computer import SandboxComputer, normalize_sandbox_path
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.plane.resolve import sandbox_ref_from

__all__ = [
    "ComputerOpResult",
    "ComputerRuntime",
    "TerminalCapableSandbox",
    "normalize_sandbox_path",
]


class ComputerRuntime(SandboxComputer):
    """Backward-compatible constructor — plane inferred from sandbox when omitted."""

    def __init__(
        self,
        *,
        sandbox: Sandbox,
        store: FileStore,
        plane: PlaneRef | None = None,
    ) -> None:
        super().__init__(
            plane=plane or sandbox_ref_from(sandbox),
            sandbox=sandbox,
            store=store,
        )
