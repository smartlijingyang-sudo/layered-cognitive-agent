"""Assistant jobs endpoints for ``/v1/assistants`` (PR-8).

Handlers stay on the COMPAT 501 envelope until the ``assistant.jobs``
capability is wired to ``app.state.assistant_jobs``; the delete-when marker
is carried in the response body.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _jobs_from_request,
    _jobs_not_implemented,
    _json,
)


async def list_assistant_jobs(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/jobs`` —— ``AssistantJobs.list_jobs``."""
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.list_jobs")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")


async def create_assistant_job(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/jobs`` —— ``AssistantJobs.register``."""
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.register")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")


async def assistant_jobs_root(request: Request) -> JSONResponse:
    """``/v1/assistants/{assistant_id}/jobs`` method dispatcher (GET + POST)."""
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        return await create_assistant_job(request)
    if method == "GET":
        return await list_assistant_jobs(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _jobs_not_implemented("jobs_unavailable", f"unsupported method {method!r}")


async def fire_assistant_job(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/jobs/{job_id}:fire`` —— ``jobs.fire``.

    Phase 1 仅人工投递（``actor="manual"`` Trigger → 0093 WorkQueue）。
    """
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.fire")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")
