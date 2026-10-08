"""Workspace SSOT regression tests.

Covers docs/plans/2026-10-03-workspace-ssot-alignment-plan.md Task 5:
the workspace is a single source of truth — one place decides where it
lives on the host, and uploads land under it with a real conversation_id.
"""

import base64

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
    from lca.plugins.transport.webserver.handlers.runs.ingest import (
        FileRef,
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


def test_wsot08_session_root_follows_run_assistant(monkeypatch, tmp_path):
    """沙箱会话目录落在 run 所属助理的 workspace，不回落到 boot 默认助理。"""
    import asyncio

    from lca.contracts.models.core.execution.sandbox import SessionConfig
    from lca.infrastructure.path.locator import assistant_workspace_root
    from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter
    from lca.infrastructure.tools.run.assistant_scope import run_assistant_scope

    _clean_env(monkeypatch)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))
    monkeypatch.setenv("LCA_ASSISTANT_ID", "asst_boot_default")

    # Constructed outside any run scope, like the boot-time provider does.
    adapter = LocalSandboxAdapter()
    boot_default_ws = tmp_path / ".lca" / "assistants" / "asst_boot_default" / "workspace"
    assert adapter.host_root == str(boot_default_ws)

    with run_assistant_scope("asst_run_owner"):
        config = SessionConfig(workspace_root=str(assistant_workspace_root()))
        info = asyncio.run(adapter.create_session(config))
    assert info is not None
    owner_ws = tmp_path / ".lca" / "assistants" / "asst_run_owner" / "workspace"
    assert (owner_ws / ".sessions" / info.session_id).is_dir()
    assert not (boot_default_ws / ".sessions" / info.session_id).exists()

    # Without the per-run binding the boot default still backs the session.
    fallback = asyncio.run(adapter.create_session())
    assert fallback is not None
    assert (boot_default_ws / ".sessions" / fallback.session_id).is_dir()


def test_wsot09_guest_scripts_honor_session_root(monkeypatch, tmp_path):
    """Local 平面 guest 脚本的 ROOT 跟随会话根，不落宿主字面 /mnt/data；
    展示层按 RA-040 投影回 guest 视图，宿主路径不泄漏。"""
    import asyncio

    from lca.contracts.models.core.execution.sandbox import SessionConfig
    from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter

    _clean_env(monkeypatch)
    adapter = LocalSandboxAdapter(root=str(tmp_path / "host_root"))
    info = asyncio.run(
        adapter.create_session(SessionConfig(workspace_root=str(tmp_path / "owner_ws")))
    )
    assert info is not None
    session_root = tmp_path / "owner_ws" / ".sessions" / info.session_id
    script = (
        "import os\n"
        "from pathlib import Path\n"
        "root = os.environ['LCA_GUEST_ROOT']\n"
        "Path(root).joinpath('probe.txt').write_text('x')\n"
    )
    result = asyncio.run(adapter.run_in_session(info.session_id, script, language="python"))
    assert result.success, result.error
    assert (session_root / "probe.txt").is_file()

    # Composed guest scripts read ROOT from the same env knob.
    from lca.infrastructure.computer.guest.json_script import compose_json_script
    from lca.infrastructure.computer.guest.preamble import SCRIPT_PRELUDE

    composed = compose_json_script(SCRIPT_PRELUDE + "def main(encoded):\n    emit(ROOT)\n", {})
    rooted = asyncio.run(adapter.run_in_session(info.session_id, composed, language="python"))
    assert rooted.success, rooted.error
    # The script itself read the session root (probe.txt above proves the host
    # side); the agent-facing display shows the guest view — the host session
    # path is projected back and never leaks (RA-040).
    assert rooted.stdout.strip().splitlines()[-1].strip('"') == "/mnt/data"
