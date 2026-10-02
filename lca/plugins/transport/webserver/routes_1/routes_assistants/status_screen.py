"""Status Screen aggregated snapshot endpoint (/v1/assistants/{id}/status-snapshot).

Aggregates Activity (unified event log projection), Approvals (pending queue),
Upcoming (ADR-0268 cron.list projection), and Identity standing files metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.infrastructure.observability.activity_projector import get_global_activity_projector
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _error_envelope,
    _json,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    STANDING_FILES_WHITELIST,
    _prelude,
    _summarize,
    sha256_of_str,
)


def _collect_standing_files(home_path: str) -> list[dict[str, Any]]:
    home = Path(home_path)
    files_data: list[dict[str, Any]] = []

    for filename in STANDING_FILES_WHITELIST:
        file_path = home / filename
        size_bytes, line_count = 0, 0
        updated_at, summary = "", ""
        content_hash = sha256_of_str("")
        if file_path.is_file():
            try:
                stat = file_path.stat()
                content = file_path.read_text(encoding="utf-8")
                size_bytes = stat.st_size
                line_count = len(content.splitlines())
                updated_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                content_hash = sha256_of_str(content)
                summary = _summarize(content)
            except (OSError, UnicodeDecodeError):
                continue
        files_data.append(
            {
                "filename": filename,
                "path": str(file_path),
                "size_bytes": size_bytes,
                "line_count": line_count,
                "updated_at": updated_at,
                "content_hash": content_hash,
                "summary": summary,
            }
        )
    return files_data


async def assistant_status_snapshot(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/status-snapshot`` —— Aggregated view for Status screen."""
    pre = _prelude(request, "status-snapshot")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre

    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    # 1. Activities from global single-track event projector
    activities = get_global_activity_projector().get_activities(assistant_id)

    # 2. Upcoming tasks from ADR-0268 CronStore
    upcoming: list[dict[str, Any]] = []
    try:
        cron_service = CronService(CronStore(Path(spec.home_path)))
        items = cron_service.list_items(owner=user_id, now=datetime.now(UTC))
        upcoming = [item.model_dump() for item in items]
    except Exception:
        upcoming = []

    # 3. Identity standing files
    files = _collect_standing_files(spec.home_path)

    # 4. Approvals
    approvals: list[dict[str, Any]] = []

    return _json(
        {
            "assistant_id": assistant_id,
            "activities": [a.model_dump() for a in activities],
            "approvals": approvals,
            "upcoming": upcoming,
            "identity": {
                "assistant_id": assistant_id,
                "files": files,
            },
        },
        status_code=200,
    )


__all__ = ("assistant_status_snapshot",)
