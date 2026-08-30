"""Publish Office Works at run completion — LobeHub file-Work scan analog.

Workspace mutations stay on disk. One basename → one ledger row (latest bytes).
Preview is officecli ``view html`` (LobeHub HTML FileViewer). Private pptx/docx
never go to officeapps.live.com.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

import structlog

from lca.layer0_infra.file_store import FileStore, persist_generated_files
from lca.layer0_infra.sandbox.paths import ONLYBOXES
from lca.layer0_infra.sandbox.runtime_scope import get_sandbox_runtime
from lca.layer0_infra.workspace.deliverable import is_office_name
from lca.layer0_infra.workspace.scope import get_run_workspace

_log = structlog.get_logger(__name__)

_OUTLINE_EMPTY_KEYS = ("slides", "slideCount", "paragraphs", "sheets")


async def seal_office_works(store: FileStore | None = None) -> list[dict[str, Any]]:
    """Flush residents, persist finished Office files + HTML previews, update ledger."""
    runtime = get_sandbox_runtime()
    workspace = get_run_workspace()
    if runtime is None or workspace is None or store is None:
        return []
    try:
        parts = await publish_office_works(runtime, store)
    except Exception:
        _log.warning("office_works_seal_failed", run_id=workspace.run_id, exc_info=True)
        return []
    if parts:
        workspace.artifacts.record_from_tool_files(parts, tool_name="office_works")
    return parts


async def publish_office_works(runtime: Any, store: FileStore) -> list[dict[str, Any]]:
    """Scan outputs after flush; publish finished Office binaries and HTML previews."""
    await runtime.flush_office_residents(timeout_s=30)
    scanned = await runtime.scan_output_files(invocation_id="office_works_scan")
    published: list[dict[str, Any]] = []
    for sandbox_file in scanned:
        name = getattr(sandbox_file, "name", "") or ""
        if not is_office_name(name):
            continue
        guest = ONLYBOXES.output_file(PurePosixPath(name).name)
        if not await _office_has_content(runtime, guest):
            continue
        parts = persist_generated_files(store, (sandbox_file,))
        published.extend(parts)
        preview = await _render_html_preview(runtime, store, guest, name)
        if preview is not None:
            published.append(preview)
    return published


async def _office_has_content(runtime: Any, guest_path: str) -> bool:
    result = await runtime.run_terminal(
        f"officecli view {shlex_quote(guest_path)} outline --json",
        timeout_s=30,
        invocation_id="office_works_outline",
        harvest_outputs=False,
    )
    payload = _json_object(getattr(result, "stdout", "") or "")
    if payload is None:
        return True
    data = payload.get("data")
    if not isinstance(data, dict):
        return bool(payload.get("success", True))
    if "slides" in data and isinstance(data["slides"], list):
        return len(data["slides"]) > 0
    if "headings" in data and isinstance(data["headings"], list) and data["headings"]:
        return True
    for key in _OUTLINE_EMPTY_KEYS:
        value = data.get(key)
        if isinstance(value, int):
            return value > 0
        if isinstance(value, list):
            return len(value) > 0
    paragraphs = data.get("paragraphs")
    if isinstance(paragraphs, int):
        return paragraphs > 0
    return True


async def _render_html_preview(
    runtime: Any,
    store: FileStore,
    guest_path: str,
    office_name: str,
) -> dict[str, Any] | None:
    stem = PurePosixPath(office_name).stem
    html_name = f"{stem}.preview.html"
    html_path = ONLYBOXES.output_file(html_name)
    result = await runtime.run_terminal(
        f"officecli view {shlex_quote(guest_path)} html -o {shlex_quote(html_path)} --json",
        timeout_s=60,
        invocation_id="office_works_html",
        harvest_outputs=False,
    )
    if not getattr(result, "success", False):
        return None
    scanned = await runtime.scan_output_files(invocation_id="office_works_html_scan")
    for sandbox_file in scanned:
        if getattr(sandbox_file, "name", "") == html_name:
            parts = persist_generated_files(store, (sandbox_file,))
            return parts[0] if parts else None
    del store
    return None


def _json_object(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
