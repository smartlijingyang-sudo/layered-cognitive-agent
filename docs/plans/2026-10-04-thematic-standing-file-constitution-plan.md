# 智能体根本宪法 Standing File (`CONSTITUTION.md`) 实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 在 LCA 架构中全量落地最高级别常驻文件 `CONSTITUTION.md`（根本宪法与行为契约），打通从底层布局、后端路由、模板物化、上下文装配到前端 LobeHub UI 卡片全屏编辑的全链路闭环。

**Architecture:** 
1. 基础设施层：扩展 `layout.toml` 与 `layout.py` 白名单，将 `CONSTITUTION.md` 作为 `standing_files` 首位核心宪章；
2. 传输层与持久化：在 `standing_files.py` 注册白名单与完整默认模板，支持 GET 优雅降级与 PUT 乐观锁原子落盘；
3. 模板与物化：在 `lca/plugins/assistant/templates/CONSTITUTION.md` 物化权威基座，并同步为现有助理落盘；
4. 前端展示层：在 `AssistantStatusDrawer.tsx` 中注册 `📜 根本宪法` 专属卡片与全屏编辑器；
5. 验证体系：基于 TDD 构建 `test_constitution_standing_file_e2e.py`，全量覆盖 INV-CONST-01 至 INV-CONST-06。

**Tech Stack:** Python 3.12, Starlette/FastAPI, Pydantic, TypeScript/React (LobeHub patch), Pytest.

---

### Task 1: 拓扑与契约层扩展 (`layout.toml` & `layout.py`)

**Files:**
- Modify: `lca/infrastructure/memory/contextfiles/layout.toml`
- Modify: `lca/infrastructure/memory/contextfiles/domain/layout.py`
- Test: `tests/infrastructure/memory/contextfiles/test_layout.py`
- Does NOT own: `standing_files.py`, `AssistantStatusDrawer.tsx`, 宿主机资产
- Invariants to test: `INV-CONST-01`（`CONSTITUTION.md` 处于 `standing_files` 首位，且 `packaged_layout()` 正确解析）

**Step 1: 编写失败测试**
在 `tests/infrastructure/memory/contextfiles/test_layout.py` 中增加断言：
```python
def test_constitution_md_is_first_standing_file():
    layout = packaged_layout()
    assert layout.standing_files[0] == "CONSTITUTION.md"
    assert "CONSTITUTION.md" in layout.standing_files
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/infrastructure/memory/contextfiles/test_layout.py -k test_constitution_md_is_first_standing_file -v`
Expected: FAIL（首项当前为 `SOUL.md`）

**Step 3: 实现最小代码**
1. 在 `lca/infrastructure/memory/contextfiles/layout.toml` 的 `standing_files` 最首行插入 `"CONSTITUTION.md"`；
2. 检查 `domain/layout.py` 确保白名单和路径校验放行 `CONSTITUTION.md`。

**Step 4: 运行测试验证通过**
Run: `pytest tests/infrastructure/memory/contextfiles/test_layout.py -v`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/infrastructure/memory/contextfiles/layout.toml lca/infrastructure/memory/contextfiles/domain/layout.py tests/infrastructure/memory/contextfiles/test_layout.py
git commit -m "feat(layout): register CONSTITUTION.md at the head of standing_files"
```

---

### Task 2: 模板基座物化与默认模板注入 (`templates/` & `standing_files.py`)

**Files:**
- Create: `lca/plugins/assistant/templates/CONSTITUTION.md`
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py`
- Test: `tests/lca_plugins/assistant/test_templates.py` (或对应模板单测)
- Does NOT own: UI 补丁, 外部资产
- Invariants to test: 模板包含完整六维价值、LCA 四大特色、目录拓扑与时间真值，且 `DEFAULT_STANDING_FILE_TEMPLATES` 包含一致文本

**Step 1: 编写失败测试**
在单测中增加对 `DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"]` 的内容健全性测试：
```python
def test_constitution_template_contains_core_charter():
    from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import DEFAULT_STANDING_FILE_TEMPLATES
    text = DEFAULT_STANDING_FILE_TEMPLATES.get("CONSTITUTION.md", "")
    assert "Who You Are" in text
    assert "LCA Architecture & Governance Principles" in text
    assert "Assistant Home & Directory Topology" in text
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -k test_constitution_template -v`
Expected: FAIL（未定义 `CONSTITUTION.md` 模板）

**Step 3: 实现最小代码**
1. 落地 `lca/plugins/assistant/templates/CONSTITUTION.md`，写入经过审批的完整权威文本；
2. 在 `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py` 的 `DEFAULT_STANDING_FILE_TEMPLATES` 中注入该文本。

**Step 4: 运行测试验证通过**
Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -k test_constitution_template -v`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/plugins/assistant/templates/CONSTITUTION.md lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py
git commit -m "feat(templates): add authoritative CONSTITUTION.md template and fallback string"
```

---

### Task 3: 传输层路由白名单、优雅降级与乐观锁 (`standing_files.py`)

