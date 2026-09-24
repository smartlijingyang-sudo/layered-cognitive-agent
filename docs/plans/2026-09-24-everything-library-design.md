# Everything Library（个人智库与资源枢纽）系统设计文档

> **创建日期:** 2026-09-24  
> **设计状态:** 已确认（User Approved）  
> **Autopilot 级别:** DRAFT  

---

## 1. 业务目标与第一性原理

### 1.1 业务愿景
构建一个长期可维护、架构优雅、兼顾人类高品质交互体验与 AI Agent 机器可读性的个人数字智库与资源枢纽（`~/everything-library`）。
统一汇聚并管理：
1. **开源项目与库**（如 `sindresorhus/awesome` 及各类精选项目）；
2. **技术文档、网络文章与经典链接**；
3. **个人灵感、实践备忘与待办清单（Todo / 待看 / 临时暂存 / 常驻参考）**；
4. **代码实践空间（本地探索/克隆工程）**。

### 1.2 核心第一性原理
- **内容为代码（Content as Code & GitOps）**：所有资料与卡片以纯文本 Markdown + YAML Frontmatter 为唯一事实源（SSOT），全量纳入 Git 版本控制。即使展示层 Web 技术在未来迭代重构，全部知识资产与版本历史永不损坏。
- **事实与投影分离（SSOT vs. Projection）**：Markdown 文件是唯一事实；SQLite FTS5 是启动与保存时自动派生的只读全文检索与聚合索引（Projection），可毫秒级丢弃与 100% 重建。
- **人机双轨友好（Dual Interface）**：
  - **对人**：局域网（`10.36.6.252:1889`）精美仪表盘，密码安全准入，深浅色主题，卡片与紧凑表格双视图，分类与状态流转，秒级全文搜索。
  - **对 Agent**：标准化 RESTful / OpenAPI 接口，以及终端友好的文件布局与强类型 Frontmatter，Agent 可零门槛在文件系统通过 bash/grep/cat 读写或通过 API 交互。

---

## 2. 边界规范（Boundaries）

- **Owns（本方案构建范围）**：
  - 初始化目录 `~/everything-library` 并建立独立 Git 仓库。
  - 数据模型：Pydantic v2 条目元数据规范与 Markdown 序列化/反序列化。
  - 存储与投影：Markdown 读写层、文件变更同步 SQLite FTS5 全文索引层。
  - Web 与 API 服务：FastAPI 后端、Session 密码认证（`lichao12`）、局域网监听（`0.0.0.0:1889`）。
  - 前端界面：基于现代响应式 UI（TailwindCSS 调色、暗黑模式切换、卡片与表格视图、分类与状态过滤、快速录入/编辑、实时搜索）。
  - 导出能力：一键生成/导出类似 `sindresorhus/awesome` 规范的 Markdown 索引。
  - 自动化测试套件与一键启动脚本 `run.sh`。
- **Does NOT own（严格禁止越界）**：
  - 不修改外部主工作区（`~/layered-cognitive-agent`）的任何业务代码或配置。
  - 不篡改操作系统系统级网络配置或占用非声明端口（严格使用 `1889`）。

---

## 3. 总体架构与数据契约

### 3.1 目录组织架构（`~/everything-library`）

```text
~/everything-library/
├── .git/                      # 独立 Git 仓库
├── data/
│   ├── items/                 # 核心条目卡片（SSOT，Markdown + Frontmatter）
│   │   ├── awesome-lists/     # 经典 Awesome 资源条目（含 sindresorhus/awesome）
│   │   ├── ai-agent/          # AI 与 Agent 领域
│   │   ├── dev-tools/         # 开发与效率工具
│   │   ├── learning/          # 教程与经典书籍/文章
│   │   └── inbox/             # 待整理与临时速记
│   ├── categories.yaml        # 分类字典（ID、显示名、图标、顺序）
│   └── repos/                 # 本地实践代码/克隆工程（.gitignore 规则按需管理）
├── app/                       # 核心应用服务
│   ├── __init__.py
│   ├── config.py              # 配置管理（端口 1889、主机 0.0.0.0、认证密码等）
│   ├── models.py              # Pydantic 数据契约（ItemSchema, CategorySchema, etc.）
│   ├── storage/
│   │   ├── markdown_store.py  # Markdown 文件的持久化、读取与解析
│   │   └── index_store.py     # SQLite FTS5 只读索引投影管理
│   ├── auth.py                # Session Cookie 鉴权机制
│   ├── api/                   # RESTful API 路由（items, categories, search, export）
│   │   └── routes.py
│   ├── web/                   # Web UI 页面路由与模板资源
│   │   ├── routes.py
│   │   └── templates/         # 现代响应式 HTML (Tailwind, Lucide 图标, 深浅色)
│   └── main.py                # FastAPI 组合根
├── tests/                     # 自动化测试
│   ├── test_models.py         # 契约与序列化单测
│   ├── test_storage.py        # 存储与 SQLite FTS 索引单测
│   └── test_api.py            # API 与认证安全单测
├── run.sh                     # 启动管理脚本（start / stop / status）
├── requirements.txt           # 核心依赖清单
└── README.md                  # 智库使用与 Agent 交互手册
```

