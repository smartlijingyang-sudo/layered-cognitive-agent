"""Tests for ``runs create`` assistant binding (PR-1).

Pins the ``--assistant-id`` plumbing added by PR-1:

- the ``POST /runs`` body carries the passed ``assistant_id`` (and omits
  it when empty, keeping the legacy unbound path byte-identical);
- the ``--facade`` path forwards ``assistant_id`` into ``CliRunArgs``;
- when ``--agent`` maps to an assistant, the body carries the resolved
  ``assistant_id`` (best-effort; unmapped agents stay unbound).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from lca.infrastructure.cli.commands.runs.runs import (
    _build_create_body,
    _resolve_assistant_id,
)

_RUNS_MODULE = "lca.infrastructure.cli.commands.runs.runs"


# ── helpers ─────────────────────────────────────────────────────────


class _FakeResponse:
    """Minimal context-manager stand-in for ``urllib.response``."""

    def __init__(self, payload: dict, status: int = 202) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _register_runs_app() -> typer.Typer:
    from lca.infrastructure.cli.commands.runs.runs import register

    app = typer.Typer()
    register(app)
    return app


def _invoke_create(*args: str):
    """Invoke ``runs create`` on a fresh app and return the result."""
    runner = CliRunner()
    return runner.invoke(_register_runs_app(), ["runs", "create", *args])


# ── body construction ───────────────────────────────────────────────


def test_assistant_id_in_body() -> None:
    """The CLI builds a body containing the passed ``assistant_id``."""
    body = _build_create_body(
        user_text="hello",
        mode="solo",
        agent="agt_agent_x",
        profile="web-standard",
        assistant_id="asst_123",
    )
    assert body["assistant_id"] == "asst_123"
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_assistant_id_omitted_when_empty() -> None:
    """An empty ``assistant_id`` keeps the legacy body shape (no key)."""
    body = _build_create_body(
        user_text="hello",
        mode="solo",
        agent="agt_agent_x",
        profile="web-standard",
        assistant_id=None,
    )
    assert "assistant_id" not in body


# ── facade path ─────────────────────────────────────────────────────


def test_facade_forwards_assistant_id() -> None:
    """The facade path receives the passed assistant id."""
    captured: dict[str, Any] = {}

    def fake_facade(**kwargs: Any) -> None:
        captured.update(kwargs)

    with patch(f"{_RUNS_MODULE}._create_via_facade", side_effect=fake_facade):
        result = _invoke_create(
            "--facade",
            "--user-text",
            "hello",
            "--assistant-id",
            "asst_123",
        )
    assert result.exit_code == 0, result.output
    assert captured["assistant_id"] == "asst_123"


# ── agent → assistant resolution ────────────────────────────────────


def test_agent_resolves_to_assistant() -> None:
    """When ``--agent`` maps to an assistant, the body carries the resolved id."""
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: int) -> _FakeResponse:
        del timeout  # carrier timeout is not observable at this seam
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"run_id": "run_1", "trace_id": "trace_1"})

    with (
        patch(f"{_RUNS_MODULE}._resolve_assistant_id", return_value="asst_resolved"),
        patch(f"{_RUNS_MODULE}.urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        result = _invoke_create(
            "--user-text",
            "hello",
            "--agent",
            "agt_agent_x",
            "--json",
            "--no-sop",
        )
    assert result.exit_code == 0, result.output
    assert captured["data"]["assistant_id"] == "asst_resolved"


def test_resolve_assistant_id_explicit_wins() -> None:
    """An explicitly passed ``--assistant-id`` wins over agent resolution."""
    assert _resolve_assistant_id("agt_agent_x", "asst_123") == "asst_123"


def test_resolve_assistant_id_unbound_when_no_mapping() -> None:
    """No agent→assistant mapping ⇒ the run stays unbound (None), not an error."""
    assert _resolve_assistant_id("agt_agent_x", None) is None
