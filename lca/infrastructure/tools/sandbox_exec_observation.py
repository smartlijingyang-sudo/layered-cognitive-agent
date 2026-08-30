"""Structured observation builder for sandbox tools (ADR-0050)."""

from __future__ import annotations

import json
import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import (
    SANDBOX_PREVIEW_CHAR_LIMIT,
    SandboxErrorKind,
    SandboxExecResult,
)
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.observability import get_current_run_scope
from lca.infrastructure.tools.sandbox_observation import _stored_part, _truncate_preview
from lca.infrastructure.workspace import get_run_workspace
from lca.infrastructure.workspace.deliverable import is_office_name

_LOG_MIME = "text/plain"

_FAILURE_KIND_BY_ERROR: dict[SandboxErrorKind, str] = {
    SandboxErrorKind.MOUNT: FAILURE_KIND_EXECUTION,
    SandboxErrorKind.USER_CODE: FAILURE_KIND_EXECUTION,
    SandboxErrorKind.TIMEOUT: FAILURE_KIND_EXECUTION,
    SandboxErrorKind.INFRA: FAILURE_KIND_EXECUTION,
}


def build_exec_observation(
    store: FileStore,
    result: SandboxExecResult,
    invocation_id: str,
    start: float,
    *,
    tool_name: str = "sandbox_execute",
) -> Observation:
    """Build a structured Observation from ``SandboxExecResult``."""
    file_parts: list[dict[str, Any]] = []
    for gen in result.generated_files:
        if is_office_name(gen.name):
            continue
        file_parts.append(_stored_part(store, gen.data, gen.name, gen.mime_type))
    for label, body in (("stdout", result.stdout), ("stderr", result.stderr)):
        if len(body) > SANDBOX_PREVIEW_CHAR_LIMIT:
            file_parts.append(
                _stored_part(
                    store,
                    body.encode("utf-8", errors="replace"),
                    f"{invocation_id}_{label}.log",
                    _LOG_MIME,
                    previewable=False,
                )
            )

    latency_ms = int((time.monotonic() - start) * 1000)
    manifest_payload = [
        {
            "path": e.path,
            "name": e.name,
            "sizeBytes": e.size_bytes,
            "attachmentId": e.attachment_id,
        }
        for e in result.mount_manifest.entries
    ]

    payload: dict[str, Any] = {
        "stdout": _truncate_preview(result.stdout),
        "stderr": _truncate_preview(result.stderr),
        "files": file_parts,
        "exit_code": result.exit_code,
        "invocation_id": invocation_id,
        "error_kind": result.error_kind.value,
        "error_summary": result.error_summary,
        "suggested_fix": result.suggested_fix,
        "environment_ready": result.environment_ready,
        "mount_manifest": manifest_payload,
        "partial": result.partial,
        "failed_at_line": result.failed_at_line,
    }
    if result.inspect_profile is not None:
        payload["inspect_profile"] = result.inspect_profile

    error_text = result.error_summary or result.error or "sandbox execution failed"
    _record_workspace_artifacts(file_parts, tool_name, stdout=result.stdout or "")
    if not result.success:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=error_text,
            latency_ms=latency_ms,
            extra={
                "invocation_id": invocation_id,
                "files": file_parts,
                FAILURE_KIND: _FAILURE_KIND_BY_ERROR.get(result.error_kind, FAILURE_KIND_EXECUTION),
            },
        )

    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
        extra={"invocation_id": invocation_id, "files": file_parts},
    )


def _record_workspace_artifacts(
    file_parts: list[dict[str, Any]],
    tool_name: str,
    *,
    stdout: str = "",
) -> None:
    workspace = get_run_workspace()
    if workspace is None or not file_parts:
        return
    scope = get_current_run_scope()
    role = scope.agent_role if scope is not None else ""
    workspace.artifacts.record_harvest(
        file_parts, stdout=stdout, tool_name=tool_name, agent_role=role
    )


def build_inspect_observation(
    result: SandboxExecResult,
    invocation_id: str,
    start: float,
) -> Observation:
    """Inspect returns profile JSON as primary payload."""
    latency_ms = int((time.monotonic() - start) * 1000)
    profile = result.inspect_profile or {}
    manifest_payload = [
        {
            "path": e.path,
            "name": e.name,
            "sizeBytes": e.size_bytes,
            "attachmentId": e.attachment_id,
        }
        for e in result.mount_manifest.entries
    ]
    payload: dict[str, Any] = {
        "inspect_profile": profile,
        "mount_manifest": manifest_payload,
        "environment_ready": result.environment_ready,
        "invocation_id": invocation_id,
        "summary": json.dumps(profile, ensure_ascii=False)[:SANDBOX_PREVIEW_CHAR_LIMIT],
    }
    if not result.success:
        payload["error_kind"] = result.error_kind.value
        payload["error_summary"] = result.error_summary
        payload["suggested_fix"] = result.suggested_fix
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=result.error_summary or result.error,
            latency_ms=latency_ms,
            extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
        )
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
        extra={"invocation_id": invocation_id},
    )
