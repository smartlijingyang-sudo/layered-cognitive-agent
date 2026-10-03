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
# ---------------------------------------------------------------------------
# WSOT-07: per-run assistant resolution — the run's assistant wins over the
# global LCA_ASSISTANT_ID default; other assistants are never pointed at the
# default assistant's workspace.
# ---------------------------------------------------------------------------

def test_ssot_run_assistant_beats_global_default(monkeypatch, tmp_path):
    """run 作用域绑定的 assistant 优先于全局 LCA_ASSISTANT_ID 默认值。"""
    from lca.infrastructure.path.locator import assistant_workspace_root
    from lca.infrastructure.tools.run.assistant_scope import run_assistant_scope

    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    monkeypatch.delenv("LCA_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("LCA_LOCAL_SANDBOX_ROOT", raising=False)
    monkeypatch.setenv("LCA_ASSISTANT_ID", "asst_default")

    with run_assistant_scope("asst_other"):
        root = assistant_workspace_root()
    assert root == tmp_path / "assistants" / "asst_other" / "workspace"
    assert "asst_default" not in str(root)


def test_ssot_explicit_arg_still_wins_over_run_scope(monkeypatch, tmp_path):
    """显式参数仍高于 run 作用域。"""
    from lca.infrastructure.path.locator import assistant_workspace_root
    from lca.infrastructure.tools.run.assistant_scope import run_assistant_scope

    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    monkeypatch.delenv("LCA_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("LCA_LOCAL_SANDBOX_ROOT", raising=False)
    monkeypatch.delenv("LCA_ASSISTANT_ID", raising=False)

    with run_assistant_scope("asst_run"):
        root = assistant_workspace_root("asst_explicit")
    assert root == tmp_path / "assistants" / "asst_explicit" / "workspace"


def test_ssot_no_run_scope_falls_back_to_env_default(monkeypatch, tmp_path):
    """无 run 作用域时回退到 LCA_ASSISTANT_ID 全局默认（CLI/测试场景）。"""
    from lca.infrastructure.path.locator import assistant_workspace_root
    from lca.infrastructure.tools.run.assistant_scope import (
        get_current_assistant_id,
    )

    monkeypatch.setenv("LCA_HOME", str(tmp_path))
    monkeypatch.delenv("LCA_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("LCA_LOCAL_SANDBOX_ROOT", raising=False)
    monkeypatch.setenv("LCA_ASSISTANT_ID", "asst_default")

    assert get_current_assistant_id() == ""
    root = assistant_workspace_root()
    assert root == tmp_path / "assistants" / "asst_default" / "workspace"


def test_ssot_assistant_scope_is_run_local():
    """作用域退出后恢复；嵌套覆盖按栈语义。"""
    from lca.infrastructure.tools.run.assistant_scope import (
        get_current_assistant_id,
        run_assistant_scope,
    )

    assert get_current_assistant_id() == ""
    with run_assistant_scope("asst_a"):
        assert get_current_assistant_id() == "asst_a"
        with run_assistant_scope("asst_b"):
            assert get_current_assistant_id() == "asst_b"
        assert get_current_assistant_id() == "asst_a"
    assert get_current_assistant_id() == ""
