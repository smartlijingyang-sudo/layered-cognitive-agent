"""Publish machine ``outputs_dir`` into FileStore — same parts as sandbox harvest."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.models.core.sandbox import SandboxFile
from lca.infrastructure.computer.op_result import ComputerOpResult
from lca.infrastructure.file_store import FileStore, persist_generated_files
from lca.infrastructure.workspace.deliverable import visible_generated_files

ComputerOp = Callable[..., Awaitable[Mapping[str, Any]]]


def output_paths_from_list_body(body: Mapping[str, Any], outputs_dir: str) -> list[str]:
    """Accept CLI (nested ``state.files``, name-only) and guest (top-level + path)."""
    raw = body.get("files")
    if not isinstance(raw, list):
        nested = body.get("state")
        if isinstance(nested, dict):
            raw = nested.get("files")
    if not isinstance(raw, list):
        content = body.get("content")
        if isinstance(content, str) and content[:1] in {"[", "{"}:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None
            raw = parsed if isinstance(parsed, list) else None
    if not isinstance(raw, list):
        return []

    paths: list[str] = []
    for item in raw:
        if isinstance(item, str):
            candidate = item
        elif isinstance(item, dict):
            if item.get("isDirectory"):
                continue
            candidate = str(item.get("path") or item.get("name") or "")
        else:
            continue
        if not candidate:
            continue
        resolved = (
            candidate if candidate.startswith("/") else f"{outputs_dir.rstrip('/')}/{candidate}"
        )
        if _under_dir(resolved, outputs_dir):
            paths.append(resolved)
    return list(dict.fromkeys(paths))


async def read_machine_bytes(computer_op: ComputerOp, path: str) -> bytes | None:
    """Binary read via sidecar ``exportFile`` (base64). Never UTF-8 ``readFile``."""
    body = await computer_op("exportFile", {"path": path})
    if not isinstance(body, Mapping) or not body.get("success", True):
        return None
    raw = body.get("b64") or body.get("content")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return base64.b64decode(raw)
    except (ValueError, TypeError):
        return None


async def harvest_plane_outputs(
    *,
    computer_op: ComputerOp,
    plane: PlaneRef,
    store: FileStore,
    seen: dict[str, str] | None = None,
    extra_path: str = "",
    tool_name: str = "",
    command: str = "",
) -> list[dict[str, Any]]:
    """Scan ``plane.outputs_dir``, persist new/changed files, return canonical parts."""
    outputs_dir = plane.outputs_dir
    if not outputs_dir:
        return []
    paths: list[str] = []
    if extra_path and _under_dir(extra_path, outputs_dir):
        paths.append(extra_path)
    listed = await computer_op("listFiles", {"directory_path": outputs_dir})
    if isinstance(listed, Mapping):
        paths.extend(output_paths_from_list_body(listed, outputs_dir))

    fingerprints = seen if seen is not None else {}
    generated: list[SandboxFile] = []
    for path in dict.fromkeys(paths):
        data = await read_machine_bytes(computer_op, path)
        if not data:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if fingerprints.get(path) == digest:
            continue
        fingerprints[path] = digest
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        mime, _ = mimetypes.guess_type(name)
        generated.append(
            SandboxFile(name=name, mime_type=mime or "application/octet-stream", data=data)
        )
    return persist_generated_files(
        store,
        visible_generated_files(generated, tool_name=tool_name, command=command),
    )


async def attach_harvested_outputs(
    result: ComputerOpResult,
    *,
    computer_op: ComputerOp,
    plane: PlaneRef,
    store: FileStore,
    seen: dict[str, str] | None = None,
    extra_path: str = "",
    tool_name: str = "",
    command: str = "",
) -> ComputerOpResult:
    """Copy sandbox harvest onto a successful machine op without leaking file bytes."""
    if not result.success:
        return result
    cmd = command or str(result.state.get("command") or "")
    try:
        parts = await harvest_plane_outputs(
            computer_op=computer_op,
            plane=plane,
            store=store,
            seen=seen,
            extra_path=extra_path,
            tool_name=tool_name,
            command=cmd,
        )
    except Exception:
        return result
    if not parts:
        return result
    state = dict(result.state)
    state["files"] = parts
    return ComputerOpResult(
        success=result.success,
        content=result.content,
        state=state,
        error=result.error,
        exec_result=result.exec_result,
        generated_files=result.generated_files,
    )


def _under_dir(path: str, directory: str) -> bool:
    left = os.path.normpath(path)
    right = os.path.normpath(directory)
    return left == right or left.startswith(right + os.sep)
