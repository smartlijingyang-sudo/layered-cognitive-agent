from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from lca.infrastructure.computer.companion.client import (
    CompanionClient,
    CompanionConfig,
    is_process_alive,
)


def test_is_process_alive_with_current_pid() -> None:
    import os

    assert is_process_alive(os.getpid()) is True
    assert is_process_alive(-1) is False
    assert is_process_alive(99999999) is False


def test_companion_state_written_on_startup(tmp_path: Path) -> None:
    state_file = tmp_path / "companion_state.json"
    cfg = CompanionConfig(server_url="http://127.0.0.1:8765", token_file=tmp_path / "token.json", state_file=state_file)
    client = CompanionClient(cfg)
    client.write_state(state_file=state_file, pid=12345)

    assert state_file.is_file()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["pid"] == 12345
    assert data["status"] == "running"
    assert data["server_url"] == "http://127.0.0.1:8765"
    assert "started_at" in data


def test_check_existing_instance_active(tmp_path: Path) -> None:
    state_file = tmp_path / "companion_state.json"
    state_file.write_text(json.dumps({"pid": 99999, "status": "running"}), encoding="utf-8")
    cfg = CompanionConfig(server_url="http://127.0.0.1:8765", token_file=tmp_path / "token.json", state_file=state_file)
    client = CompanionClient(cfg)

    with patch("lca.infrastructure.computer.companion.client.is_process_alive", return_value=True):
        assert client.is_another_instance_running(state_file=state_file) is True

    with patch("lca.infrastructure.computer.companion.client.is_process_alive", return_value=False):
        assert client.is_another_instance_running(state_file=state_file) is False


def test_clear_state(tmp_path: Path) -> None:
    state_file = tmp_path / "companion_state.json"
    cfg = CompanionConfig(server_url="http://127.0.0.1:8765", token_file=tmp_path / "token.json", state_file=state_file)
    client = CompanionClient(cfg)
    client.write_state(state_file=state_file, pid=12345)
    assert state_file.is_file()

    client.clear_state(state_file=state_file)
    assert not state_file.is_file()
