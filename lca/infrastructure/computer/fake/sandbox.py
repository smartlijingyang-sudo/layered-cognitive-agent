"""FakeSandboxProvider — 替换测试对称用 (ADR-0246 M1).

结构与 FakeCompanionProvider 一致，target.kind = SANDBOX。
确保 Provider 替换不改变 error_kind 形状（替换测试要求）。
"""

from __future__ import annotations

import posixpath
import time
from typing import Any

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)


class FakeSandboxProvider:
    """Sandbox Provider 测试替身，与 FakeCompanionProvider 保持 error_kind 形状一致。"""

    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.SANDBOX,
            id="sandbox-fake-01",
            label="FakeSandbox",
            capability_summary=["read_file", "write_file", "run_command"],
        )

    async def execute(
        self,
        operation: str,
        args: dict[str, Any],
        grant: CapabilityGrant,
    ) -> EffectReceipt:
        base: dict[str, Any] = {
            "job_id": grant.job_id,
            "idempotency_key": grant.idempotency_key,
            "stderr_digest": None,
        }
        if grant.expires_at < int(time.time()):
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="grant_expired",
                stdout_digest=None,
            )
        path = str(args.get("path", args.get("directory", "")))
        if path and grant.path_prefixes:
            norm = posixpath.normpath(path)
            if not any(norm.startswith(posixpath.normpath(p)) for p in grant.path_prefixes):
                return EffectReceipt(
                    **base,
                    success=False,
                    exit_code=None,
                    error_kind="scope_violation",
                    stdout_digest=None,
                )
        return EffectReceipt(
            **base,
            success=True,
            exit_code=0,
            error_kind=None,
            stdout_digest="sha256-sandbox",
        )


__all__ = ["FakeSandboxProvider"]
