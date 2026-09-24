# Everything Library（个人智库与资源枢纽）Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建一个长期可维护、高颜值、易用且对 Agent 极其友好的个人智库与资源枢纽（`~/everything-library`），支持局域网（`10.36.6.252:1889`）密码访问（`lichao12`）、分类管理、状态流转（待看/Todo/参考）、极速全文搜索与 Awesome 格式导出。

**Architecture:** 采用 **Content as Code (GitOps)** 架构：Markdown + YAML Frontmatter 作为唯一真实数据源（SSOT），本地 SQLite FTS5 充当启动/保存时派生的只读全文检索与聚合索引（Projection）。通过 Python FastAPI 提供强类型 RESTful 接口与现代响应式 Web UI（TailwindCSS + 深浅色切换 + 卡片/列表双视图），完全兼顾人类沉浸交互与 Agent 终端直读/API 操作。

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, PyYAML, SQLite FTS5, TailwindCSS (CDN), Jinja2, Lucide Icons.

---

### Task 1: 初始化 `~/everything-library` Git 仓库与标准目录骨架

**Files:**
- Create: `/home/lichao/everything-library/.git` (via `git init`)
- Create: `/home/lichao/everything-library/data/categories.yaml`
- Create: `/home/lichao/everything-library/data/items/.gitkeep`
- Create: `/home/lichao/everything-library/data/repos/.gitkeep`
- Create: `/home/lichao/everything-library/.gitignore`
- Create: `/home/lichao/everything-library/README.md`
- Does NOT own: `/home/lichao/layered-cognitive-agent/**` (除自身 plans/task.md 外不改动任何主工程代码)
- Invariants to test: 仓库根目录在 `/home/lichao/everything-library`，git 状态干净，分类配置 YAML 合法且包含基础分类

**Step 1: Write initial categories.yaml and .gitignore**
- 创建初始分类：`awesome-lists` (精选项目导航), `ai-agent` (AI与智能体), `dev-tools` (开发与系统工具), `learning` (学习资料与文献), `inbox` (随手记/待整理)。
- `.gitignore` 忽略 `__pycache__`, `*.pyc`, `.env`, `data/cache_index.db`, `venv/` 等临时产物。

**Step 2: Initialize git and commit**
- 执行 `git init`，创建初始分支 `main` 并做初始提交。

**Step 3: Verification**
- 运行 `git -C /home/lichao/everything-library status` 确认提交成功。

---

### Task 2: 数据契约与 MarkdownFrontmatter 读写引擎

**Files:**
- Create: `/home/lichao/everything-library/app/models.py`
- Create: `/home/lichao/everything-library/app/storage/markdown_store.py`
- Create: `/home/lichao/everything-library/tests/test_models.py`
- Create: `/home/lichao/everything-library/tests/test_markdown_store.py`
- Does NOT own: Web 页面及路由代码
- Invariants to test:
  - `[INV-01]` 往返保真度：Item 模型转为 Markdown 保存后再次读取，所有字段（含 Frontmatter 元数据及正文）100% 保持一致。

**Step 1: Write the failing tests**
- `test_models.py`: 验证 `ItemSchema`（包含 id, title, url, category, tags, status, rating, created_at, updated_at, agent_notes, content）的合法校验与非法枚举拒绝。
- `test_markdown_store.py`: 写入一个 item 到文件，读取并断言对象属性无损一致。

**Step 2: Run test to verify it fails**
- 运行 `pytest /home/lichao/everything-library/tests/test_models.py`（预期报错缺少模块）。

**Step 3: Write minimal implementation**
- `app/models.py`: 定义 `ItemStatus` (inbox, todo, in_progress, reference, archived)、`ItemSchema`、`CategorySchema`。
- `app/storage/markdown_store.py`: 基于 PyYAML 与标准 Frontmatter 分割逻辑（`---`），实现 `dump_item_to_markdown` 与 `load_item_from_markdown`，支持文件的原子写入与按目录/分类扫描读取。

**Step 4: Run test to verify it passes**
- 运行 `pytest /home/lichao/everything-library/tests/`，确认测试全部 PASS。

**Step 5: Commit**
- 在 `/home/lichao/everything-library` 提交代码。

