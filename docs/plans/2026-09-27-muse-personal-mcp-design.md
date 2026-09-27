# 个人资产聚合 MCP 服务 (Muse Personal Hub MCP) 设计方案

> **日期**: 2026-09-27  
> **状态**: 已批准 (Approved)  
> **目标**: 构建符合 Anthropic 官方规范的个人专属 MCP (Model Context Protocol) 聚合服务，支持通过 SSE (Server-Sent Events) 与 HTTP 网络传输接入公网/内网的 muse.ai 及其他标准 MCP 客户端。

---

## 1. 系统定位与核心价值

用户在个人工作机 `/home/lichao` 上积累了大量高价值的结构化资产与工具：
1. **Everything Library (`~/everything-library`)**: 包含技术选型、UI 模板、开源项目和避坑指南的个人智库；
2. **Weekly Report (`~/weekly-report`)**: 包含日常流水记录、分类与周报自动生成的个人效能系统；
3. **Wiki (`~/wiki`)**: 包含概念 (`concepts`)、实体 (`entities`)、角色 (`roles`) 与流水日志 (`log.md`) 的个人知识网络与第二大脑。

本项目实现一个统一的高内聚 MCP 服务，对外通过标准 SSE / HTTP POST 协议暴露，内置严格的 Bearer Token 鉴权中间件与 JSON Schema 契约校验，让远端手机端/网页端的 `muse.ai` 助理能够直接挂载该 MCP 地址，无缝调用本地资产。

---

## 2. 边界规范 (Scope & Boundaries)

### 2.1 Owns (负责范围)
* **独立工程封装**: 在 `/home/lichao/tools/muse-mcp-hub` 构建一套结构清晰、工业级标准的 Python MCP 包。
* **MCP 规范实现**:
  * 采用官方推荐的 `mcp` SDK (FastMCP / Starlette SSE Transport)。
  * 提供 `GET /sse` 与 `POST /messages` 标准端点及 `GET /health` 探针。
  * 自动为所有 Tools 生成符合 JSON Schema 规范的 `inputSchema`。
* **核心工具集与能力**:
  * **Everything Library 适配器**: 全文检索 (`library_search`)、详情查看 (`library_get`)、快捷入库 (`library_add`)。
  * **Weekly Report 适配器**: 工作流水追加 (`weekly_log_append`)、周报查询 (`weekly_report_get`)、本周总结汇总 (`weekly_summary`)。
  * **Wiki 适配器**: 知识检索 (`wiki_search`)、概念阅读 (`wiki_read_concept`)、思想灵感流追加 (`wiki_append_log`)。
* **安全性与网络传输**:
  * 支持 Bearer Token 鉴权（配置项 `MUSE_MCP_AUTH_TOKEN`）。
  * 严格防御路径穿越漏洞（Path Traversal），限制所有文件操作在各自数据根目录内。
  * 支持通过 systemd 或 pm2 进行守护管理。
* **测试套件**:
  * 单元测试与协议级集成测试（Invariants 自动化验证）。

### 2.2 Does NOT own (严格禁止触碰，AP-01)
* **禁止修改 `openmuse` 源代码**：本服务作为标准独立服务端，不改动 OpenMuse 源码或内部依赖。
* **禁止修改外部项目的 schema 或业务逻辑**：不破坏 `everything-library`、`weekly-report`、`wiki` 原有的数据库模型或目录结构，只以适配器和安全 API/文件访问方式对接。

### 2.3 Autopilot 风险等级 (AP-05)
* 评级: **AUTOPILOT**（新独立工具包开发，隔离于已有核心业务系统，变更边界清晰，无生产线上风险）。

---

## 3. 架构设计与技术栈

### 3.1 技术栈
* **运行环境**: Python 3.11+
* **MCP 核心库**: Anthropic 官方 `mcp` SDK (`mcp[cli]>=1.3.0`, `fastmcp`)
* **网络与 ASGI 服务**: `starlette`, `uvicorn`, `sse-starlette`
* **数据访问层**: Python 标准库 `sqlite3`、`pathlib`、`json`、`pydantic`

