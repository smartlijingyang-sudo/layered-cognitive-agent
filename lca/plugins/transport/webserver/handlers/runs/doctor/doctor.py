"""Stable Gateway doctor.v2 facade.

Legacy JSONL inspection and Session Spine projection diagnostics have distinct
read models.  Their focused implementations live in sibling modules; this file
keeps only the response contract and compatibility-facing entry points.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.harness.state.projection import ProjectionSnapshot
from lca.plugins.transport.webserver.handlers.runs.doctor.legacy import diagnose_legacy
from lca.plugins.transport.webserver.handlers.runs.doctor.models import DoctorReport, HopVerdict
from lca.plugins.transport.webserver.handlers.runs.doctor.session_check import (
    diagnose_session_projection,
)


def diagnose(session: Any | None, jsonl_path: Path) -> DoctorReport:
    """Diagnose a legacy RunSession through its append-only JSONL journal."""
    return diagnose_legacy(session, jsonl_path)


def diagnose_session(
    *,
    run_id: str,
    snapshot: ProjectionSnapshot,
    persisted_seq: int,
    persistence_ref: str,
) -> DoctorReport:
    """Diagnose a Session Spine run through its durable projection."""
    return diagnose_session_projection(
        run_id=run_id,
        snapshot=snapshot,
        persisted_seq=persisted_seq,
        persistence_ref=persistence_ref,
    )


__all__ = ["DoctorReport", "HopVerdict", "diagnose", "diagnose_session"]
