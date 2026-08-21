"""HTTP for Runs: create, live, get, cancel, answer, doctor."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway.cors import cors_headers
from gateway.modes import resolve_lca_mode
from gateway.runs.doctor import diagnose
from gateway.runs.execute import create_run_session, llm_status, resume_run, schedule_run
from gateway.runs.identity import parse_agent_ref
from gateway.runs.ingress import prepare_run_from_messages
from gateway.runs.live import LiveGap, LiveTail
from gateway.runs.session import RunRegistry, RunStatus
from lca.contracts.models.observability.journal import (
    StampedEvent,
    StepTextDelta,
)
from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.observability.journal.sse_frames import (
    parse_last_event_id,
    stamped_to_sse_frame,
)

# ADR-0051 Phase 2 § 九: StepTextDelta 双通道。UI 仅取 answer；ops/replay 取 all。
_TEXT_CHANNEL_ALL: str = "all"
_TEXT_CHANNEL_ANSWER: str = "answer"


def _is_visible_text_channel(stamped: StampedEvent, channel: str | None) -> bool:
    """StepTextDelta 按 channel 过滤；其它事件类型总是可见。

    ``channel=None`` 不过滤；``channel="all"`` 全推；``channel="answer"``
    仅推 answer 通道（ADR-0051 Phase 2 § 九 —— chat-projector / turn-timeline-projector
    只用 answer 通道更新 finalAnswer）。
    """
    if channel is None or channel == _TEXT_CHANNEL_ALL:
        return True
    event = stamped.event
    if not isinstance(event, StepTextDelta):
        return True
    return getattr(event, "channel", "decision") == channel


def _registry_of(request: Request) -> RunRegistry:
    return cast("RunRegistry", request.app.state.registry)


def _file_store_of(request: Request) -> LocalFileStore:
    return cast("LocalFileStore", request.app.state.file_store)


def _ctx_of(request: Request) -> Any:
    """Cordis Context booted by create_app(); None when running without profile."""
    return getattr(request.app.state, "ctx", None)


_HEARTBEAT_INTERVAL_S = 15.0
_HEARTBEAT = b": keepalive\n\n"


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


def encode_live_gap(gap: LiveGap) -> bytes:
    payload = json.dumps(
        {"requested_seq": gap.requested_seq, "oldest_seq": gap.oldest_seq},
        ensure_ascii=False,
    )
    return f"event: LiveGap\ndata: {payload}\n\n".encode()


async def iter_live_sse(
    tail: LiveTail,
    *,
    after_seq: int = 0,
    heartbeat_s: float = _HEARTBEAT_INTERVAL_S,
    redact: bool = True,
    text_channel: str | None = _TEXT_CHANNEL_ANSWER,
) -> AsyncIterator[bytes]:
    """Journal frames + comment heartbeats. No projection, no adapter.

    ``text_channel`` 过滤 StepTextDelta：

    - ``"answer"`` (默认) — LobeHub live 只推 answer 通道（ADR-0051 Phase 2 § 九）
    - ``"all"``          — ops 调试全推（``/journal/live``）
    - ``None``           — 不过滤（向后兼容 / 排查用）

    Journal 仍写双份：decision 给 replay/audit，answer 给 UI。
    """
    sub = tail.subscribe(after_seq=after_seq)
    while True:
        try:
            item = await asyncio.wait_for(sub.__anext__(), timeout=heartbeat_s)
        except TimeoutError:
            yield _HEARTBEAT
            continue
        except StopAsyncIteration:
            break
        if isinstance(item, LiveGap):
            yield encode_live_gap(item)
            continue
        if not _is_visible_text_channel(item, text_channel):
            continue
        yield stamped_to_sse_frame(item, redact=redact).encode()


async def create_run(request: Request) -> JSONResponse:
    """POST /runs — start an LCA run; client then GETs /runs/{id}/live."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    ctx = _ctx_of(request)
    if ctx is None:
        return _err(
            "gateway boot 未加载 profile，无法执行 LCA run。",
            status_code=503,
            error_type="service_unavailable",
            code="lca_plugin_ctx_missing",
        )
    if not llm_status(ctx)["llm_available"]:
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
    run_input = await prepare_run_from_messages(messages, _file_store_of(request))
    if not run_input.user_text.strip():
        return _err("messages must include a non-empty user message", status_code=400)

    mode = resolve_lca_mode(model)
    agent = parse_agent_ref(body.get("agent"))
    registry = _registry_of(request)
    registry.prune()
    session = registry.find_inflight_run(
        user_text=run_input.user_text,
        mode=mode,
        attachment_ids=run_input.attachment_ids,
        agent_id=agent.agent_id,
    )
    if session is None:
        session = create_run_session(
            registry,
            question=run_input.question,
            user_text=run_input.user_text,
            mode=mode,
            attachment_ids=run_input.attachment_ids,
            prior_turns=run_input.prior_turns,
            agent=agent,
            device_id=str(body.get("device_id") or ""),
            plane=str(body.get("plane") or ""),
            extra_plane=str(body.get("extra_plane") or ""),
            execution_target=str(body.get("execution_target") or body.get("executionTarget") or ""),
            ctx=ctx,
        )
        schedule_run(registry, session, ctx=ctx)

    return JSONResponse(
        {
            "run_id": session.run_id,
            "trace_id": session.trace_id,
            "agent": {"id": session.agent.agent_id, "name": session.agent.name},
            "live_url": f"/runs/{session.run_id}/live",
        },
        status_code=202,
        headers=cors_headers(),
    )


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
    """GET /context — bound planes of latest run + online machine candidates."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    devices = request.app.state.devices
    online = [device.as_dict() for device in devices.list_online()]
    latest = _registry_of(request).latest_bindings()
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
    """GET /journal/live — every Run's journal, process-wide. For lca-ops logs."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    after = parse_last_event_id(request.headers.get("last-event-id"))
    tail = _registry_of(request).journal.tail

    async def _gen() -> AsyncIterator[bytes]:
        async for frame in iter_live_sse(
            tail, after_seq=after, redact=False, text_channel=_TEXT_CHANNEL_ALL
        ):
            yield frame

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


