"""Guest emit() is the single model-visible path projection point.

Every guest computer-op script exits through emit(), so projecting there
covers all current and future guest tools on every plane without
per-script edits (ADR-0121 display/process split).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from lca.infrastructure.computer.guest.json_script import compose_json_script
from lca.infrastructure.computer.guest.preamble import SCRIPT_PRELUDE
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter


@pytest.fixture
def session(tmp_path: Path) -> tuple[LocalSandboxAdapter, str]:
    adapter = LocalSandboxAdapter(root=str(tmp_path / "root"))
    info = asyncio.run(adapter.create_session())
    assert info is not None
    return adapter, info.session_id


def _emit(adapter: LocalSandboxAdapter, session_id: str, body: str):
    script = compose_json_script(SCRIPT_PRELUDE + body, {})
    return asyncio.run(adapter.run_in_session(session_id, script, language="python"))


def _shown(result: object) -> dict:
    assert result.success, result.error
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_emit_projects_whitelisted_path_keys(session) -> None:
    adapter, sid = session
    body = (
        "def main(encoded):\n"
        "    emit({'path': ROOT + '/outputs/a.pdf', 'directoryPath': ROOT,\n"
        "          'files': [{'name': 'a.pdf', 'path': ROOT + '/outputs/a.pdf'}]})\n"
    )
    shown = _shown(_emit(adapter, sid, body))
    assert shown["path"] == "outputs/a.pdf"
    assert shown["directoryPath"] == "."
    assert shown["files"][0]["path"] == "outputs/a.pdf"


def test_emit_leaves_content_and_unknown_keys_untouched(session) -> None:
    adapter, sid = session
    body = (
        "def main(encoded):\n"
        "    emit({'content': ROOT + '/keep me.txt', 'note': 'see ' + ROOT + '/x'})\n"
    )
    shown = _shown(_emit(adapter, sid, body))
    # Non-whitelisted keys keep their raw values, including absolute roots.
    assert shown["content"].startswith("/") and shown["content"].endswith("/keep me.txt")
    assert shown["note"].startswith("see /") and shown["note"].endswith("/x")


def test_emit_keeps_paths_outside_root_absolute(session) -> None:
    adapter, sid = session
    shown = _shown(_emit(adapter, sid, "def main(encoded):\n    emit({'path': '/etc/hosts'})\n"))
    assert shown["path"] == "/etc/hosts"
