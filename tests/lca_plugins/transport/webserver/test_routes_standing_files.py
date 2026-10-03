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


def _create_test_app(
    tmp_path: Any, *, ensure_memory: bool = True
) -> tuple[Starlette, AssistantCatalogImpl, str]:
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
    # Ensure MEMORY.md exists in home if requested
    home = Path(handle.home_path)
    if ensure_memory and not (home / "MEMORY.md").is_file():
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
    assert len(files) == 5
    filenames = [f["filename"] for f in files]
    assert "IDENTITY.md" in filenames
    assert "SOUL.md" in filenames
    assert "USER.md" in filenames
    assert "AGENTS.md" in filenames
    assert "MEMORY.md" in filenames

    # 验证元数据字段完整性
    for f in files:
        assert f["filename"] in {"IDENTITY.md", "SOUL.md", "USER.md", "AGENTS.md", "MEMORY.md"}
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
    response_traversal = client.get(
        f"/v1/assistants/{assistant_id}/standing-files/..%2F..%2Fetc%2Fpasswd"
    )
    assert response_traversal.status_code in {400, 404}


def test_standing_files_unknown_assistant_returns_404(tmp_path: Any) -> None:
    app, _, _ = _create_test_app(tmp_path)
    client = TestClient(app)

    response = client.get("/v1/assistants/asst_nonexistent/standing-files")
    assert response.status_code == 404


def test_standing_file_update_success(tmp_path: Any) -> None:
    app, catalog, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    # 1. 先读获取当前 hash 与原文
    read_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/SOUL.md")
    assert read_resp.status_code == 200
    current_hash = read_resp.json()["content_hash"]
    original_soul = read_resp.json()["content"]

    # 2. 追加新准则保持 SOUL 完整度要求
    new_content = (
        original_soul + "\n\n- 演化增量：用户是至高第一真理，坚决遵循三原则并持续沉淀知识。"
    )
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/SOUL.md",
        json={"content": new_content, "expected_hash": current_hash, "actor": "user_ui"},
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["assistant_id"] == assistant_id
    assert data["filename"] == "SOUL.md"
    assert data["revision_seq"] >= 1
    assert data["new_hash"].startswith("sha256:")
    assert catalog.get(assistant_id).revision_seq == data["revision_seq"]

    # 3. 验证再次读取与磁盘真值一致
    verify_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/SOUL.md")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["content"] == new_content


def test_standing_file_update_optimistic_lock_conflict(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/SOUL.md",
        json={
            "content": "# 冲突内容",
            "expected_hash": "sha256:wrong_stale_hash",
            "actor": "user_ui",
        },
    )
    assert put_resp.status_code == 409
    err = put_resp.json()["error"]
    assert err["code"] == "conflict"
    assert "current_hash" in err
    assert "current_content" in err


