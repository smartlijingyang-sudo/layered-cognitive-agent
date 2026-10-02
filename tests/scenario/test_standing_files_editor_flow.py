"""Comprehensive E2E scenario tests for standing files editor and status drawer flow.

Covers INV-01 ~ INV-06:
- INV-01: Whitelist restriction (IDENTITY.md, SOUL.md, USER.md, MEMORY.md only; directory traversal rejected)
- INV-02: Exact byte-level roundtrip parity with disk truth; standard sha256 hash prefix
- INV-03: Concurrency optimistic lock conflict handling (409 Conflict with current content)
- INV-04: Revision sequence increment on Catalog profile writes
- INV-05: user_store.update_user_md synchronization on USER.md edit
- INV-06: Declarative patch integrity (check_patch_integrity exits with code 0)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
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


class _FakeUserStore:
    def __init__(self) -> None:
        self.records: dict[str, str] = {}

    def update_user_md(self, user_id: str, content: str) -> None:
        self.records[user_id] = content


def _create_app_with_user_store(
    tmp_path: Path,
) -> tuple[Starlette, AssistantCatalogImpl, _FakeUserStore, str]:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(setup.setup(ctx, None))

    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(root=tmp_path / "assistants")
    user_store = _FakeUserStore()

    app.state.assistant_catalog = catalog
    app.state.user_store = user_store

    handle = catalog.create(
        CreateAssistantRequest(
            name="架构小助",
            description="系统架构演化助手",
            template_id="assistant.default",
            seed_user_md="# USER.md\n用户是高级系统架构师",
        )
    )
    home = Path(handle.home_path)
    if not (home / "MEMORY.md").is_file():
        (home / "MEMORY.md").write_text("# MEMORY.md\n- 记忆基线事实", encoding="utf-8")

    return app, catalog, user_store, handle.assistant_id


def test_inv01_whitelist_disallows_illegal_files_and_traversal(tmp_path: Path) -> None:
    app, _, _, assistant_id = _create_app_with_user_store(tmp_path)
    client = TestClient(app)

    # 1. 尝试读取非白名单文件
    resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/tools.yaml")
    assert resp.status_code in {400, 404}
    assert resp.json()["error"]["code"] in {"disallowed_file", "invalid_request", "not_found"}

    # 2. 尝试读取路径穿越
    resp_traversal = client.get(
        f"/v1/assistants/{assistant_id}/standing-files/..%2F..%2Fetc%2Fpasswd"
    )
    assert resp_traversal.status_code in {400, 404}

    # 3. 尝试更新非白名单文件
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/sensitive.env",
        json={"content": "SECRET=123"},
    )
    assert put_resp.status_code == 400
    assert put_resp.json()["error"]["code"] == "disallowed_file"


def test_inv02_content_parity_and_standard_sha256_hash(tmp_path: Path) -> None:
    app, _, _, assistant_id = _create_app_with_user_store(tmp_path)
    client = TestClient(app)

    for filename in ("IDENTITY.md", "SOUL.md", "USER.md", "AGENTS.md", "MEMORY.md"):
        resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/{filename}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["filename"] == filename
        disk_path = Path(data["path"])
        assert disk_path.is_file()
        assert disk_path.read_text(encoding="utf-8") == data["content"]

        # Hash 校验
        content_hash = data["content_hash"]
        assert content_hash.startswith("sha256:")
        assert len(content_hash) == 7 + 64


def test_inv03_optimistic_concurrency_conflict_defense(tmp_path: Path) -> None:
    app, _, _, assistant_id = _create_app_with_user_store(tmp_path)
    client = TestClient(app)

    # 1. 获取当前最新 hash
    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/IDENTITY.md")
    assert get_resp.status_code == 200
    current_hash = get_resp.json()["content_hash"]
    current_content = get_resp.json()["content"]

    # 2. 携带过期（过时）hash 尝试保存
    conflict_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/IDENTITY.md",
        json={
            "content": "# 篡改内容",
            "expected_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        },
    )
    assert conflict_resp.status_code == 409
    err = conflict_resp.json()["error"]
    assert err["code"] == "conflict"
    assert err["type"] == "optimistic_lock_conflict"
    assert err["current_hash"] == current_hash
    assert err["current_content"] == current_content


def test_inv04_catalog_revision_increments_on_standing_file_write(tmp_path: Path) -> None:
    app, catalog, _, assistant_id = _create_app_with_user_store(tmp_path)
    client = TestClient(app)

    # 1. 读取初始 revision
    initial_seq = catalog.get(assistant_id).revision_seq

    # 2. 更新 IDENTITY.md
    read_id = client.get(f"/v1/assistants/{assistant_id}/standing-files/IDENTITY.md")
    assert read_id.status_code == 200
    id_hash = read_id.json()["content_hash"]
    new_identity = "# 架构小助 2.0\n定位：高级演化架构师。"

    put_id = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/IDENTITY.md",
        json={"content": new_identity, "expected_hash": id_hash},
    )
    assert put_id.status_code == 200
    assert put_id.json()["revision_seq"] == initial_seq + 1
    assert catalog.get(assistant_id).revision_seq == initial_seq + 1

    # 3. 更新 AGENTS.md
    read_agents = client.get(f"/v1/assistants/{assistant_id}/standing-files/AGENTS.md")
    assert read_agents.status_code == 200
    agents_hash = read_agents.json()["content_hash"]
    new_agents = "# AGENTS.md\n- 沉淀血训：杜绝硬编码"

    put_agents = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/AGENTS.md",
        json={"content": new_agents, "expected_hash": agents_hash},
    )
    assert put_agents.status_code == 200
    assert put_agents.json()["revision_seq"] == initial_seq + 2
    assert catalog.get(assistant_id).revision_seq == initial_seq + 2


def test_inv05_user_md_write_syncs_with_global_user_store(tmp_path: Path) -> None:
    app, _, user_store, assistant_id = _create_app_with_user_store(tmp_path)
    client = TestClient(app)

    read_user = client.get(f"/v1/assistants/{assistant_id}/standing-files/USER.md")
    assert read_user.status_code == 200
    user_hash = read_user.json()["content_hash"]

    new_user_md = "# USER.md\n用户是李超，核心技术栈为 Python 和 Rust。"
    put_user = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/USER.md",
        headers={"x-lca-user-id": "user_lichao_001"},
        json={"content": new_user_md, "expected_hash": user_hash},
    )
    assert put_user.status_code == 200

    # 验证 user_store 已同步更新
    assert user_store.records.get("user_lichao_001") == new_user_md


def test_inv06_patch_integrity_and_declarative_contracts() -> None:
    res = subprocess.run(
        [sys.executable, "scripts/check_patch_integrity.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"check_patch_integrity failed:\n{res.stdout}\n{res.stderr}"
    assert "all source / deployed / byte-identical" in res.stdout
