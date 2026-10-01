# Muse 风格顶栏动态形象、右侧状态抽屉与文件即 SSOT 全屏编辑器实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 为 LCA 建立顶栏居中动态呼吸 Mascot、右侧平滑滑出多 Section 状态抽屉、点击卡片展开全屏沉浸式 Markdown 编辑器，以及基于文件唯一真值源（File as SSOT）与乐观锁防双写踩踏的完整前后端体系。

**Architecture:** 后端在 `lca/plugins/transport/webserver/routes_1/routes_assistants/` 增加 `standing_files.py` 路由，直接与 `AssistantCatalog` 和 Assistant Home 磁盘真值交互，支持强安全文件名白名单与 sha256 乐观锁校验；前端在 `deploy/lobehub/patches/ui/` 实现 `AssistantTopMascot.tsx`、`AssistantStatusDrawer.tsx`、`StandingFileFullscreenEditor.tsx` 独立组件，并由声明式补丁 `assistant_status_drawer.py` 优雅注入 LobeHub 聊天主页。

**Tech Stack:** Python 3.11+, Starlette, Pydantic, TypeScript, React 19, Lucide React, Lobe UI, Tailwind CSS.

---

### Task 1: 后端 REST 契约：查询与单文件读取端点 (`standing_files.py`)

**Files:**
- Create: `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py`
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/router.py`
- Test: `tests/lca_plugins/transport/webserver/test_routes_standing_files.py`
- Does NOT own: 宿主机资产、核心枚举、`AssistantCatalog` 内部实现、前端组件文件 (AP-01)
- Invariants to test:
  - INV-01: 仅允许访问 `IDENTITY.md`、`SOUL.md`、`USER.md`、`MEMORY.md` 4 大白名单文件，任何非法文件名（如 `../../etc/passwd`）返回 400
  - INV-02: 返回的内容必须 100% 逐字等于磁盘真实文件内容，content_hash 必须为标准 sha256 格式 (AP-02)

**Step 1: Write the failing test**

```python
# tests/lca_plugins/transport/webserver/test_routes_standing_files.py
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
    standing_files_list,
    standing_file_detail,
)

def test_standing_files_illegal_filename_rejected():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -v`  
Expected: FAIL with ModuleNotFoundError or 404

**Step 3: Write minimal implementation**

实现 `standing_files_list` 与 `standing_file_detail`，绑定路由并验证白名单防护与真实文件读取。

**Step 4: Run test to verify it passes**

Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/routes_1/routes_assistants/ tests/lca_plugins/transport/webserver/
git commit -m "feat(standing-files): add list and read endpoints for assistant standing files"
```

---

### Task 2: 乐观锁并发写入与 Catalog / user_store 同步端点

**Files:**
- Modify: `lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py`
- Test: `tests/lca_plugins/transport/webserver/test_routes_standing_files.py`
- Does NOT own: 宿主机资产、LobeHub Postgres 表结构、前端组件 (AP-01)
- Invariants to test:
  - INV-03: 当 `expected_hash` 与磁盘实际计算 hash 不符时，必须返回 409 Conflict 并带回当前磁盘内容
  - INV-04: 写入 `SOUL.md`/`IDENTITY.md`/`USER.md` 必须调用 `AssistantCatalog.revise_profile` 更新 revision
  - INV-05: 写入 `USER.md` 时同步更新全局 `user_store.update_user_md` (AP-02)

**Step 1: Write the failing test**

```python
def test_standing_file_optimistic_lock_conflict():
    # 测试携带旧 expected_hash 触发 409 Conflict
    ...

def test_standing_file_write_updates_catalog_and_user_store():
    # 测试成功写盘后 Catalog revision 递增且 user_store 同步
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -k "conflict or updates" -v`  
Expected: FAIL with 405 Method Not Allowed 或尚未实现

**Step 3: Write minimal implementation**

在 `standing_files.py` 中实现 `update_standing_file`，校验 `expected_hash`，调用 Catalog 与 `user_store`。

**Step 4: Run test to verify it passes**

Run: `pytest tests/lca_plugins/transport/webserver/test_routes_standing_files.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/transport/webserver/routes_1/routes_assistants/standing_files.py tests/
git commit -m "feat(standing-files): add optimistic lock update endpoint with catalog sync"
```

---

### Task 3: 前端组件：居中动态呼吸 Mascot (`AssistantTopMascot.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/AssistantTopMascot.tsx`
- Test: `tests/deploy/test_assistant_top_mascot.py`
- Does NOT own: `lobehub-ui/` 源码目录（严禁直接修改，必须通过补丁）、后端 Python 核心逻辑 (AP-01)
- Invariants to test:
  - 组件必须具备平滑呼吸 CSS 动画（gentle breathing keyframes）
  - 点击必须正确触发 `onOpenDrawer` 回调并携带当前 `assistantId` (AP-02)

