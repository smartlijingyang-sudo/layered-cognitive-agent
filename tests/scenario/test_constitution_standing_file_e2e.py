"""Comprehensive End-to-End Conformance Tests for CONSTITUTION.md Standing File.

Validates all 6 architectural invariants (INV-CONST-01 ~ INV-CONST-06):
- INV-CONST-01: Topological SSOT (CONSTITUTION.md sits at index 0 of standing_files)
- INV-CONST-02: Whitelist Gate (CONSTITUTION.md allowed; arbitrary and traversal paths blocked)
- INV-CONST-03: Graceful Fallback & Template Integrity (GET returns 200 + template + hash before disk write)
- INV-CONST-04: Optimistic Concurrency & Direct Disk Write (Atomic write, 409 conflict, no revision_seq churn)
- INV-CONST-05: UI Card Metadata & Patch Parity (AssistantStatusDrawer.tsx has '📜 根本宪法' card)
- INV-CONST-06: Backstory Ingestion & Context Supremacy (CONSTITUTION.md injected at the head of prompt backstory)
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
from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.service.assembly import refresh_standing_backstory
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import setup
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    DEFAULT_STANDING_FILE_TEMPLATES,
    STANDING_FILES_WHITELIST,
)


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
            seed_user_md="# USER.md\n用户是系统架构师",
        )
    )
    return app, catalog, handle.assistant_id


def test_inv_const_01_topological_ssot() -> None:
    """INV-CONST-01: layout.toml 与 domain.layout 解析中 CONSTITUTION.md 必须处于 standing_files 首位。"""
    layout = packaged_layout()
    assert layout.standing_files[0] == "CONSTITUTION.md"
    assert "CONSTITUTION.md" in layout.standing_files
    assert layout.standing_files.index("CONSTITUTION.md") < layout.standing_files.index("SOUL.md")


def test_inv_const_02_whitelist_gate_and_traversal_defense(tmp_path: Any) -> None:
    """INV-CONST-02: HTTP API 白名单放行 CONSTITUTION.md，非法或越界访问必须被 400/404 拒绝。"""
    assert "CONSTITUTION.md" in STANDING_FILES_WHITELIST
    assert STANDING_FILES_WHITELIST[0] == "CONSTITUTION.md"

    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    # 1. 列表包含 CONSTITUTION.md
    list_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files")
    assert list_resp.status_code == 200
    filenames = [f["filename"] for f in list_resp.json()["files"]]
    assert "CONSTITUTION.md" in filenames

    # 2. 正常读取 CONSTITUTION.md
    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md")
    assert get_resp.status_code == 200

    # 3. 未白名单文件被 400 阻断
    disallowed_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/id_rsa")
    assert disallowed_resp.status_code == 400
    assert disallowed_resp.json()["error"]["code"] == "disallowed_file"

    # 4. 路径遍历被 400/404 拦截
    traversal_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/..%2F..%2Fetc%2Fpasswd")
    assert traversal_resp.status_code in {400, 404}


def test_inv_const_03_graceful_fallback_and_template_integrity(tmp_path: Any) -> None:
    """INV-CONST-03: 物理文件未落盘或被删除时，GET 接口优雅降级返回 200、权威模板完整内容及 sha256 乐观锁哈希。"""
    app, catalog, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    spec = catalog.get(assistant_id)
    const_file = Path(spec.home_path) / "CONSTITUTION.md"
    # 验证 Catalog 脚手架已自动初始化 CONSTITUTION.md
    assert const_file.is_file(), "Catalog 骨架应默认根据模板初始化 CONSTITUTION.md"
    assert const_file.read_text(encoding="utf-8") == DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"]

    # 模拟磁盘文件不存在/未落盘场景，验证优雅降级
    const_file.unlink()
    assert not const_file.exists(), "已模拟物理文件被移除"

    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md")
    assert get_resp.status_code == 200
    payload = get_resp.json()

    assert payload["filename"] == "CONSTITUTION.md"
    content = payload["content"]
    assert content == DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"]

    # 校验零遗漏核心宪章内容
    assert "## Who You Are" in content
    assert "### Truth" in content
    assert "### Beauty" in content
    assert "### Respect" in content
    assert "### Fun" in content
    assert "### Connection" in content
    assert "### Curiosity" in content
    assert "### Due Diligence" in content
    assert "### Who Built You" in content
    assert "### Who You Work For" in content
    assert "### Discretion and Alignment" in content
    assert "### How You Work" in content
    assert "## LCA Architecture & Governance Principles" in content
    assert "## Assistant Home & Directory Topology" in content
    assert "## Runtime Environment & Context Perception" in content

    # 校验哈希格式
    assert payload["content_hash"].startswith("sha256:")
    assert len(payload["content_hash"]) == 7 + 64


def test_inv_const_04_optimistic_concurrency_and_direct_atomic_write(tmp_path: Any) -> None:
    """INV-CONST-04: 乐观锁防并发冲突（409），携带有效哈希执行原子直接落盘，且不改变 catalog revision_seq。"""
    app, catalog, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    spec = catalog.get(assistant_id)
    const_file = Path(spec.home_path) / "CONSTITUTION.md"
    # 模拟从无物理文件开始（删除后首写测试）
    if const_file.exists():
        const_file.unlink()
    initial_seq = spec.revision_seq

    # 1. 尝试使用错误哈希写入，必须返回 409 Conflict
    conflict_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md",
        json={"content": "# Conflict Content", "expected_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000"},
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error"]["code"] == "conflict"
    assert not const_file.exists()

    # 2. 获取初始降级模板哈希
    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md")
    template_hash = get_resp.json()["content_hash"]

    # 3. 携带模板哈希首次保存，落盘成功
    custom_content = (
        "# 根本宪法与行为契约\n\n"
        "## Who You Are\n"
        "You are a friendly and intelligent personal assistant.\n\n"
        "## Core Principles\n"
        "- 独立不变量：真理高于世俗教条\n"
    )
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md",
        json={"content": custom_content, "expected_hash": template_hash},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["filename"] == "CONSTITUTION.md"

    # 4. 验证物理落盘与 revision_seq 不变
    assert const_file.is_file()
    assert const_file.read_text(encoding="utf-8") == custom_content
    assert catalog.get(assistant_id).revision_seq == initial_seq, "CONSTITUTION.md 写入不改变 revision_seq"

    # 5. 再次写入增量内容
    new_hash = put_resp.json()["new_hash"]
    updated_content = custom_content + "- 增量原则：零遗漏与第一性原理\n"
    put_resp2 = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md",
        json={"content": updated_content, "expected_hash": new_hash},
    )
    assert put_resp2.status_code == 200
    assert const_file.read_text(encoding="utf-8") == updated_content


def test_inv_const_05_ui_metadata_and_patch_parity() -> None:
    """INV-CONST-05: 前端 UI 补丁 AssistantStatusDrawer.tsx 包含 '📜 根本宪法' 元数据，且前端 patch 保持完整。"""
    drawer_path = Path("deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx")
    assert drawer_path.is_file()
    content = drawer_path.read_text(encoding="utf-8")
    assert "'CONSTITUTION.md': { label: '根本宪法', icon: '📜', tagColor: 'purple' }" in content

    # 验证补丁应用一致性
    res = subprocess.run(
        [sys.executable, "deploy/lobehub/patch_lobehub.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "done: 0 applied, 45 skipped" in res.stdout


def test_inv_const_06_context_assembly_and_backstory_order(tmp_path: Any) -> None:
    """INV-CONST-06: 上下文组装时，CONSTITUTION.md 必须首位注入在 SOUL.md 前，且未落盘时不注入。"""
    _app, catalog, assistant_id = _create_test_app(tmp_path)
    spec = catalog.get(assistant_id)
    home = Path(spec.home_path)
    const_file = home / "CONSTITUTION.md"

    # 1. 物理文件移除后，Backstory 不注入 CONSTITUTION.md 标记（避免空文件消耗 Token）
    if const_file.exists():
        const_file.unlink()
    cold_backstory = refresh_standing_backstory(str(home), "")
    assert "<!-- INJECTED FILE: CONSTITUTION.md -->" not in cold_backstory

    # 2. 物理文件落盘
    const_file.write_text(DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"], encoding="utf-8")

    # 3. 重新组装 Backstory
    live_backstory = refresh_standing_backstory(str(home), "")
    assert "<!-- INJECTED FILE: CONSTITUTION.md -->" in live_backstory
    assert "<!-- END INJECTED FILE: CONSTITUTION.md -->" in live_backstory
    assert "Who You Are" in live_backstory

    # 4. 验证宪法最高地位：CONSTITUTION.md 处于首位，且在 SOUL.md 之前
    const_idx = live_backstory.index("<!-- INJECTED FILE: CONSTITUTION.md -->")
    if "<!-- INJECTED FILE: SOUL.md -->" in live_backstory:
        soul_idx = live_backstory.index("<!-- INJECTED FILE: SOUL.md -->")
        assert const_idx < soul_idx, "CONSTITUTION.md 必须在 SOUL.md 之前注入"
