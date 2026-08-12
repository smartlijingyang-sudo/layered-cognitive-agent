"""HTTP: agent run create + native timeline SSE."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway._http import cors_headers
from gateway.lobehub_bridge import prepare_run_from_messages
from gateway.mode_catalog import resolve_lca_mode
from gateway.run_executor import create_run_session, llm_status, schedule_run
from lca.layer0_infra.observability.journal.sse_frames import parse_last_event_id


def _err(
    message: str,
    *,
    status_code: int,
    error_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    err: dict[str, Any] = {"message": message, "type": error_type}
    if code:
        err["code"] = code
    return JSONResponse({"error": err}, status_code=status_code, headers=cors_headers())


async def create_agent_run(request: Request) -> JSONResponse:
    """POST /v1/agent/runs — start an LCA agent run; client then GETs timeline."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    if not llm_status()["llm_available"]:
        return _err(
            "LLM_API_KEY 未配置，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_llm_unavailable",
        )
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("invalid JSON body", status_code=400)
    if not isinstance(body, dict):
        return _err("request body must be a JSON object", status_code=400)

    messages = body.get("messages") or []
    if not isinstance(messages, list):
        return _err("messages must be an array", status_code=400)

    model = str(body.get("model", "solo"))
    from gateway.app import get_file_store, get_registry

    run_input = await prepare_run_from_messages(messages, get_file_store())
    if not run_input.user_text.strip():
        return _err("messages must include a non-empty user message", status_code=400)

    mode = resolve_lca_mode(model)
    registry = get_registry()
    session = registry.find_inflight_run(
        user_text=run_input.user_text,
        mode=mode,
        attachment_ids=run_input.attachment_ids,
    )
    if session is None:
        session = create_run_session(
            registry,
            question=run_input.question,
            user_text=run_input.user_text,
            mode=mode,
            attachment_ids=run_input.attachment_ids,
            prior_turns=run_input.prior_turns,
        )
        schedule_run(registry, session)

    return JSONResponse(
        {
            "run_id": session.run_id,
            "trace_id": session.trace_id,
            "timeline_url": f"/v1/agent/runs/{session.run_id}/timeline",
        },
        status_code=202,
        headers=cors_headers(),
    )


async def stream_agent_timeline(request: Request) -> StreamingResponse | JSONResponse:
    """GET /v1/agent/runs/{run_id}/timeline — timeline.v1 SSE."""
    run_id = request.path_params["run_id"]
    last_event_id = request.headers.get("last-event-id")
    after = parse_last_event_id(last_event_id)

    from gateway.app import get_registry

    session = get_registry().get(run_id)
    if session is None:
        return _err("run not found", status_code=404)

    buffered = session.bus.buffered_after(after)

    async def _gen() -> AsyncIterator[bytes]:
        # Replay buffer through projector (stateful — single projector for whole stream)
        from gateway.timeline.projector import TimelineProjector
        from gateway.timeline.protocol import encode_sse_bytes

        projector = TimelineProjector()
        for stamped in buffered:
            for ev in projector.project(stamped):
                yield encode_sse_bytes(ev, seq=int(ev.get("seq") or stamped.seq))
        if not session.bus.is_closed:
            async for stamped in session.bus.subscribe(after_seq=after):
                for ev in projector.project(stamped):
                    yield encode_sse_bytes(ev, seq=int(ev.get("seq") or stamped.seq))

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers=cors_headers(
            **{
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        ),
    )
