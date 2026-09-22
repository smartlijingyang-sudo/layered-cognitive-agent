"""MachineLocalExecAdapter — 将 MachineComputer 适配为 LocalExecPort (ADR-0246 M1)。

职责：Grant 校验（过期、路径越界）→ 调用 MachineComputer → 包装为 EffectReceipt。
"""

from __future__ import annotations

import hashlib
import posixpath
import time
from typing import Any

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    LocalExecTarget,
    TargetKind,
    access_scope_of,
)
from lca.infrastructure.computer.machine.machine import MachineComputer


class MachineLocalExecAdapter:
    def __init__(self, computer: MachineComputer, *, machine_id: str, label: str) -> None:
        self._computer = computer
        self._machine_id = machine_id
        self._label = label

    @property
    def target(self) -> LocalExecTarget:
        return LocalExecTarget(
            kind=TargetKind.USER_MACHINE,
            id=self._machine_id,
            label=self._label,
            capability_summary=["read_file", "write_file", "run_command", "git"],
        )

    async def execute(
        self, operation: str, args: dict[str, Any], grant: CapabilityGrant
    ) -> EffectReceipt:
        base = {
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
        orig_scope = getattr(self._computer, "_scope", None)
        try:
            if hasattr(self._computer, "_scope") and grant:
                self._computer._scope = access_scope_of(grant)
            result = await self._dispatch(operation, args)
        except ConnectionError:
            return EffectReceipt(
                **base,
                success=False,
                exit_code=None,
                error_kind="device_offline",
                stdout_digest=None,
            )
        finally:
            if hasattr(self._computer, "_scope") and orig_scope is not None:
                self._computer._scope = orig_scope
        digest = (
            "sha256-" + hashlib.sha256(result.content.encode()).hexdigest()[:16]
            if result.content
            else None
        )
        if not result.success:
            is_offline = "offline" in (result.error or "").lower()
            return EffectReceipt(
                **base,
                success=False,
                exit_code=1,
                error_kind="device_offline" if is_offline else "execution_error",
                stdout_digest=digest,
            )
        return EffectReceipt(
            **base,
            success=True,
            exit_code=0,
            error_kind=None,
            stdout_digest=digest,
        )

    async def _dispatch(self, operation: str, args: dict[str, Any]):
        _map = {
            "read_file": lambda: self._computer.read_file(path=args.get("path", "")),
            "write_file": lambda: self._computer.write_file(
                path=args.get("path", ""), content=args.get("content", "")
            ),
            "run_command": lambda: self._computer.run_command(
                command=args.get("command", ""), timeout_s=args.get("timeout_s", 60)
            ),
            "list_files": lambda: self._computer.list_files(
                directory_path=args.get("directory", "")
            ),
        }
        fn = _map.get(operation)
        if fn is None:
            from lca.infrastructure.computer.op.result import ComputerOpResult

            return ComputerOpResult(
                success=False,
                content=f"unknown: {operation}",
                state={},
                error="unknown",
            )
        return await fn()


__all__ = ["MachineLocalExecAdapter"]