---

### Task 3: SQLite FTS5 全文检索投影引擎

**Files:**
- Create: `/home/lichao/everything-library/app/storage/index_store.py`
- Create: `/home/lichao/everything-library/tests/test_index_store.py`
- Does NOT own: Web 模板与 HTTP 路由
- Invariants to test:
  - `[INV-02]` 索引投影一致性：向 IndexStore 插入/更新/删除条目后，FTS5 全文搜索（标题、标签、内容、URL）能准确命中，统计数与真实条目 100% 同步。

**Step 1: Write the failing test**
- 编写测试用例：初始化临时数据库，索引一批条目，搜索关键词断言返回预期项；更新状态与标签后断言搜索结果同步更新；删除条目后断言搜索结果不再包含。

**Step 2: Run test to verify it fails**
- 运行 `pytest /home/lichao/everything-library/tests/test_index_store.py`（预期失败）。

**Step 3: Write minimal implementation**
- `app/storage/index_store.py`:
  - 使用 SQLite3 内置 FTS5 表（`items_fts`）结合主数据投影表（`items_index`）。
  - 提供 `rebuild_from_items(items)`、`upsert_item(item)`、`delete_item(item_id)`、`search(query, category, status, tag)` 方法。
  - 支持按更新时间倒序与相关度排序。

**Step 4: Run test to verify it passes**
- 运行测试套件，确认 PASS。

**Step 5: Commit**
- 在 `/home/lichao/everything-library` 提交。

---

### Task 4: 认证模块与安全门禁

**Files:**
- Create: `/home/lichao/everything-library/app/config.py`
- Create: `/home/lichao/everything-library/app/auth.py`
- Create: `/home/lichao/everything-library/tests/test_auth.py`
- Does NOT own: UI 页面布局
- Invariants to test:
  - `[INV-03]` 鉴权门禁不变量：未携带有效 Session Cookie 访问受保护接口必须返回 401 或重定向；正确密码 `lichao12` 颁发有效 Session；伪造/过期 Session 被坚决拦截。

**Step 1: Write the failing test**
- 编写 FastAPI TestClient 针对受保护端点的测试：未认证返回 401；登录成功获得 Cookie；持 Cookie 访问返回 200。

**Step 2: Run test to verify it fails**
- 运行 `pytest /home/lichao/everything-library/tests/test_auth.py`（预期失败）。

**Step 3: Write minimal implementation**
- `app/config.py`: 配置类，管理 `PORT=1889`, `HOST="0.0.0.0"`, `PASSWORD="lichao12"`, `SECRET_KEY`, `SESSION_COOKIE_NAME`。
- `app/auth.py`: 依赖项 `verify_session`、密码验证函数、Session 签名与验签工具。

**Step 4: Run test to verify it passes**
- 运行测试并确认全部通过。

**Step 5: Commit**
- 在 `/home/lichao/everything-library` 提交。

---

### Task 5: RESTful API 与 Awesome 导出端点

**Files:**
- Create: `/home/lichao/everything-library/app/api/routes.py`
- Create: `/home/lichao/everything-library/tests/test_api.py`
- Does NOT own: HTML 模板文件
- Invariants to test:
  - `[INV-04]` Awesome 格式合规性：`/api/export/awesome` 导出的 Markdown 必须具备规范的二级标题分类、标准 GitHub Markdown 超链接及条目描述。
  - 条目增删改查 REST 接口完整可用。

**Step 1: Write the failing test**
- 测试 `GET /api/items`、`POST /api/items`、`PUT /api/items/{id}`、`DELETE /api/items/{id}`、`GET /api/search`、`GET /api/export/awesome`。

**Step 2: Run test to verify it fails**
- 运行 pytest 确认预期失败。

**Step 3: Write minimal implementation**
- `app/api/routes.py`: 实现上述所有路由，调用 `MarkdownStore` 读写文件并同步更新 `IndexStore`。
- 实现 `export_awesome_markdown` 函数，生成结构标准的 Awesome 清单。

**Step 4: Run test to verify it passes**
- 运行测试并确认全部通过。

**Step 5: Commit**
- 在 `/home/lichao/everything-library` 提交。