**Step 1: Write the failing test**

编写单元测试，验证组件语法与关键 DOM 属性。

**Step 2: Run test to verify it fails**

Run: `pytest tests/deploy/test_assistant_top_mascot.py -v`  
Expected: FAIL with FileNotFoundError

**Step 3: Write minimal implementation**

编写 `AssistantTopMascot.tsx`，使用精美 SVG 水豚/灵动吉祥物、动态微浮动与呼吸光圈，展示助理名称与在线状态。

**Step 4: Run test to verify it passes**

Run: `pytest tests/deploy/test_assistant_top_mascot.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/AssistantTopMascot.tsx tests/deploy/
git commit -m "feat(ui): implement dynamic animated mascot component for conversation header"
```

---

### Task 4: 前端组件：右侧多 Section 滑出抽屉 (`AssistantStatusDrawer.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_assistant_status_drawer.py`
- Does NOT own: 宿主机资产、外部样式库、`lobehub-ui/` 源码 (AP-01)
- Invariants to test:
  - 必须提供 `Identity`、`Memory`、`Workspace` 三大横向 Section 切换
  - 必须渲染 4 大 Standing Files 的卡片预览、路径与「全屏编辑」触发入口 (AP-02)

**Step 1: Write the failing test**

**Step 2: Run test to verify it fails**

Run: `pytest tests/deploy/test_assistant_status_drawer.py -v`  
Expected: FAIL

**Step 3: Write minimal implementation**

编写 `AssistantStatusDrawer.tsx`，调用 `/v1/assistants/{id}/standing-files` 拉取数据，支持横向 Tab 切换与卡片化展示。

**Step 4: Run test to verify it passes**

Run: `pytest tests/deploy/test_assistant_status_drawer.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/
git commit -m "feat(ui): implement right-side status drawer with horizontal section cards"
```

---

### Task 5: 前端组件：全屏沉浸式 Markdown 编辑器模态窗 (`StandingFileFullscreenEditor.tsx`)

**Files:**
- Create: `deploy/lobehub/patches/ui/StandingFileFullscreenEditor.tsx`
- Test: `tests/deploy/test_standing_file_fullscreen_editor.py`
- Does NOT own: 宿主机环境、非 UI 代码 (AP-01)
- Invariants to test:
  - 编辑器支持等宽字体、行号显示与 `Ctrl+S` / `Cmd+S` 快捷保存
  - 保存时向后端传递当前加载的 `content_hash`，遇到 409 Conflict 时展示合并冲突警告 (AP-02)

**Step 1: Write the failing test**

**Step 2: Run test to verify it fails**

Run: `pytest tests/deploy/test_standing_file_fullscreen_editor.py -v`  
Expected: FAIL

**Step 3: Write minimal implementation**

编写 `StandingFileFullscreenEditor.tsx`，提供纯文本高效率 Markdown 编辑、全屏视窗、快捷保存与冲突拦截。

**Step 4: Run test to verify it passes**

Run: `pytest tests/deploy/test_standing_file_fullscreen_editor.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/StandingFileFullscreenEditor.tsx tests/deploy/
git commit -m "feat(ui): implement fullscreen monospace markdown editor with optimistic locking"
```

---

### Task 6: 前端补丁挂载与全链路不变量集成测试 (INV-01 ~ INV-06)

**Files:**
- Create: `deploy/lobehub/patches/ui/assistant_status_drawer.py`
- Test: `tests/scenario/test_standing_files_editor_flow.py`
- Does NOT own: 宿主机资产与环境 (AP-01)
- Invariants to test:
  - INV-01 ~ INV-06 全量覆盖通过
  - `patch_lobehub.py` 应用后通过 `check_patch_integrity` byte-identical 检验 (AP-02)

**Step 1: Write the failing test**

编写端到端场景集成测试 `test_standing_files_editor_flow.py`。

**Step 2: Run test to verify it fails**

Run: `pytest tests/scenario/test_standing_files_editor_flow.py -v`  
Expected: FAIL

**Step 3: Write minimal implementation**

编写 `assistant_status_drawer.py` 补丁，挂载 Mascot 与 Drawer 至 LobeHub 聊天视图，应用补丁并校验。

**Step 4: Run test to verify it passes**

Run: `pytest tests/scenario/test_standing_files_editor_flow.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add deploy/lobehub/patches/ui/ tests/scenario/
git commit -m "feat(integration): mount status drawer patch and verify full-flow invariants"
```
