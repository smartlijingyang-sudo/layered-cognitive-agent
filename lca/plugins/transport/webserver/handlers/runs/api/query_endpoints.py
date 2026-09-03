"""HTTP query handlers for the run carrier.

All handlers read through the composition-selected run owner or observability
store. This keeps query shaping and compatibility SSE framing local while the
carrier remains independent from concrete loop implementations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_locator import RunLocator
from lca.infrastructure.observability.journal.sse.frames import parse_last_event_id
from lca.plugins.transport.webserver.handlers.cors import cors_headers
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import _run_port_of
from lca.plugins.transport.webserver.handlers.runs.observability.evidence import (
    EvidencePayloadDecodeError,
    InvalidEvidenceDigestError,
    RunEvidenceNotFoundError,
    RunEvidenceReader,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port import RunPort

_DEFAULT_PROFILE_SNAPSHOT_ROOT = Path("traces") / "runs"


def _spine_path_of(request: Request, run_id: str):
    """Resolve one run's Journal through the owner selected by composition."""
    return _run_port_of(request).journal_path(run_id)


def _run_locator_of(request: Request) -> RunLocator | None:
    """Resolve the boot-provided RunLocator without constructing a filesystem backend."""
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is None:
        return None
    try:
        locator = require_capability(ctx, "run_locator")
    except MissingCapabilityError:
        return None
    return locator if isinstance(locator, RunLocator) else None


def _profile_snapshot_path(request: Request, run_id: str) -> Path:
    """Resolve ``<run_dir>/profile_snapshot.json`` via RunLocator when bound."""
    locator = _run_locator_of(request)
    if locator is not None:
        return locator.profile_snapshot_path(run_id)
    return _DEFAULT_PROFILE_SNAPSHOT_ROOT / run_id / "profile_snapshot.json"  # noqa: observation_ssot


def _plane_payload(ref: object | None) -> dict[str, str] | None:
    if ref is None:
        return None
    kind_attr = getattr(ref, "kind", None)
    kind_value = getattr(kind_attr, "value", "") if kind_attr is not None else ""
    return {
        "id": getattr(ref, "id", ""),
        "label": getattr(ref, "label", ""),
        "kind": kind_value,
        "root": getattr(ref, "root", ""),
        "outputs_dir": getattr(ref, "outputs_dir", ""),
        "platform": getattr(ref, "platform", ""),
        "home": getattr(ref, "home", ""),
    }


async def get_context(request: Request) -> JSONResponse:
    """GET /context — bound planes of latest run plus online device candidates."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    devices = request.app.state.devices
    online = [device.as_dict() for device in devices.list_online()]
    latest = _run_port_of(request).latest_bindings()
    bindings = None
    if latest is not None:
        bindings = {
            "primary": _plane_payload(latest.primary),
            "secondary": _plane_payload(latest.secondary),
        }
    return JSONResponse(
        {"bindings": bindings, "online_devices": online},
        headers=cors_headers(),
    )


async def stream_journal_live(request: Request) -> StreamingResponse | JSONResponse:
    """``GET /journal/live`` — process-wide compatibility SSE.

    The route is bound at boot only when the ``process_journal`` capability
    is present (ADR-0163 决策 3). Reaching this handler implies
    ``RunPort.stream_process_journal_live`` must produce frames. Returning
    ``None`` here is a real port bug, not a service-shaped 503.
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    after = parse_last_event_id(request.headers.get("last-event-id"))
    frames = _run_port_of(request).stream_process_journal_live(after)
    if frames is None:
        return JSONResponse(
            {"error": "run owner lacks process journal streaming"},
            status_code=500,
            headers=cors_headers(),
        )
    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers=cors_headers(
            **{
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        ),
    )


def _parse_after(request: Request) -> int:
    """Parse ``?after=`` as a non-negative int; invalid values start from 0."""
    raw = request.query_params.get("after", "0")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


