"""Tests for assistant standing files endpoints (/v1/assistants/{id}/standing-files)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import setup


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def provide(self, key: str, value: Any) -> None:
        pass

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


def _create_test_app(tmp_path: Any) -> tuple[Starlette, AssistantCatalogImpl, str]:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    import asyncio

    asyncio.run(setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(root=Path(tmp_path) / "assistants")
    app.state.assistant_catalog = catalog

    handle = catalog.create(
        CreateAssistantRequest(
            name="架构小助",
            description="系统架构演化助手",
            template_id="assistant.default",
            seed_user_md="# USER.md\n用户是架构师",
        )
    )
    # Ensure MEMORY.md exists in home
    home = Path(handle.home_path)
    if not (home / "MEMORY.md").is_file():
        (home / "MEMORY.md").write_text("# MEMORY.md\n- 长期记忆初始条目", encoding="utf-8")

    return app, catalog, handle.assistant_id


def test_standing_files_list_returns_four_standing_files(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(f"/v1/assistants/{assistant_id}/standing-files")
    assert response.status_code == 200
    data = response.json()
    assert data["assistant_id"] == assistant_id
    files = data["files"]
    assert len(files) == 4
    filenames = [f["filename"] for f in files]
    assert "IDENTITY.md" in filenames
    assert "SOUL.md" in filenames
    assert "USER.md" in filenames
    assert "MEMORY.md" in filenames

    # 验证元数据字段完整性
    for f in files:
        assert f["filename"] in {"IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md"}
        assert f["path"].endswith(f["filename"])
        assert isinstance(f["size_bytes"], int)
        assert isinstance(f["line_count"], int)
        assert f["content_hash"].startswith("sha256:")
        assert isinstance(f["summary"], str)


def test_standing_file_detail_returns_raw_content(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(f"/v1/assistants/{assistant_id}/standing-files/SOUL.md")
    assert response.status_code == 200
    data = response.json()
    assert data["assistant_id"] == assistant_id
    assert data["filename"] == "SOUL.md"
    assert "content" in data
    assert "# SOUL.md" in data["content"] or "SOUL" in data["content"]
    assert data["content_hash"].startswith("sha256:")


def test_standing_file_detail_disallows_illegal_file(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    # 尝试访问非白名单文件
    response = client.get(f"/v1/assistants/{assistant_id}/standing-files/tools.yaml")
    assert response.status_code in {400, 404}
    assert response.json()["error"]["code"] in {"disallowed_file", "invalid_request", "not_found"}

    # 尝试路径穿越
    response_traversal = client.get(f"/v1/assistants/{assistant_id}/standing-files/..%2F..%2Fetc%2Fpasswd")
    assert response_traversal.status_code in {400, 404}


def test_standing_files_unknown_assistant_returns_404(tmp_path: Any) -> None:
    app, _, _ = _create_test_app(tmp_path)
    client = TestClient(app)

    response = client.get("/v1/assistants/asst_nonexistent/standing-files")
    assert response.status_code == 404
