"""PR-6: PATCH /v1/assistants/{assistant_id}/profile —— catalog.revise_profile.

Covers the wired handler replacing the 501 stub: an existing assistant's
profile is revised through ``AssistantCatalog.revise_profile`` and a missing
assistant maps to 404 (ADR-0187 §3 D7 fail-closed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.protocols.assistant.catalog import PlanRevision
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError
from lca.plugins.transport.webserver.routes_1.routes_assistants import (
    revise_assistant_profile,
)


class _FakeCatalog:
    """Programmable ``AssistantCatalog`` stand-in on ``request.app.state``."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self.revise_calls: list[tuple[str, Any, str]] = []

    def _home(self, assistant_id: str) -> Path:
        home = self._root / assistant_id
        if not home.is_dir():
            raise AssistantCatalogError(f"assistant home 不存在: {home}")
        return home

    def get(self, assistant_id: str) -> Any:
        class _Spec:
            home_path = str(self._home(assistant_id))

        return _Spec()

    def revise_profile(
        self,
        assistant_id: str,
        patch: Any,
        *,
        actor: str = "system",
    ) -> PlanRevision:
        self.revise_calls.append((assistant_id, patch, actor))
        home = self._home(assistant_id)
        profile_path = home / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if patch.profile_name is not None:
            profile["name"] = patch.profile_name
        if patch.profile_description is not None:
            profile["description"] = patch.profile_description
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=1,
            manifest_digest="sha256:new",
            actor=actor,
            snapshot_path=str(home / "revisions" / "1.json"),
            revised_at="2026-09-19T00:00:00Z",
        )


class _FakeApp:
    def __init__(self, catalog: _FakeCatalog) -> None:
        class _State:
            assistant_catalog = catalog

        self.state = _State()


class _FakeRequest:
    def __init__(
        self,
        body: Any,
        catalog: _FakeCatalog,
        assistant_id: str,
    ) -> None:
        self._body = body
        self.app = _FakeApp(catalog)
        self.method = "PATCH"
        self.path_params = {"assistant_id": assistant_id}

    async def json(self) -> Any:
        return self._body


def _seed_assistant(root: Path, assistant_id: str) -> Path:
    home = root / assistant_id
    home.mkdir(parents=True)
    (home / "profile.json").write_text(
        json.dumps({"name": "旧名", "description": "旧描述", "status": "active"}),
        encoding="utf-8",
    )
    return home


class TestReviseAssistantProfile:
    @pytest.mark.anyio
    async def test_patch_profile_revises(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        assistant_id = "asst_1"
        _seed_assistant(tmp_path, assistant_id)
        req = _FakeRequest(
            {"profile_name": "新名", "profile_description": "新描述"},
            catalog,
            assistant_id,
        )
        resp = await revise_assistant_profile(req)

        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert body["assistant_id"] == assistant_id
        assert body["revision_seq"] == 1
        assert body["manifest_digest"] == "sha256:new"
        assert body["actor"] == "system"
        assert body["profile"]["name"] == "新名"
        assert body["profile"]["description"] == "新描述"

        revised_id, patch, actor = catalog.revise_calls[0]
        assert revised_id == assistant_id
        assert patch.profile_name == "新名"
        assert patch.profile_description == "新描述"
        assert actor == "system"

    @pytest.mark.anyio
    async def test_patch_profile_actor_passthrough(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        assistant_id = "asst_1"
        _seed_assistant(tmp_path, assistant_id)
        req = _FakeRequest(
            {"profile_name": "新名", "actor": "user:demo"},
            catalog,
            assistant_id,
        )
        resp = await revise_assistant_profile(req)

        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert body["actor"] == "user:demo"
        assert catalog.revise_calls[0][2] == "user:demo"

    @pytest.mark.anyio
    async def test_patch_profile_missing_assistant_404(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        req = _FakeRequest(
            {"profile_name": "新名"},
            catalog,
            "asst_missing",
        )
        resp = await revise_assistant_profile(req)

        assert resp.status_code == 404
        body = json.loads(resp.body)
        assert body["error"]["code"] == "assistant_not_found"

    @pytest.mark.anyio
    async def test_patch_profile_unknown_field_400(self, tmp_path: Path) -> None:
        catalog = _FakeCatalog(tmp_path)
        assistant_id = "asst_1"
        _seed_assistant(tmp_path, assistant_id)
        req = _FakeRequest({"profile_nam": "typo"}, catalog, assistant_id)
        resp = await revise_assistant_profile(req)

        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body["error"]["code"] == "invalid_request"
