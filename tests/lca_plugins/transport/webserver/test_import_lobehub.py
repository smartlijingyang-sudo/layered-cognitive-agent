"""Tests for POST /v1/assistants/import-lobehub endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.plugins.transport.webserver.routes_1.routes_assistants import (
    import_lobehub_agent,
    _extract_emoji,
)


class _FakeCatalog:
    def __init__(self, tmp_path: Path) -> None:
        self._root = tmp_path
        self._counter = 0

    def create(self, req: Any) -> Any:
        self._counter += 1
        asst_id = f"asst_{self._counter:012x}"
        home = self._root / asst_id
        home.mkdir(parents=True)
        (home / "profile.json").write_text(
            json.dumps({"name": req.name, "description": req.description, "emoji": "🤖", "status": "active"}),
            encoding="utf-8",
        )
        (home / "SOUL.md").write_text("# SOUL\n\nDefault soul.", encoding="utf-8")
        (home / "USER.md").write_text("# USER\n", encoding="utf-8")
        (home / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        (home / "goals.yaml").write_text("goals: []\n", encoding="utf-8")
        (home / "grants.yaml").write_text("grants: []\n", encoding="utf-8")
        (home / "tools.yaml").write_text("tools:\n  allow: []\n", encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "assistant_id": asst_id,
            "template_id": "assistant.default",
            "revision_seq": 0,
            "digests": {},
            "manifest_digest": "sha256:fake",
            "created_at": "2026-01-01T00:00:00Z",
        }
        (home / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        class _Handle:
            assistant_id = asst_id
            home_path = str(home)
            revision_seq = 0

        return _Handle()


class _FakeApp:
    def __init__(self, catalog: _FakeCatalog) -> None:
        class _State:
            assistant_catalog = catalog

        self.state = _State()


class _FakeRequest:
    def __init__(self, body: Any, catalog: _FakeCatalog) -> None:
        self._body = body
        self.app = _FakeApp(catalog)
        self.method = "POST"
        self.path_params: dict = {}

    async def json(self) -> Any:
        return self._body


class TestExtractEmoji:
    def test_empty_returns_empty(self) -> None:
        assert _extract_emoji("") == ""

    def test_url_returns_empty(self) -> None:
        assert _extract_emoji("https://example.com/avatar.png") == ""

    def test_short_string_returns_as_is(self) -> None:
        assert _extract_emoji("🤖") == "🤖"

    def test_long_string_returns_empty(self) -> None:
        assert _extract_emoji("some long text") == ""


class TestImportLobeHubAgent:
    @pytest.mark.anyio
    async def test_import_basic(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        body = {
            "title": "Test Agent",
            "description": "A test agent",
            "avatar": "🧪",
            "systemRole": "You are a test agent. Be helpful.",
        }
        req = _FakeRequest(body, catalog)
        resp = await import_lobehub_agent(req)
        assert resp.status_code == 201

        data = json.loads(resp.body)
        assert data["assistant_id"].startswith("asst_")
        assert data["source"] == "lobehub"

        home = Path(data["home_path"])
        soul = (home / "SOUL.md").read_text(encoding="utf-8")
        assert "test agent" in soul

        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
        assert profile["emoji"] == "🧪"
        assert profile["source"] == "lobehub"

    @pytest.mark.anyio
    async def test_import_without_system_role(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        body = {"title": "Simple Agent", "description": "No system role"}
        req = _FakeRequest(body, catalog)
        resp = await import_lobehub_agent(req)
        assert resp.status_code == 201

    @pytest.mark.anyio
    async def test_import_missing_title_returns_400(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        body = {"description": "No title"}
        req = _FakeRequest(body, catalog)
        resp = await import_lobehub_agent(req)
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_import_url_avatar_ignored(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        body = {
            "title": "URL Avatar",
            "avatar": "https://example.com/avatar.png",
            "systemRole": "Test",
        }
        req = _FakeRequest(body, catalog)
        resp = await import_lobehub_agent(req)
        assert resp.status_code == 201
        data = json.loads(resp.body)
        home = Path(data["home_path"])
        profile = json.loads((home / "profile.json").read_text(encoding="utf-8"))
        assert profile["emoji"] == "🤖"
