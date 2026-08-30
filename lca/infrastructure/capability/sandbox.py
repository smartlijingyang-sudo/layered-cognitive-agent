"""sandbox seam Definition — owns ctx.sandbox."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.contracts.protocols import Sandbox
from lca.infrastructure.capability.dispatch import ProviderDispatch


class SandboxService(Sandbox):
    """Service Definition for Sandbox. Consumer 调用本对象，不知 Provider。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[Sandbox]("sandbox")

    def register(self, name: str, provider: Sandbox, *, activate: bool = False) -> None:
        self.providers.register(name, provider, activate=activate)

    def current(self) -> Sandbox:
        return self.providers.current()

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = SANDBOX_MOUNT_ROOT,
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        return await self.providers.current().write_files(
            files, base_dir=base_dir, session_id=session_id, timeout_s=timeout_s
        )

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self.providers.current().run(code, language, timeout_s, **kwargs)

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        return await self.providers.current().create_session(config)

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self.providers.current().run_in_session(
            session_id, code, language, timeout_s, **kwargs
        )

    async def destroy_session(self, session_id: str) -> None:
        await self.providers.current().destroy_session(session_id)

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self.providers.current().run_terminal(command, timeout_s=timeout_s, **kwargs)