async def stream_run_live(request: Request) -> StreamingResponse | JSONResponse:
    """GET /runs/{run_id}/live — Journal SSE. Honors Last-Event-ID."""
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    run_id = request.path_params["run_id"]
    after = parse_last_event_id(request.headers.get("last-event-id"))
    session = _registry_of(request).get(run_id)
    if session is None:
        return _err("run not found", status_code=404)

    async def _gen() -> AsyncIterator[bytes]:
        async for frame in iter_live_sse(session.tail, after_seq=after):
            yield frame

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


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    registry = _registry_of(request)
    registry.prune()
    summary = registry.summary(run_id)
    if summary is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    return JSONResponse(summary, headers=cors_headers())


async def get_run_doctor(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    registry = _registry_of(request)
    session = registry.get(run_id)
    jsonl_path = session.jsonl_path if session is not None else registry.jsonl_path_for(run_id)
    if session is None and not jsonl_path.is_file():
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    report = diagnose(session, jsonl_path)
    return JSONResponse(report.as_dict(), headers=cors_headers())


async def get_run_evidence(request: Request) -> JSONResponse:
    """GET /runs/{run_id}/evidence/{ref} —— fetch evidence by content hash.

    ADR-0065 §四 L5: 大 UI state 走 EvidenceStore(``state_ref``);本端点
    接受 ``EvidenceRef.digest`` (``sha256:<hex>`` 或裸 hex),从
    ``EvidenceStore.get()`` 取出并验证完整性(L5)。响应 body 是
    JSON-decoded dict,即原始 ``plugin_state``。

    实现路径:
    1. 在 run 的 journal.jsonl 里查 ``state_ref.digest`` 匹配的 Tool* 事件
       (typed field ``state_ref`` 在 v2 envelope 里有完整 EvidenceRef,
       含 ``byte_length`` / ``classification`` 等;ref-only URL 不可信,
       必须用 journal 里记录的完整 EvidenceRef 调 store.get())。
    2. 拿到的完整 EvidenceRef 调 ``EvidenceStore.get(requester, audience)``,
       store 内部做 sha256 + byte_length + classification 校验(L5)。
    3. payload 必须是 JSON,decode 后作为 ``data`` 字段返回。

    Status codes:
    - 200 找到 + 完整性校验通过
    - 400 ref 格式非法
    - 403 audience 拒绝
    - 404 EvidenceStore 未配 / run 不存在 / ref 不属于 run
    - 500 摘要校验失败 / payload 非 JSON(0065 §四 不允许静默)
    """
    from lca.contracts.observability.evidence import (
        Classification,
        EvidenceIntegrityError,
    )
    from lca.layer0_infra.observability.journal.journal_io import (
        record_normalize,
    )

    run_id = request.path_params["run_id"]
    ref_str = request.path_params["ref"]
    bound = getattr(request.app.state, "bound_observability", None)
    if bound is None or bound.evidence_store is None:
        return JSONResponse(
            {"error": "evidence store not configured", "run_id": run_id, "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )
    # Parse ref: accept "sha256:<hex>" or bare hex
    raw = ref_str.strip()
    if raw.startswith("sha256:"):
        digest_only = raw[len("sha256:"):]
    elif len(raw) == 64 and all(c in "0123456789abcdef" for c in raw.lower()):
        digest_only = raw.lower()
    else:
        return JSONResponse(
            {"error": "invalid ref format", "ref": ref_str},
            status_code=400,
            headers=cors_headers(),
        )

    # Locate the run's journal.jsonl via the registry; if not running,
    # the bootstrap fallback in registry.jsonl_path_for is used.
    registry = getattr(request.app.state, "registry", None)
    jsonl_path = None
    if registry is not None:
        try:
            jsonl_path = registry.jsonl_path_for(run_id)
        except Exception:
            jsonl_path = None
    if jsonl_path is None or not jsonl_path.is_file():
        # try canonical "traces/lca_journal.jsonl" as a last resort
        from pathlib import Path

        candidate = Path("traces") / "lca_journal.jsonl"
        if candidate.is_file():
            jsonl_path = candidate
    if jsonl_path is None or not jsonl_path.is_file():
        return JSONResponse(
            {"error": "run not found", "run_id": run_id, "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )

    # Find the full EvidenceRef for this digest in the journal (typed field).
    ref = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        normalized = record_normalize(payload)
        if normalized.get("schema") != "lca.journal/2":
            continue
        sr = normalized.get("data", {}).get("state_ref")
        if not isinstance(sr, dict):
            continue
        if str(sr.get("digest", "")).lower() == digest_only:
            try:
                from lca.contracts.observability.evidence import EvidenceRef

                ref = EvidenceRef.from_dict(sr)
            except (ValueError, TypeError, KeyError):
                ref = None
            break
    if ref is None:
        return JSONResponse(
            {"error": "evidence ref not found in run journal", "run_id": run_id, "ref": ref_str},
            status_code=404,
            headers=cors_headers(),
        )

    requester = f"gateway:{run_id}"
    try:
        payload = bound.evidence_store.get(
            ref, requester=requester, audience=Classification.INTERNAL
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
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(
            {"error": "evidence payload not json-decodable", "ref": ref_str, "byte_length": len(payload)},
            status_code=500,
            headers=cors_headers(),
        )
    return JSONResponse(
        {"run_id": run_id, "ref": ref_str, "byte_length": len(payload), "data": decoded},
        headers=cors_headers(),
    )


async def cancel_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    session = _registry_of(request).get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    if session.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED):
        return JSONResponse({"status": session.status.value}, headers=cors_headers())
    session.cancel_requested = True
    session.status = RunStatus.CANCELED
    if session.task is not None and not session.task.done():
        session.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session.task
    return JSONResponse({"status": RunStatus.CANCELED.value}, headers=cors_headers())


async def answer_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    registry = _registry_of(request)
    session = registry.get(run_id)
    if session is None:
        return JSONResponse({"error": "run not found"}, status_code=404, headers=cors_headers())
    if session.status != RunStatus.WAITING_INPUT:
        return JSONResponse(
            {"error": "run not waiting for input", "status": session.status.value},
            status_code=409,
            headers=cors_headers(),
        )
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400, headers=cors_headers())
    answer = str(body.get("answer", "")).strip()
    if not answer:
        return JSONResponse(
            {"error": "answer is required"}, status_code=400, headers=cors_headers()
        )
    if session.snapshot is None or session.runnable is None:
        return JSONResponse(
            {"error": "no resume state available"},
            status_code=500,
            headers=cors_headers(),
        )
    session.status = RunStatus.RUNNING
    task = asyncio.create_task(resume_run(session, registry, answer))
    session.task = task
    return JSONResponse({"run_id": run_id, "status": "resumed"}, headers=cors_headers())


def health_payload(registry: RunRegistry, *, ctx: Any) -> dict[str, Any]:
    return {
        "status": "ok",
        **llm_status(ctx),
        "runs": registry.status_counts(),
        "live": registry.live_totals(),
    }