---

### Task 6: 现代响应式 Web UI 与交互视图

**Files:**
- Create: `/home/lichao/everything-library/app/web/routes.py`
- Create: `/home/lichao/everything-library/app/web/templates/base.html`
- Create: `/home/lichao/everything-library/app/web/templates/index.html`
- Create: `/home/lichao/everything-library/app/web/templates/login.html`
- Create: `/home/lichao/everything-library/app/main.py`
- Invariants to test:
  - 页面能正确渲染分类、状态标签与条目卡片。
  - 包含深色（Dark Mode）与浅色无缝切换机制。
  - 提供快速录入/编辑模态窗与即时搜索前端逻辑。

**Step 1: Write Web routes and Templates**
- `login.html`: 现代居中卡片式登录页，输入密码 `lichao12`。
- `base.html`: 引入 TailwindCSS (CDN) + Lucide Icons，内建全局深浅色模式切换脚本与全局顶部导航。
- `index.html`:
  - 左侧边栏：状态过滤按钮（全部、待看、Todo、在读、参考、归档）+ 分类树带计数 + 标签过滤。
  - 顶部操作区：全局实时搜索输入框、视图切换（卡片 Grid / 表格 List）、`+ 录入新资源` 按钮、导出 Awesome 按钮。
  - 主内容区：响应式卡片网格，展示 URL 标题、外链、分类、状态选择器（可即时切换并保存）、星级、Agent 备忘与操作按钮。
  - 模态窗/抽屉：录入新条目和编辑现有条目的现代化表单。

**Step 2: Connect FastAPI main.py application**
- 挂载路由，配置生命周期（启动时自动扫描 `data/items/` 构建 SQLite 投影索引）。

**Step 3: Verification**
- 编写端到端 Web 路由测试，断言未登录 302 重定向到 `/login`，登录后 200 返回首页 HTML。

**Step 4: Commit**
- 在 `/home/lichao/everything-library` 提交。

---

### Task 7: 种子数据注入与一键管理脚本 `run.sh`

**Files:**
- Create: `/home/lichao/everything-library/data/items/awesome-lists/awesome-sindresorhus.md`
- Create: `/home/lichao/everything-library/data/items/ai-agent/layered-cognitive-agent.md`
- Create: `/home/lichao/everything-library/run.sh`
- Invariants to test:
  - 种子条目被正确加载入库。
  - `run.sh` 脚本可执行，支持 `start`, `stop`, `status`, `restart`，指定端口 1889 与绑定 `0.0.0.0`。

**Step 1: Create seed items**
- 写入 `sindresorhus/awesome` 初始卡片（参考前述设计，标记为 `reference` 状态，5 星，包含详尽 Agent 说明与备忘）。
- 写入本地认知项目条目与开发工具示例。

**Step 2: Create run.sh**
- 编写开箱即用的启动脚本：自动创建 Python 虚拟环境（如需）或使用系统 Python 3.12，安装依赖，后台启动 Uvicorn（`--host 0.0.0.0 --port 1889`），输出清晰的访问地址 `http://10.36.6.252:1889` 及登录密码提示。

**Step 3: Test run.sh**
- 执行 `./run.sh start`，校验 `curl -I http://127.0.0.1:1889` 返回 302 或 200。

**Step 4: Commit**
- 在 `/home/lichao/everything-library` 提交。

---

### Task 8: 全链路端到端验证与服务交付

**Files:**
- Verify: 服务在 `10.36.6.252:1889` 稳定运行
- Verify: 登录验证（密码 `lichao12`）
- Verify: 状态流转（测试将条目在 Inbox / Todo / Reference 间流转）
- Verify: 全文搜索（搜索 `awesome`、`agent` 等快速响应）
- Verify: Agent 访问接口（`curl http://127.0.0.1:1889/api/items`）

**Step 1: Run comprehensive tests**
- 运行所有自动化测试（`pytest`），确保全部通过。

**Step 2: Start service and verify network**
- 确保后台进程常驻运行，测试局域网 IP 与端口联通性。

**Step 3: Update documentation and task tracking**
- 完善 `~/everything-library/README.md`，更新 `docs/plans/task.md`。
