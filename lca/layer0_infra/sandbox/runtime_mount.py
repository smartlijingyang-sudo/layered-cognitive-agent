"""Mount loading and guest-path verification for run-bound sandbox (ADR-0050)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    MountEntry,
    MountManifest,
    SandboxErrorKind,
    SandboxExecResult,
    SandboxResult,
)
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.sandbox.exec_result import sandbox_exec_result_from
from lca.layer0_infra.tools.run_attachment_scope import merge_attachment_ids

MOUNT_VERIFY_SCRIPT = """
import json as _j
import os as _o
root = {root!r}
expected = {expected!r}
found = {{}}
for dirpath, _, filenames in _o.walk(root):
    if "/outputs" in dirpath.replace("\\\\", "/"):
        continue
    for fn in filenames:
        fp = _o.path.join(dirpath, fn)
        try:
            found[fn] = _o.path.getsize(fp)
        except OSError:
            pass
missing = [n for n in expected if n not in found]
print(_j.dumps({{"found": found, "missing": missing}}, ensure_ascii=False))
""".strip()

ExecuteFn = Callable[..., Awaitable[SandboxResult]]


def load_mount_files(store: FileStore, explicit_ids: list[str] | None = None) -> dict[str, bytes]:
    ids = merge_attachment_ids(explicit_ids)
    files: dict[str, bytes] = {}
    for aid in ids:
        meta = store.get(aid)
        data = store.read_bytes(aid)
        if meta is None or data is None:
            continue
        files[meta.name] = data
    return files


def build_mount_manifest(store: FileStore, mount_files: dict[str, bytes]) -> MountManifest:
    ids = merge_attachment_ids(None)
    id_by_name: dict[str, str] = {}
    for aid in ids:
        meta = store.get(aid)
        if meta is not None:
            id_by_name[meta.name] = aid
    entries: list[MountEntry] = []
    for name, data in mount_files.items():
        guest_path = f"{SANDBOX_MOUNT_ROOT}/{name}"
        entries.append(
            MountEntry(
                path=guest_path,
                name=name,
                size_bytes=len(data),
                attachment_id=id_by_name.get(name, ""),
            )
        )
    return MountManifest(entries=tuple(entries))


async def verify_mount_or_error(
    execute: ExecuteFn,
    *,
    manifest: MountManifest,
    timeout_s: int,
) -> SandboxExecResult | None:
    """Run guest verify script; return structured error result when mounts are missing."""
    if not manifest.entries:
        return None

    verify = await execute(
        MOUNT_VERIFY_SCRIPT.format(
            root=SANDBOX_MOUNT_ROOT,
            expected=[e.name for e in manifest.entries],
        ),
        timeout_s=timeout_s,
    )
    if not verify.success:
        return sandbox_exec_result_from(
            verify,
            error_kind=SandboxErrorKind.MOUNT,
            error_summary=verify.error or "挂载校验执行失败",
            suggested_fix="检查 Onlyboxes worker 与附件是否可读",
            mount_manifest=manifest,
            environment_ready=False,
        )
    try:
        payload: dict[str, Any] = json.loads(verify.stdout.strip().splitlines()[-1])
        missing = payload.get("missing") or []
    except (json.JSONDecodeError, IndexError, AttributeError):
        missing = ["<parse error>"]
    if missing:
        return SandboxExecResult(
            success=False,
            stdout=verify.stdout,
            stderr=verify.stderr,
            exit_code=1,
            error="mount verification failed",
            error_kind=SandboxErrorKind.MOUNT,
            error_summary=f"预期挂载缺失: {missing}",
            suggested_fix="确认 run 附件已上传；路径为 /mnt/data/<原文件名>",
            mount_manifest=manifest,
            environment_ready=False,
        )
    return None
