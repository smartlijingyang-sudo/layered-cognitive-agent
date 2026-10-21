"""Regression lock: ``POST /runs`` uploads land in the run assistant's workspace.

Workspace SSOT (ADR-0187 / WSOT-08) says uploads belong to
``{assistant_home}/workspace/user/``. The webserver previously stored them
under the process-wide FileStore root that boot resolved from the global
``LCA_ASSISTANT_ID`` default. This test drives ``decode_create_run`` with a
data-URI attachment and asserts the bytes land in the *run assistant's*
workspace while the id-mirror stays readable on the global store.
"""

import base64
from pathlib import Path

import pytest

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    CreateRunRequest,
    decode_create_run,
)


def _clean_lca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LCA_WORKSPACE_ROOT", "LCA_LOCAL_SANDBOX_ROOT", "LCA_ASSISTANT_ID"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_upload_lands_in_run_assistant_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_lca_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))

    global_uploads = tmp_path / "global" / "uploads"
    global_store = LocalFileStore(root=global_uploads)

    csv_bytes = b"product,revenue\nalpha,12000\n"
    b64 = base64.b64encode(csv_bytes).decode()
    body = {
        "assistant_id": "asst_upload",
        "profile": "web-assistant",
        "messages": [
            {
                "role": "user",
                "content": "请读取上传的 CSV",
                "files": [
                    {
                        "name": "sales.csv",
                        "url": f"data:text/csv;base64,{b64}",
                        "mime_type": "text/csv",
                    }
                ],
            }
        ],
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=global_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="local-dev-user",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert decoded.assistant_id == "asst_upload"
    assert len(decoded.attachment_ids) == 1

    owner_workspace = tmp_path / ".lca" / "assistants" / "asst_upload" / "workspace"
    # SSOT: uploads belong to the run assistant's workspace/user/.
    assert (owner_workspace / "user" / "sales.csv").is_file()
    assert (owner_workspace / "user" / "sales.csv").read_bytes() == csv_bytes

    attachment_id = decoded.attachment_ids[0]
    # Mirror stays on the process-wide store so /files/{id} and staging work.
    assert global_store.read_bytes(attachment_id) == csv_bytes
    assert (global_uploads / attachment_id / "blob").read_bytes() == csv_bytes


@pytest.mark.asyncio
async def test_upload_without_assistant_id_keeps_global_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_lca_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))

    global_uploads = tmp_path / "global" / "uploads"
    global_store = LocalFileStore(root=global_uploads)

    b64 = base64.b64encode(b"plain").decode()
    body = {
        "messages": [
            {
                "role": "user",
                "content": "无归属上传",
                "files": [
                    {
                        "name": "note.txt",
                        "url": f"data:text/plain;base64,{b64}",
                        "mime_type": "text/plain",
                    }
                ],
            }
        ]
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=global_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="local-dev-user",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert decoded.assistant_id == ""
    assert len(decoded.attachment_ids) == 1
    # No run assistant: the classic behavior applies (global mirror + its
    # own workspace/user/ under the boot default root).
    assert global_store.read_bytes(decoded.attachment_ids[0]) == b"plain"


@pytest.mark.asyncio
async def test_upload_via_service_wrapped_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The kernel seam wraps the store in FileStoreService; uploads still
    belong to the run assistant while the mirror lands on the wrapped store."""
    _clean_lca_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))

    from lca.infrastructure.capability.files.files import FileStoreService

    global_uploads = tmp_path / "global" / "uploads"
    global_store = LocalFileStore(root=global_uploads)
    service = FileStoreService()
    service.register("app_bootstrap", global_store, activate=True)

    csv_bytes = b"service,ok\n"
    b64 = base64.b64encode(csv_bytes).decode()
    body = {
        "assistant_id": "asst_service",
        "messages": [
            {
                "role": "user",
                "content": "请读取上传",
                "files": [
                    {
                        "name": "svc.csv",
                        "url": f"data:text/csv;base64,{b64}",
                        "mime_type": "text/csv",
                    }
                ],
            }
        ],
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=service,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="local-dev-user",
    )

    assert isinstance(decoded, CreateRunRequest)
    assert len(decoded.attachment_ids) == 1
    owner_workspace = tmp_path / ".lca" / "assistants" / "asst_service" / "workspace"
    assert (owner_workspace / "user" / "svc.csv").read_bytes() == csv_bytes
    assert global_store.read_bytes(decoded.attachment_ids[0]) == csv_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_assistant_id",
    [
        "../asst_admin",
        "../../../../tmp/escape",
        "asst_ok/../x",
        "/abs/path",
        "asst\\..\\escape",
        "..",
        ".hidden",
    ],
)
async def test_upload_with_malicious_assistant_id_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_assistant_id: str
) -> None:
    """Path-traversal assistant ids are rejected before any byte is written.

    ``assistant_id`` joins ``{lca_home}/assistants/<id>/workspace``; an id
    containing ``..`` or path separators must not reach the filesystem
    (cross-assistant contamination / arbitrary-directory write).
    """
    _clean_lca_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))

    global_uploads = tmp_path / "global" / "uploads"
    global_store = LocalFileStore(root=global_uploads)

    b64 = base64.b64encode(b"pwn").decode()
    body = {
        "assistant_id": bad_assistant_id,
        "messages": [
            {
                "role": "user",
                "content": "x",
                "files": [
                    {
                        "name": "pwn.txt",
                        "url": f"data:text/plain;base64,{b64}",
                        "mime_type": "text/plain",
                    }
                ],
            }
        ],
    }

    decoded = await decode_create_run(
        body,
        ctx=None,
        file_store=global_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
        user_id="local-dev-user",
    )

    from starlette.responses import JSONResponse

    assert isinstance(decoded, JSONResponse)
    assert decoded.status_code == 400
    # Nothing was written: no workspace, no mirror, no registry.
    assert global_store.list() == []
    assert not (tmp_path / ".lca" / "assistants" / "asst_admin" / "workspace").exists()
    assert not (tmp_path / "escape" / "workspace").exists()


def test_file_store_mirror_root_fail_soft_on_empty_service(tmp_path: Path) -> None:
    """The mirror-root resolver never raises on a provider-less service."""
    from lca.infrastructure.capability.files.files import FileStoreService
    from lca.infrastructure.file.store import file_store_mirror_root

    service = FileStoreService()
    assert file_store_mirror_root(service) is None

    # A service with an active LocalFileStore resolves to its mirror root.
    store = LocalFileStore(root=tmp_path / "uploads")
    service.register("local", store, activate=True)
    assert file_store_mirror_root(service) == store.root