### 3.2 数据条目契约（Item Frontmatter Schema）

所有条目文件 `data/items/**/*.md` 均遵循统一规范：

```yaml
---
id: "20260924-awesome-sindresorhus"
title: "Awesome Lists (sindresorhus/awesome)"
url: "https://github.com/sindresorhus/awesome"
category: "awesome-lists"
tags: ["curated", "github-star", "meta", "resource-hub"]
status: "reference"          # 枚举: inbox | todo | in_progress | reference | archived
rating: 5                    # 1-5 星推荐度
created_at: "2026-09-24T22:20:00"
updated_at: "2026-09-24T22:20:00"
agent_notes: "GitHub 最著名的资源汇总总目录，适合技术选型与新领域导航。"
---

## 概述与核心价值
GitHub 上最具影响力的开源资源汇总总库，拥有 30 万+ Star。

## 我的实践计划 / 备忘
- 参考其分类标准梳理本智库的顶级分类。
- 定期探索其中的 Trending 和新兴 Agent 列表。
```

---

## 4. 关键子系统设计

### 4.1 认证与安全机制（Auth & Security）
- **认证凭证**：局域网访问密码 `lichao12`（可经配置文件/环境变量覆盖）。
- **Session 管理**：用户输入密码成功后，发放签名 Session Cookie（`HttpOnly`, `SameSite=Lax`），默认有效期 30 天。
- **访问拦截**：除登录页面与静态资源外，所有 Web 页面与 `/api/*` 请求均进行 Session 校验；未登录用户访问 Web 自动重定向至登录页，访问 API 返回 401。

### 4.2 存储与索引投影引擎（MarkdownStore & IndexStore）
- **启动初始化**：应用启动时扫描 `data/items/**/*.md`，全量在内存/本地临时 SQLite（`data/cache_index.db`）建立 FTS5 全文索引。
- **写操作流程**：
  1. Web 或 API 提交创建/更新请求；
  2. 经过 Pydantic Schema 校验；
  3. 原子写入指定 Markdown 文件（并在 Git 对应提交记录）；
  4. 增量更新 SQLite 索引；
  5. 返回结构化结果。

### 4.3 Web UI / UX 设计
- **现代美学**：类 Notion / Linear 的现代极简卡片与列表排版，支持 Dark / Light 模式一键切换。
- **核心交互视图**：
  1. **顶部栏**：全局搜索框（实时 FTS5 模糊/高亮匹配）、深浅色切换、快速录入按钮（`+ 录入新资源`）、退出登录。
  2. **左侧导航**：
     - **状态漏斗**：全部 / 待整理 (Inbox) / 待实践 (Todo) / 学习中 (In Progress) / 常驻参考 (Reference) / 归档 (Archived)。
     - **分类树**：显示各分类名称及收录条目数统计。
     - **常用标签**：点击标签即刻过滤。
  3. **主工作区**：
     - 卡片网格（Card Grid）/ 紧凑表格（List View）一键切换。
     - 每张卡片包含：标题、外部链接外跳、分类徽章、状态徽章（支持直接下拉变更状态）、星级、标签列表、正文折叠摘要与操作按钮（编辑/删除）。
  4. **快速录入/编辑抽屉（Modal / Drawer）**：
     - 表单字段：URL（支持一键提取/抓取标题）、标题、分类（下拉）、状态、星级、标签（逗号分隔）、Agent 简注、Markdown 详细备忘。

### 4.4 Agent 机器接口
- **RESTful API**：
  - `GET /api/items`：支持 `category`, `status`, `tag`, `search` 参数，返回 JSON 数组。
  - `POST /api/items`：Agent 可用以新增条目。
  - `GET /api/items/{id}`：获取完整元数据与正文。
  - `PUT /api/items/{id}`：修改条目或更新状态。
  - `DELETE /api/items/{id}`：删除条目。
  - `GET /api/export/awesome`：一键导出为标准 Awesome README.md 格式。
- **OpenAPI 规范**：自动提供交互式文档 `/docs`。

---

## 5. 自动化测试不变量（Invariants in Tests）

必须在 `tests/` 中通过自动化测试断言以下不变量：
1. **[INV-01] 契约往返保真度**：Item 模型经 Markdown 序列化写入磁盘再反序列化读取，所有字段（含 Frontmatter 元数据与正文内容）100% 一致。
2. **[INV-02] 索引投影一致性**：新增、修改、删除条目文件后，SQLite FTS5 索引命中结果与文件系统完全对齐。
3. **[INV-03] 鉴权安全门禁**：未经授权请求 `/api/items` 必返回 401；错误密码拒绝签发 Cookie；正确密码签发有效 Session 并放行。
4. **[INV-04] Awesome 导出合规性**：导出的 Markdown 符合 GitHub Awesome List 结构，能够正确按分类渲染二级标题与超链接列表。