async def stream_run_live(request: Request) -> StreamingResponse | JSONResponse:
    """GET /runs/{run_id}/live — Journal SSE for one run (event = class name).

    Tool lifecycle frames carry the renderer-facing ``projected_state``
    field directly (set by ``lca/cognition/body/tool_journal_emit.py``
    via each Tool's RenderContract). No further lifting is required —
    the frontend's ``projectToolCall()`` reads the projected_state as-is.
    """
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    run_id = request.path_params["run_id"]
    if await _run_port_of(request).summary(run_id) is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    return StreamingResponse(
        _run_port_of(request).stream_run_live(run_id, _parse_after(request)),
        media_type="text/event-stream",
        headers=cors_headers(
            **{
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        ),
    )


async def get_run(request: Request) -> JSONResponse:
    """GET /runs/{run_id} — retrieve a compatibility summary through the owner."""
    run_id = request.path_params["run_id"]
    summary = await _run_port_of(request).summary(run_id)
    if summary is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    return JSONResponse(summary, headers=cors_headers())


async def get_run_doctor(request: Request) -> JSONResponse:
    """GET /runs/{run_id}/doctor — expose the owner's diagnostic projection."""
    run_id = request.path_params["run_id"]
    report = await _run_port_of(request).doctor(run_id)
    if report is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    return JSONResponse(report.as_dict(), headers=cors_headers())


async def get_run_profile(request: Request) -> JSONResponse:
    """GET /runs/{run_id}/profile — return the boot-time profile_snapshot.json."""
    run_id = request.path_params["run_id"]
    snapshot_path = _profile_snapshot_path(request, run_id)
    if not snapshot_path.is_file():
        return JSONResponse(
            {"error": f"No profile snapshot for run {run_id}"},
            status_code=404,
            headers=cors_headers(),
        )
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "invalid profile snapshot", "run_id": run_id},
            status_code=500,
            headers=cors_headers(),
        )
    return JSONResponse(payload, headers=cors_headers())


async def get_run_evidence(request: Request) -> JSONResponse:
    """GET /runs/{run_id}/evidence/{ref} — fetch verified evidence by digest."""
    from lca.contracts.observability.evidence import EvidenceIntegrityError

    run_id = request.path_params["run_id"]
    ref_str = request.path_params["ref"]
    bound = getattr(request.app.state, "bound_observability", None)
    evidence_binding = bound.evidence_binding() if bound is not None else None
    if evidence_binding is None or evidence_binding.store is None:
        return JSONResponse(
            {"error": "evidence store not configured", "run_id": run_id, "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )

    try:
        evidence = RunEvidenceReader(evidence_binding.store).read_json(
            run_id=run_id,
            requested_ref=ref_str,
            journal_path=_spine_path_of(request, run_id),
            requester=f"gateway:{run_id}",
        )
    except InvalidEvidenceDigestError:
        return JSONResponse(
            {"error": "invalid ref format", "ref": ref_str},
            status_code=400,
            headers=cors_headers(),
        )
    except RunEvidenceNotFoundError:
        return JSONResponse(
            {"error": "evidence ref not found in run journal", "run_id": run_id, "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )
    except EvidenceIntegrityError as exc:
        return JSONResponse(
            {"error": "evidence integrity violation", "detail": str(exc), "ref": ref_str},
            status_code=500,
            headers=cors_headers(),
        )
    except KeyError as exc:
        return JSONResponse(
            {"error": "evidence ref not found", "detail": str(exc), "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )
    except PermissionError as exc:
        return JSONResponse(
            {"error": "audience rejected", "detail": str(exc), "ref": ref_str},
            status_code=403,
            headers=cors_headers(),
        )
    except EvidencePayloadDecodeError as exc:
        return JSONResponse(
            {
                "error": "evidence payload not json-decodable",
                "ref": ref_str,
                "byte_length": exc.byte_length,
            },
            status_code=500,
            headers=cors_headers(),
        )
    return JSONResponse(
        {
            "run_id": evidence.run_id,
            "ref": evidence.requested_ref,
            "byte_length": evidence.byte_length,
            "data": evidence.data,
        },
        headers=cors_headers(),
    )


def health_payload(run_port: RunPort, *, ctx: Any) -> dict[str, Any]:
    """Build a health projection from the composition-selected run owner.

    Boot-period readiness is enforced by the routes plugin and the LLM
    resolver plugin; this projection is now run-port-only and fits inside
    the carrier surface.
    """
    return {
        "status": "ok",
        "runs": run_port.status_counts(),
        "live": run_port.live_totals(),
    }


__all__ = [
    "get_context",
    "get_run",
    "get_run_doctor",
    "get_run_evidence",
    "get_run_profile",
    "health_payload",
    "stream_journal_live",
    "stream_run_live",
]