**Files:**
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py`
- Test: `tests/lca_plugins/transport/webserver/test_routes_standing_files.py`
- Does NOT own: 前端 UI 补丁, 外部资产
- Invariants to test: `INV-CONST-02`, `INV-CONST-03`, `INV-CONST-04`

**Step 1: 编写失败测试**
在 `test_routes_standing_files.py` 中增加用例：
```python
def test_constitution_standing_file_endpoints(client, assistant_id):
    # 1. 列表包含 CONSTITUTION.md
    list_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files")
    assert any(f["filename"] == "CONSTITUTION.md" for f in list_resp.json()["files"])

    # 2. 未建盘时降级返回 200 与模板哈希 (INV-CONST-03)
    get_resp = client.get(f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md")
    assert get_resp.status_code == 200
    assert "Who You Are" in get_resp.json()["content"]

    # 3. 携带模板哈希更新写入 (INV-CONST-04)
    h = get_resp.json()["hash"]
    put_resp = client.put(
        f"/v1/assistants/{assistant_id}/standing-files/CONSTITUTION.md",
        json={"content": "# Custom Constitution\n", "expected_hash": h}
    )
    assert put_resp.status_code == 200
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -k test_constitution_standing_file_endpoints -v`
Expected: FAIL（白名单未放行）

**Step 3: 实现最小代码**
1. 将 `"CONSTITUTION.md"` 加入 `STANDING_FILES_WHITELIST`；
2. 确保 `update_standing_file` 直接写盘机制兼容 `CONSTITUTION.md`。

**Step 4: 运行测试验证通过**
Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -v`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py tests/lca_plugins/transport/webserver/test_routes_standing_files.py
git commit -m "feat(routes): whitelist CONSTITUTION.md with optimistic concurrency and fallback"
```

---

### Task 4: 前端 UI 补丁与卡片元数据 (`AssistantStatusDrawer.tsx`)

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_assistant_status_drawer.py`
- Does NOT own: 后端路由, 宿主机资产
- Invariants to test: `INV-CONST-05`（`FILE_ROLE_METADATA` 注册 `CONSTITUTION.md`，patch_lobehub 成功应用且一致）

**Step 1: 编写失败测试**
在 `tests/deploy/test_assistant_status_drawer.py` 中增加断言：
```python
def test_constitution_card_metadata():
    content = Path("deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx").read_text(encoding="utf-8")
    assert "'CONSTITUTION.md': { label: '根本宪法', icon: '📜', tagColor: 'purple' }" in content
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/deploy/test_assistant_status_drawer.py -k test_constitution_card_metadata -v`
Expected: FAIL

**Step 3: 实现最小代码**
1. 修改 `AssistantStatusDrawer.tsx`，在 `FILE_ROLE_METADATA` 中新增：
   `'CONSTITUTION.md': { label: '根本宪法', icon: '📜', tagColor: 'purple' }`
   并将 `'SOUL.md'` 调整为 `{ label: '角色灵魂', icon: '🌟', tagColor: 'gold' }`；
2. 执行 `python3 deploy/lobehub/patch_lobehub.py` 应用前端补丁并校验。

**Step 4: 运行测试验证通过**
Run: `pytest tests/deploy/test_assistant_status_drawer.py -v`
Run: `python3 deploy/lobehub/check_patch_integrity.py`
Expected: PASS

**Step 5: 提交**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_assistant_status_drawer.py
git commit -m "feat(ui): add CONSTITUTION.md card metadata in AssistantStatusDrawer"
```

---

### Task 5: 上下文装配、活跃助理物化与全链路集成验收

**Files:**
- Create: `tests/scenario/test_constitution_standing_file_e2e.py`
- Synchronize: 为活跃助理 `asst_29c963417967` 物化 `CONSTITUTION.md`
- Does NOT own: 宿主机资产, 外部代码库
- Invariants to test: `INV-CONST-01` ~ `INV-CONST-06` 全量端到端验证

**Step 1: 编写全链路端到端符合性测试**
创建 `tests/scenario/test_constitution_standing_file_e2e.py`：
- 验证布局解析首位为 `CONSTITUTION.md` (INV-CONST-01)；
- 验证 HTTP 接口白名单与 404/403 防御 (INV-CONST-02)；
- 验证未建盘物理文件时 200 降级与哈希 (INV-CONST-03)；
- 验证 PUT 乐观锁初次写入与冲突 409 (INV-CONST-04)；
- 验证 UI 补丁与元数据完整性 (INV-CONST-05)；
- 验证 `refresh_standing_backstory` 生成的 Backstory 包含 `<!-- INJECTED FILE: CONSTITUTION.md -->` 且排在首位 (INV-CONST-06)。

**Step 2: 运行测试验证**
Run: `pytest tests/scenario/test_constitution_standing_file_e2e.py -v`
Expected: PASS

**Step 3: 物化活跃助理文件并执行全套质量门禁**
1. 为活跃助理 `asst_29c963417967` 写入权威 `CONSTITUTION.md`；
2. 运行 `ruff check` 与 `ruff format --check`；
3. 运行 `git diff --check`。

**Step 4: 提交**
```bash
git add tests/scenario/test_constitution_standing_file_e2e.py
git commit -m "test(scenario): add E2E conformance tests for CONSTITUTION.md standing file"
```
