"""FakeCompanionProvider — 测试专用，验证 LocalExecPort 契约 (ADR-0246 M1)。

永不执行真实 I/O。覆盖所有 M1 验收场景：
- offline: fail-loud (I-UMS-1)
- grant_expired: fail-loud (I-UMS-3)
- scope_violation: fail-loud (I-UMS-3)
- idempotent replay: 重复 key 返回原 receipt (I-UMS-6)
- deny: local policy 拒绝
"""

from __future__ import annotations

import posixpath
import time
from typing import Any, Literal

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
)


class FakeCompanionProvider:
    """mode: normal | offline | deny | timeout | cancel"""

    def __init__(
        self,
        *,
        mode: Literal["normal", "offline", "deny", "timeout", "cancel"] = "normal",
        machine_id: str = "m-fake-01",
        label: str = "FakeWindows-PC",
    ) -> None:
        self._mode = mode
        self._machine_id = machine_id
        self._label = label
        self._idem_store: dict[str, EffectReceipt] = {}
        self.execution_count = 0

    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.USER_MACHINE,
            id=self._machine_id,
            label=self._label,
            capability_summary=["read_file", "write_file", "run_command", "git"],
        )

    async def execute(
        self,
        operation: str,
        args: dict[str, Any],
        grant: CapabilityGrant,
    ) -> EffectReceipt:
        idem_key = f"{grant.job_id}:{grant.idempotency_key}"
        if idem_key in self._idem_store:
            return self._idem_store[idem_key]
        receipt = self._run(operation, args, grant)
        # Only cache successful executions for idempotency; offline is retryable
        if receipt.error_kind not in ("device_offline",):
            self._idem_store[idem_key] = receipt
        return receipt

    def _run(
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
        if self._mode == "offline":
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="device_offline",
                stdout_digest=None,
            )
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
        if self._mode == "deny":
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="local_policy_denied",
                stdout_digest=None,
            )
        if self._mode == "timeout":
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="timeout",
                stdout_digest=None,
            )
        if self._mode == "cancel":
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="cancelled",
                stdout_digest=None,
            )
        self.execution_count += 1
        return EffectReceipt(
            **base,
            success=True,
            exit_code=0,
            error_kind=None,
            stdout_digest="sha256-fake",
        )


__all__ = ["FakeCompanionProvider"]
