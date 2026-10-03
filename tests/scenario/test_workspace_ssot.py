"""Workspace SSOT regression tests.

Covers docs/plans/2026-10-03-workspace-ssot-alignment-plan.md Task 5:
the workspace is a single source of truth — one place decides where it
lives on the host, and uploads land under it with a real conversation_id.
"""

import base64
import os

import pytest

from lca.infrastructure.path.locator import assistant_workspace_root


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "LCA_WORKSPACE_ROOT",
        "LCA_LOCAL_SANDBOX_ROOT",
        "LCA_ASSISTANT_ID",
        "LCA_HOME",
    ):
        monkeypatch.delenv(key, raising=False)


def test_wsot01_ssot_explicit_override_wins(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("LCA_ASSISTANT_ID", "asst_should_not_win")
    assert assistant_workspace_root("asst_x") == (tmp_path / "ws").resolve()


def test_wsot01_ssot_legacy_env_backward_compat(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_LOCAL_SANDBOX_ROOT", str(tmp_path / "legacy"))
    assert assistant_workspace_root("asst_x") == (tmp_path / "legacy").resolve()


def test_wsot01_ssot_assistant_home(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))
    expected = tmp_path / ".lca" / "assistants" / "asst_abc" / "workspace"
    assert assistant_workspace_root("asst_abc") == expected
    monkeypatch.setenv("LCA_ASSISTANT_ID", "asst_env")
    assert assistant_workspace_root() == (
        tmp_path / ".lca" / "assistants" / "asst_env" / "workspace"
    )


def test_wsot02_local_adapter_delegates_to_ssot(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from lca.infrastructure.sandbox.local.adapter import default_local_root

    assert default_local_root() == str((tmp_path / "ws").resolve())


def test_wsot03_filestore_default_root_and_list(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from lca.infrastructure.file.store import LocalFileStore

    store = LocalFileStore()
    assert store.root == (tmp_path / "ws" / "uploads").resolve()

    stored = store.put(
        data=b"hello",
        name="a.txt",
        mime_type="text/plain",
        conversation_id="conv_1",
    )
    assert stored.conversation_id == "conv_1"
    assert (store.root / stored.attachment_id / "blob").is_file()

    listed = store.list()
    assert [s.attachment_id for s in listed] == [stored.attachment_id]
    assert listed[0].conversation_id == "conv_1"


def test_wsot04_bootstrap_default_root_under_workspace(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from lca.plugins.transport.webserver.bootstrap.bootstrap import (
        WebserverBootstrapConfig,
    )

    cfg = WebserverBootstrapConfig()
    assert cfg.file_store_root == (tmp_path / "ws" / "uploads").resolve()


async def test_wsot05_ingest_writes_conversation_id(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    from lca.infrastructure.file.store import LocalFileStore
    from lca.plugins.transport.webserver.handlers.runs.ingest.models.models import (
        FileRef,
    )
    from lca.plugins.transport.webserver.handlers.runs.ingest.service.service import (
        ingest_file_refs,
    )

    store = LocalFileStore()
    payload = base64.b64encode(b"ingest-me").decode()
    ref = FileRef(
        name="note.txt",
        url=f"data:text/plain;base64,{payload}",
        mime_type="text/plain",
    )
    result = await ingest_file_refs((ref,), store, conversation_id="topic_9")
    assert len(result.attachment_ids) == 1
    stored = store.get(result.attachment_ids[0])
    assert stored is not None
    assert stored.conversation_id == "topic_9"
    assert store.read_bytes(result.attachment_ids[0]) == b"ingest-me"
