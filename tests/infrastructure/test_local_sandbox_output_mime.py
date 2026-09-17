"""Harvested local-sandbox outputs carry their real MIME type.

``LocalSandboxAdapter._collect_outputs`` used to stamp every harvested file
``application/octet-stream``, so a PDF written to ``outputs/`` reached the
FileStore with ``previewable=False`` and the UI offered a generic blob
instead of a PDF. The shared harvest helper (``sandbox/output/collect.py``,
already used by the Onlyboxes adapter) guesses the type and applies the
generated-file caps.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.core.state.guest_layout import GuestLayout
from lca.infrastructure.file.store import LocalFileStore, persist_generated_files
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter


@pytest.mark.asyncio
async def test_harvested_pdf_is_stored_as_a_previewable_pdf(tmp_path) -> None:
    root = tmp_path / "mnt"
    root.mkdir()
    adapter = LocalSandboxAdapter(root=str(root), layout=GuestLayout.from_root(str(root)))
    session = await adapter.create_session()
    assert session is not None

    result = await adapter.run_terminal(
        "mkdir -p outputs && echo pdf-bytes > outputs/订单宝_倒排任务表.pdf",
        session_id=session.session_id,
    )
    assert result.success, f"{result.exit_code} {result.stderr} {result.error}"

    harvested = next(f for f in result.generated_files if f.name.endswith(".pdf"))
    assert harvested.mime_type == "application/pdf"

    store = LocalFileStore(root=tmp_path / "files")
    parts = persist_generated_files(store, (harvested,))

    assert parts[0]["mimeType"] == "application/pdf"
    assert parts[0]["previewable"] is True
    assert parts[0]["url"] == f"/files/{parts[0]['attachmentId']}"
