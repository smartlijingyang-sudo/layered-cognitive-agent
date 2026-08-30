"""Map ``SandboxResult`` → ``SandboxExecResult`` (L0 — keeps contracts pure)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.sandbox import (
    MountManifest,
    SandboxErrorKind,
    SandboxExecResult,
    SandboxResult,
)


def sandbox_exec_result_from(
    result: SandboxResult,
    *,
    error_kind: SandboxErrorKind = SandboxErrorKind.NONE,
    error_summary: str = "",
    suggested_fix: str = "",
    mount_manifest: MountManifest | None = None,
    environment_ready: bool = False,
    partial: bool = False,
    failed_at_line: int | None = None,
    inspect_profile: dict[str, Any] | None = None,
) -> SandboxExecResult:
    kind = error_kind
    if not result.success and kind == SandboxErrorKind.NONE:
        kind = SandboxErrorKind.INFRA
    summary = error_summary or (result.error if not result.success else "")
    return SandboxExecResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        success=result.success,
        generated_files=result.generated_files,
        error=result.error,
        error_kind=kind,
        error_summary=summary,
        suggested_fix=suggested_fix,
        mount_manifest=mount_manifest or MountManifest(),
        environment_ready=environment_ready,
        partial=partial,
        failed_at_line=failed_at_line,
        inspect_profile=inspect_profile,
    )