### 3.2 架构分层
```text
┌────────────────────────────────────────────────────────┐
│                   Remote muse.ai Client                │
└───────────────────────────┬────────────────────────────┘
                            │ SSE / HTTP (Authorization: Bearer <TOKEN>)
                            ▼
┌────────────────────────────────────────────────────────┐
│         muse-mcp-hub (ASGI / Uvicorn Service)          │
│  ┌──────────────────────────────────────────────────┐  │
│  │     Auth Middleware (Token Verification & CORS)   │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │   MCP Protocol Layer (JSON-RPC 2.0 / FastMCP)    │  │
│  │   - tools/list (JSON Schema Draft-07 generation) │  │
│  │   - tools/call (Dispatch & Result Envelope)      │  │
│  │   - resources/list & prompts/list                │  │
│  └───────┬───────────────────┬───────────────────┬──┘  │
└──────────┼───────────────────┼───────────────────┼─────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ EverythingLib    │ │ WeeklyReport     │ │ PersonalWiki     │
│ Adapter          │ │ Adapter          │ │ Adapter          │
│ (data/library.db)│ │ (weekly_report.db│ │ (concepts/log.md)│
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## 4. MCP Tools & Schema 详细定义

### 4.1 Everything Library 模块
1. **`library_search`**
   * **描述**: 全文检索个人智库(Everything Library)中的技术选型、UI模板、开源项目和避坑指南。
   * **参数 Schema**:
     * `query` (str, required): 检索词
     * `tag` (str, optional): 标签过滤
     * `limit` (int, default=5): 返回条数限制
2. **`library_get`**
   * **描述**: 根据 ID 获取智库条目的详细信息（包括完整描述、链接与核心笔记）。
   * **参数 Schema**:
     * `item_id` (str, required): 条目唯一 ID
3. **`library_add`**
   * **描述**: 向个人智库暂存区添加一条新的技术选型或项目收藏。
   * **参数 Schema**:
     * `title` (str, required): 标题
     * `url` (str, optional): 项目或文档链接
     * `category` (str, optional): 分类（ui, backend, ai, cloud 等）
     * `notes` (str, optional): 核心评价或关键特征

### 4.2 Weekly Report 模块
1. **`weekly_log_append`**
   * **描述**: 向个人周报流水中追加一条工作进展或日志。
   * **参数 Schema**:
     * `content` (str, required): 工作内容描述
     * `category` (str, default="feature"): 分类 ("feature", "bugfix", "ops", "study", "other")
     * `date_str` (str, optional): 记录日期 (YYYY-MM-DD)，留空则默认今天
2. **`weekly_report_get`**
   * **描述**: 获取指定周或当周的全部工作日志列表。
   * **参数 Schema**:
     * `week_offset` (int, default=0): 0 表示当周，-1 表示上周
3. **`weekly_summary`**
   * **描述**: 生成本周工作汇总摘要，便于快速汇报或导出。
   * **参数 Schema**:
     * `include_metrics` (bool, default=True): 是否包含分类计数统计

### 4.3 Wiki 个人知识库模块
1. **`wiki_search`**
   * **描述**: 在个人第二大脑(Wiki)中搜索相关概念、实体或日志条目。
   * **参数 Schema**:
     * `keyword` (str, required): 搜索关键词
2. **`wiki_read_concept`**
   * **描述**: 读取个人知识库中某个概念或实体文档的完整正文内容。
   * **参数 Schema**:
     * `name` (str, required): 概念或实体名称（如 "驾驭工程"、"LCA" 等）
3. **`wiki_append_log`**
   * **描述**: 向个人 Wiki 流水日志 (`~/wiki/log.md`) 追加灵感碎片或快速记录。
   * **参数 Schema**:
     * `text` (str, required): 记录文本

---

## 5. 安全性与测试不变量 (Invariants, AP-02)

1. **鉴权不变量 (C-AUTH)**: 未携带有效 Token 的请求，一律被 ASGI 鉴权中间件在握手前拦截，返回 HTTP 401，绝不向下游 MCP 路由透传。
2. **路径安全不变量 (C-PATH)**: Wiki 模块的所有文件读取与追加严格限定在 `~/wiki` 目录内，任何 `../` 或越界绝对路径调用必须抛出 `PermissionError` 或安全拒绝响应。
3. **协议合规不变量 (C-SCHEMA)**: `tools/list` 输出必须能通过标准 JSON Schema 语法校验，所有工具入参和返回结构符合 JSON-RPC 2.0 规范。
4. **幂等与健壮性不变量 (C-RES)**: 数据库查询出错或外部不可用时，工具执行必须以友好错误消息封装（`isError=True` 并在 `content` 中说明原因），禁止未捕获异常导致 SSE 进程崩溃。
