"""Regression test: ``build_cloud_sandbox_prompt`` must emit ``<uploaded_files>`` even
when called without an explicit ``store=`` kwarg.

Trace reference: ``run_75e88a76899b`` — user asked "这是什么文件" about an uploaded
``Clash_1752915628.yaml``. The previous implementation gated the cloud branch on
``store is not None``, so the reasoner produced a system prompt with neither
``<files_info>`` nor ``<uploaded_files>``; the model then re-used the
``/files/<attachment_id>`` download URL as a guest path and ``readFile`` failed
with ``not a file``.

This test guards against that regression by binding the run-scope ambient
store (the only thing the reasoner code path has access to) and asserting
the rendered block carries the exact sandbox guest path.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.core.file_ref import FileRef
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.attachment.run_file_store_scope import run_file_store_scope
from lca.infrastructure.attachment.system_role_renderer import render_system_role
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.tools.run_attachment_scope import run_attachment_scope


def _first_id(store: LocalFileStore) -> str:
    for k in store._root.iterdir():  # type: ignore[attr-defined]
        return k.name
    raise AssertionError("store empty")


def test_trace_run_75e88a76899b_does_not_recur(tmp_path: Path) -> None:
    store = LocalFileStore(root=tmp_path)
    store.put(
        data=b"port: 7890\nproxies:\n  - name: alpha\n",
        name="Clash_1752915628.yaml",
        mime_type="text/plain",
    )
    aid = _first_id(store)
    with run_file_store_scope(store), run_attachment_scope([aid]):
        result = render_system_role(
            plane=PlaneRef(
                id="sb",
                label="sb",
                kind=PlaneKind.SANDBOX,
                root="/mnt/data",
                outputs_dir="/mnt/data/outputs",
            ),
            template_name="cloud_sandbox_system_role",
        )
    # The exact failure mode from the trace: nothing about the file's location
    # was present in the system prompt.
    assert "Clash_1752915628.yaml" in result.text, (
        "system role did not list the uploaded file's guest path"
    )
    # The model's known working path under Onlyboxes: ``/mnt/data/<name>``.
    assert "/mnt/data/Clash_1752915628.yaml" in result.text
    # And the renderer gave back a typed FileRef for the journal.
    assert any(
        isinstance(r, FileRef) and r.process_path == "/mnt/data/Clash_1752915628.yaml"
        for r in result.refs_rendered
    )
