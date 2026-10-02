"""Assistant jobs endpoints for ``/v1/assistants`` (ADR-0268 P4).

GET/POST ``/v1/assistants/{assistant_id}/jobs`` read and write ``CronJob``
definitions through :class:`CronService` rooted at the assistant home.
``PUT``/``DELETE`` ``/v1/assistants/{assistant_id}/jobs/{job_id}`` implement
the ADR-0268 §9 card path: the request body carries only user-modified
fields (``title``/``schedule``/``timezone``/``report``/``enabled``/``body``),
the server merges them into the stored definition and rewrites ``anchor_at``
when the schedule basis changes. ``POST .../jobs/{job_id}:fire`` stays on the
COMPAT 501 envelope (CronJob has no HTTP fire).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.models.cron.models import ChatDelivery, CronJob
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _catalog_from_request,
    _error_envelope,
    _jobs_from_request,
    _jobs_not_implemented,
    _json,
    _not_implemented,
    _ownership_error,
    _user_from_request,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    _resolve_assistant_id,
)

_JOB_BODY_FIELDS = frozenset(
    {
        "id",
        "title",
        "schedule",
        "timezone",
        "body",
        "execution",
        "report",
        "enabled",
        "max_retries",
        "timeout_seconds",
        "chat_id",
    }
)

# 卡片路径（ADR-0268 §9）允许用户改的字段；请求体里缺省的字段表示不动。
_JOB_UPDATE_FIELDS = frozenset(
    {
        "title",
        "schedule",
        "timezone",
        "report",
        "enabled",
        "body",
    }
)


def _prelude(request: Request, op: str) -> tuple[str, Any, str] | JSONResponse:
    """公共前置：鉴权 → catalog → 解析 assistant_id → ownership（无白名单）。"""
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error
    # 契约:user_id_from_request 成功时 user_id 必为 str;auth 通过后可收窄。
    assert user_id is not None  # noqa: S101

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", f"assistant_jobs.{op}")

    raw_id = str(request.path_params.get("assistant_id") or "")
    assistant_id = _resolve_assistant_id(request, user_id, raw_id)

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    return user_id, catalog, assistant_id


def _cron_job_from_body(body: dict[str, Any], *, owner: str, now: datetime) -> CronJob:
    """把 POST body 映射为 ``CronJob``；非法输入抛 ``ValueError``（路由映射 400）。"""
    unknown = set(body) - _JOB_BODY_FIELDS
    if unknown:
        raise ValueError(f"未知字段: {', '.join(sorted(unknown))}")

    chat_id = body.get("chat_id")
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError("chat_id 必须为非空字符串")

    execution = body.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution 必须为 object")
    if execution.get("kind") == "agent":
        delivery_targets = (ChatDelivery(chat_id=chat_id),)
    elif execution.get("kind") == "space_action":
        delivery_targets = ()
    else:
        raise ValueError("execution.kind 必须为 agent 或 space_action")

    payload: dict[str, Any] = {
        "id": body.get("id"),
        "title": body.get("title"),
        "schedule": body.get("schedule"),
        "timezone": body.get("timezone"),
        "body": body.get("body"),
        "execution": execution,
        "delivery_targets": delivery_targets,
        "report": body.get("report", "anomalies_only"),
        "owner": owner,
        "created_chat_id": chat_id,
        "anchor_at": now,
        "enabled": body.get("enabled", True),
        "max_retries": body.get("max_retries", 0),
        "timeout_seconds": body.get("timeout_seconds"),
    }
    return CronJob.model_validate(payload)


def _merge_job_update(existing: CronJob, body: dict[str, Any], *, now: datetime) -> CronJob:
    """把卡片路径提交的「改过字段」合并进现有定义（ADR-0268 §9）。

    缺省字段表示不动；改 ``schedule`` 或 ``timezone`` 时服务端重写
    ``anchor_at`` 为 ``now``（清掉「下次触发基准」，run 记录不动）。
    非法输入抛 ``ValueError``（路由映射 400）。
    """
    unknown = set(body) - _JOB_UPDATE_FIELDS
    if unknown:
        raise ValueError(f"未知字段: {', '.join(sorted(unknown))}")

    update: dict[str, Any] = {}
    for field in _JOB_UPDATE_FIELDS:
        if field in body:
            update[field] = body[field]

    merged_data = existing.model_dump()
    merged_data.update(update)
    if "schedule" in update or "timezone" in update:
        merged_data["anchor_at"] = now
    return CronJob.model_validate(merged_data)


def _service_for(catalog: Any, assistant_id: str) -> CronService:
    """构造以 assistant home 为根的 ``CronService``。"""
    spec = catalog.get(assistant_id)
    return CronService(CronStore(Path(spec.home_path)))


async def list_assistant_jobs(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/jobs`` —— ``cron.list`` 投影。"""
    pre = _prelude(request, "list")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre

    try:
        service = _service_for(catalog, assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    items = service.list_items(owner=user_id, now=datetime.now(UTC))
    return _json(
        {"assistant_id": assistant_id, "jobs": [item.model_dump() for item in items]},
        status_code=200,
    )


async def create_assistant_job(request: Request) -> JSONResponse:
    """``POST /v1/assistants/{assistant_id}/jobs`` —— ``cron.add``。"""
    pre = _prelude(request, "create")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre

    try:
        service = _service_for(catalog, assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    now = datetime.now(UTC)
    try:
        job = _cron_job_from_body(body, owner=user_id, now=now)
    except ValueError as exc:
        return _error_envelope(
            "invalid_request", status_code=400, error_type="invalid_request", detail=str(exc)
        )

    created = service.add_job(
        id=job.id,
        title=job.title,
        schedule=job.schedule,
        timezone=job.timezone,
        body=job.body,
        execution=job.execution,
        delivery_targets=job.delivery_targets,
        report=job.report,
        owner=user_id,
        created_chat_id=job.created_chat_id,
        now=now,
        enabled=job.enabled,
        max_retries=job.max_retries,
        timeout_seconds=job.timeout_seconds,
    )

    items = service.list_items(owner=user_id, now=now)
    item = next((candidate for candidate in items if candidate.id == created.id), None)
    if item is None:
        # 重复 id 且为已完成 oneshot：不在「即将到来」投影里（ADR-0268 §10），
        # 幂等返回现有定义本身。
        return _json({"assistant_id": assistant_id, "job": created.model_dump()}, status_code=200)
    return _json({"assistant_id": assistant_id, "job": item.model_dump()}, status_code=201)


async def update_assistant_job(request: Request) -> JSONResponse:
    """``PUT /v1/assistants/{assistant_id}/jobs/{job_id}`` —— 卡片路径更新。

    请求体只含用户改过的字段（ADR-0268 §9 卡片路径）；服务端合并进存储定义，
    改 ``schedule``/``timezone`` 时重写 ``anchor_at``，响应返回新的
    :class:`CronListItem` 投影。
    """
    pre = _prelude(request, "update")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre
    job_id = str(request.path_params.get("job_id") or "")

    try:
        service = _service_for(catalog, assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    existing = service.get_job(job_id)
    if existing is None or existing.owner != user_id:
        return _error_envelope(
            "job_not_found", status_code=404, error_type="not_found", detail=f"job {job_id} 不存在"
        )

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    now = datetime.now(UTC)
    try:
        updated = _merge_job_update(existing, body, now=now)
    except ValueError as exc:
        return _error_envelope(
            "invalid_request", status_code=400, error_type="invalid_request", detail=str(exc)
        )

    service.replace_job(updated)

    items = service.list_items(owner=user_id, now=now)
    item = next((candidate for candidate in items if candidate.id == updated.id), None)
    if item is None:
        # 已完成的一次性任务不在「即将到来」投影里（ADR-0268 §10），卡片路径没有卡片可返回。
        return _error_envelope(
            "job_not_found", status_code=404, error_type="not_found", detail=f"job {job_id} 不存在"
        )
    return _json({"assistant_id": assistant_id, "job": item.model_dump()}, status_code=200)


async def delete_assistant_job(request: Request) -> JSONResponse:
    """``DELETE /v1/assistants/{assistant_id}/jobs/{job_id}`` —— 删除定义。

    只删除 ``cron/<job_id>.json`` 定义文件与未注入 handoff；已结束的 run
    记录保留（ADR-0268 §9）。
    """
    pre = _prelude(request, "delete")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre
    job_id = str(request.path_params.get("job_id") or "")

    try:
        service = _service_for(catalog, assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    existing = service.get_job(job_id)
    if existing is None or existing.owner != user_id:
        return _error_envelope(
            "job_not_found", status_code=404, error_type="not_found", detail=f"job {job_id} 不存在"
        )

    removed = service.remove_job(job_id)
    if not removed:
        return _error_envelope(
            "job_not_found", status_code=404, error_type="not_found", detail=f"job {job_id} 不存在"
        )
    return _json({"assistant_id": assistant_id, "deleted": job_id}, status_code=200)


async def assistant_job_item(request: Request) -> JSONResponse:
    """``/v1/assistants/{assistant_id}/jobs/{job_id}`` method dispatcher (PUT + DELETE)."""
    method = str(getattr(request, "method", "")).upper()
    if method == "PUT":
        return await update_assistant_job(request)
    if method == "DELETE":
        return await delete_assistant_job(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _error_envelope(
        "method_not_allowed",
        status_code=405,
        error_type="method_not_allowed",
        detail=f"Unsupported method {method}",
    )


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
    """``POST /v1/assistants/{assistant_id}/jobs/{job_id}:fire`` —— 保持 501。

    CronJob 没有 HTTP fire 入口（ADR-0268），触发由调度器按 ``next_run``
    到点执行。
    """
    if _jobs_from_request(request) is None:
        return _jobs_not_implemented("jobs_unavailable", "AssistantJobs.fire")
    return _jobs_not_implemented("jobs_pending", "AssistantJobs handler not wired")
