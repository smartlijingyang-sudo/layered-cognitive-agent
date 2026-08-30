"""Stage FileStore attachments onto a resolved machine plane.

Attachment staging is an effectful transport concern.  Keeping it separate from
capability and driver resolution makes the legacy execution environment's
preflight order explicit and independently testable.
"""

from __future__ import annotations

import time
from typing import cast

import structlog

from gateway.runs.session import RunSession
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.models.observability.journal import (
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
)
from lca.contracts.protocols.infra import MachineResolver
from lca.infrastructure.attachment import FileStoreAttachmentIdentity
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.observability import record
from lca.infrastructure.plane.resolve import ref_of

_log = structlog.get_logger(__name__)


async def stage_machine_attachments(
    session: RunSession,
    store: FileStore | None,
    machine_resolver: MachineResolver | None,
) -> None:
    """Copy all run attachments to the selected machine or fail before execution."""
    if session.bindings is None:
        return
    machine = ref_of(session.bindings, PlaneKind.MACHINE)
    if machine is None or not session.attachment_ids:
        return
    if store is None:
        raise MissingCapabilityError("file_store")
    transport = (
        machine_resolver.resolve_transport(machine.id) if machine_resolver is not None else None
    )
    if transport is None:
        raise RuntimeError(f"machine {machine.label} offline; cannot stage attachments")
    files = FileStoreAttachmentIdentity(store).stage_payload(session.run_id, session.attachment_ids)
    if not files:
        raise RuntimeError(
            f"machine attachments missing in FileStore: {list(session.attachment_ids)}"
        )
    total_bytes = sum(len(value) for value in files.values())
    record(
        AttachmentStagingStarted(
            plane_id=machine.id,
            file_count=len(files),
            total_bytes=total_bytes,
            run_id=session.run_id,
        )
    )
    started = time.monotonic()
    try:
        result = await transport.write_files(
            cast("dict[str, bytes | str]", files),
            base_dir=machine.root,
        )
    except Exception as exc:
        _log.exception(
            "attachment_staging_transport_error",
            run_id=session.run_id,
            plane_id=machine.id,
        )
        record(
            AttachmentStagingFailed(
                plane_id=machine.id,
                error=f"{type(exc).__name__}: {exc}",
                failed_paths=tuple(files.keys()),
                run_id=session.run_id,
            )
        )
        raise
    duration_ms = (time.monotonic() - started) * 1000
    if getattr(result, "success", True) is False:
        error_msg = str(getattr(result, "error", result))
        record(
            AttachmentStagingFailed(
                plane_id=machine.id,
                error=error_msg,
                failed_paths=tuple(files.keys()),
                run_id=session.run_id,
            )
        )
        raise RuntimeError(f"附件暂存失败（{len(files)} 个文件）: {error_msg}")
    record(
        AttachmentStagingCompleted(
            plane_id=machine.id,
            file_count=len(files),
            total_bytes=total_bytes,
            duration_ms=duration_ms,
        )
    )


__all__ = ["stage_machine_attachments"]