def test_standing_file_update_memory_md_direct_write(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    read_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md")
    assert read_resp.status_code == 200
    current_hash = read_resp.json()["content_hash"]

    new_memory = "# MEMORY.md\n- 用户偏好使用 Rust 和 Python\n- 严禁未经性能评估引入重依赖"
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md",
        json={"content": new_memory, "expected_hash": current_hash},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["filename"] == "MEMORY.md"

    verify_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["content"] == new_memory


class _FakeOwnership:
    def __init__(self, agent_map: dict[str, str], user_assts: dict[str, list[str]]) -> None:
        self._agent_map = agent_map
        self._user_assts = user_assts

    def assistant_id_for_agent(self, agent_id: str) -> str | None:
        return self._agent_map.get(agent_id)

    def assistant_id_for_client(self, user_id: str, client_id: str) -> str | None:
        return None

    def assistant_ids_for(self, user_id: str) -> tuple[str, ...]:
        return tuple(self._user_assts.get(user_id, []))


def test_standing_files_resolve_agent_id_and_inbox(tmp_path: Any) -> None:
    app, _, assistant_id = _create_test_app(tmp_path)
    app.state.assistant_ownership = _FakeOwnership(
        agent_map={"agt_mock_123": assistant_id},
        user_assts={"local-dev-user": [assistant_id]},
    )
    client = TestClient(app)

    # 1. 以 agt_* 请求列表，自动解析为 asst_*
    agt_resp = client.get("/v1/assistants/agt_mock_123/standing-files")
    assert agt_resp.status_code == 200
    data = agt_resp.json()
    assert data["assistant_id"] == assistant_id
    assert len(data["files"]) == 5

    # 2. 以 agt_* 请求单文件，正常返回内容
    agt_file_resp = client.get("/v1/assistants/agt_mock_123/standing-files/SOUL.md")
    assert agt_file_resp.status_code == 200
    assert agt_file_resp.json()["filename"] == "SOUL.md"

    # 3. 以 inbox 请求列表，自动回退到用户的首选助理
    inbox_resp = client.get("/v1/assistants/inbox/standing-files")
    assert inbox_resp.status_code == 200
    inbox_data = inbox_resp.json()
    assert inbox_data["assistant_id"] == assistant_id
    assert len(inbox_data["files"]) == 5


def test_standing_file_memory_md_uninitialized_returns_template_and_supports_initial_write(
    tmp_path: Any,
) -> None:
    """新助理尚未生成 MEMORY.md 时，GET 返回默认模板且状态码为 200，并支持使用模板 hash 首写落盘。"""
    app, catalog, assistant_id = _create_test_app(tmp_path, ensure_memory=False)
    client = TestClient(app)

    spec = catalog.get(assistant_id)
    memory_path = Path(spec.home_path) / "MEMORY.md"
    assert not memory_path.exists(), "新创建助理在磁盘上默认不得存在 MEMORY.md"

    # 1. 列表接口应包含 MEMORY.md 及其模板摘要，不崩溃
    list_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files")
    assert list_resp.status_code == 200
    files_by_name = {f["filename"]: f for f in list_resp.json()["files"]}
    assert "MEMORY.md" in files_by_name
    mem_item = files_by_name["MEMORY.md"]
    assert mem_item["content_hash"].startswith("sha256:")
    assert "长期记忆" in mem_item["summary"]

    # 2. 单文件 GET 请求不报 404，优雅降级返回默认模板
    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["filename"] == "MEMORY.md"
    assert "## Preferences" in get_data["content"]
    assert "## Facts" in get_data["content"]
    template_hash = get_data["content_hash"]
    assert template_hash == mem_item["content_hash"]

    # 3. 基于模板 hash 进行首次持久化写入
    first_memory = (
        "# 长期记忆\n\n"
        "## Preferences\n"
        "- 偏好使用 Python 和 Rust。 This came from user, recorded 2026-10-03.\n\n"
        "## Facts\n"
    )
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md",
        json={"content": first_memory, "expected_hash": template_hash},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["filename"] == "MEMORY.md"

    # 4. 断言磁盘物理文件已被创建落盘
    assert memory_path.is_file()
    assert memory_path.read_text(encoding="utf-8") == first_memory

    # 5. 再次 GET 应返回最新落盘的内容
    verify_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["content"] == first_memory


def test_standing_file_memory_md_initial_write_with_empty_hash_compatibility(
    tmp_path: Any,
) -> None:
    """对于未建物理文件的场景，PUT 同时兼容客户端以空字符串 hash 作为基线的写入。"""
    from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
        sha256_of_str,
    )

    app, catalog, assistant_id = _create_test_app(tmp_path, ensure_memory=False)
    client = TestClient(app)

    spec = catalog.get(assistant_id)
    memory_path = Path(spec.home_path) / "MEMORY.md"
    assert not memory_path.exists()

    custom_content = "# 长期记忆\n- 纯手工新建记忆条目"
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/MEMORY.md",
        json={"content": custom_content, "expected_hash": sha256_of_str("")},
    )
    assert put_resp.status_code == 200
    assert memory_path.is_file()
    assert memory_path.read_text(encoding="utf-8") == custom_content


def test_constitution_template_contains_core_charter() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
        DEFAULT_STANDING_FILE_TEMPLATES,
    )

    template_path = Path("lca/plugins/assistant/templates/CONSTITUTION.md")
    assert template_path.is_file()
    disk_text = template_path.read_text(encoding="utf-8")

    assert "CONSTITUTION.md" in DEFAULT_STANDING_FILE_TEMPLATES
    assert DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"] == disk_text

    assert "Who You Are" in disk_text
    assert "LCA Architecture & Governance Principles" in disk_text
    assert "Assistant Home & Directory Topology" in disk_text
    assert "Runtime Environment & Context Perception" in disk_text
