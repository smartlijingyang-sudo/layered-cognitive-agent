# Muse Personal Hub MCP Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建符合 Anthropic 官方规范的个人专属 MCP (Model Context Protocol) 聚合服务，支持通过 SSE (Server-Sent Events) 与 HTTP 网络传输接入公网/内网的 muse.ai 及其他标准 MCP 客户端。

**Architecture:** 采用官方 Python `mcp` SDK (FastMCP / Starlette) 搭建独立服务，解耦业务实现，通过模块化适配器（Adapters）安全读取/追加本地 `everything-library`、`weekly-report` 和 `wiki` 资产，外层包装 Bearer Token 鉴权中间件与 CORS 支持。

**Tech Stack:** Python 3.11+, `mcp[cli]>=1.3.0`, `starlette`, `uvicorn`, `sse-starlette`, `pydantic`, `pytest`, `pytest-asyncio`, `httpx`

---

### Task 1: 初始化工程结构与配置管理

**Files:**
- Create: `/home/lichao/tools/muse-mcp-hub/pyproject.toml`
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/__init__.py`
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/config.py`
- Test: `/home/lichao/tools/muse-mcp-hub/tests/test_config.py`
- Does NOT own: `openmuse/*`, `everything-library/*`, `weekly-report/*`, `wiki/*` (AP-01)
- Invariants to test: 环境变量未配置时提供安全默认值；有效路径解析与 Token 校验 (AP-02)

**Step 1: 编写测试用例**
- 验证配置类能正确解析数据目录（智库、周报、Wiki 路径）并检验鉴权 Token。

**Step 2: 运行测试确保失败 (RED)**
- 执行 `pytest` 确认模块尚未实现。

**Step 3: 实现配置模块与环境声明**
- 实现 `Config` 类，支持从环境变量与 `.env` 读取 `MUSE_MCP_AUTH_TOKEN`, `MUSE_MCP_HOST`, `MUSE_MCP_PORT` 等。

**Step 4: 运行测试确保通过 (GREEN)**
- 执行 `pytest` 确认配置解析正常。

**Step 5: 提交代码**

---

### Task 2: 实现三大核心资产的数据适配器 (Adapters)

**Files:**
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/adapters/library.py`
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/adapters/weekly.py`
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/adapters/wiki.py`
- Test: `/home/lichao/tools/muse-mcp-hub/tests/test_adapters.py`
- Does NOT own: 原项目的业务代码和数据库迁移 (AP-01)
- Invariants to test: 
  - Wiki 模块防御路径穿越攻击（包含 `../` 的请求抛出安全异常）；
  - 智库搜索在数据库存在/不存在时返回合规结构；
  - 周报记录追加保证格式与幂等性 (AP-02)。

**Step 1: 编写适配器测试用例**
- 覆盖搜索、读取与写入逻辑，特别包含边界与安全穿越测试。

**Step 2: 运行测试确保失败 (RED)**
- 确认适配器未实现。

**Step 3: 实现适配器逻辑**
- `LibraryAdapter`: 读取 `~/everything-library/data/library.db`，支持全文模糊检索。
- `WeeklyAdapter`: 对接 `~/weekly-report/data/` 中的数据库或日志，支持记录追加与周报提取。
- `WikiAdapter`: 扫描 `~/wiki` 目录下的 Markdown 文件，提供安全沙箱下的检索、读取与日志追加。

**Step 4: 运行测试确保通过 (GREEN)**
- 执行 `pytest` 确认所有适配器通过。

**Step 5: 提交代码**

---

### Task 3: 注册官方 MCP Tools 并生成符合规范的 Schema

**Files:**
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/server.py`
- Test: `/home/lichao/tools/muse-mcp-hub/tests/test_mcp_server.py`
- Does NOT own: 任何宿主端代码 (AP-01)
- Invariants to test: 
  - `tools/list` 必须产出标准 JSON Schema（包含 `name`, `description`, `inputSchema`）；
  - `tools/call` 执行时异常必须以包含错误说明的 JSON-RPC 结果返回，绝不产生未捕获崩溃 (AP-02)。

**Step 1: 编写 MCP 服务工具注册与 Schema 测试**
- 验证所有 9 个 Tool 均被正确声明，并导出有效的 JSON Schema 字典。

**Step 2: 运行测试确保失败 (RED)**
- 确认服务端尚未构建。

**Step 3: 使用 FastMCP 实现 Server 并装配 Tools**
- 初始化 FastMCP 实例，将适配器映射为符合 MCP 规范的标准 Tools。

**Step 4: 运行测试确保通过 (GREEN)**
- 执行测试，验证工具发现与调用。

**Step 5: 提交代码**

---

### Task 4: 构建 SSE 网络传输层、鉴权中间件与 ASGI 应用

**Files:**
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/transport.py`
- Create: `/home/lichao/tools/muse-mcp-hub/src/muse_mcp_hub/app.py`
- Test: `/home/lichao/tools/muse-mcp-hub/tests/test_transport_and_auth.py`
- Does NOT own: 任何外部反代服务配置 (AP-01)
- Invariants to test:
  - 未带 Token 或 Token 错误时请求 `/sse` 直接返回 HTTP 401；
  - 携带有效 Token 时成功建立 SSE 通道；
  - `/health` 探针无需鉴权直接返回 200 (AP-02)。

**Step 1: 编写传输层与鉴权测试**
- 使用 `httpx.AsyncClient` 模拟客户端发起 HTTP/SSE 握手请求。

**Step 2: 运行测试确保失败 (RED)**
- 验证中间件与端点未就绪。

**Step 3: 实现 Bearer Token 中间件与 Starlette ASGI 应用**
- 接入 SSE Transport，设置路由挂载与鉴权拦截。

**Step 4: 运行测试确保通过 (GREEN)**
- 执行测试，验证鉴权拦截与 SSE 握手。

**Step 5: 提交代码**

---

### Task 5: 部署管理脚本、端到端验证与接入文档

**Files:**
- Create: `/home/lichao/tools/muse-mcp-hub/run.sh`
- Create: `/home/lichao/tools/muse-mcp-hub/README.md`
- Create: `/home/lichao/tools/muse-mcp-hub/.env.example`
- Does NOT own: 修改系统全局服务 (AP-01)
- Invariants to test: 启动脚本可正确启动服务并能在本地/局域网完成健康检测。

**Step 1: 编写 CLI 入口与启动脚本**
- 提供前台/后台一键启动 `run.sh`，支持 PID 管理与日志输出。

**Step 2: 端到端网络调用验证**
- 执行完整 E2E 校验：通过 curl / Python 脚本模拟 Muse 发送 initialize -> tools/list -> tools/call。

**Step 3: 编写规范使用与 Muse.ai 客户端配置说明**
- 产出清晰文档，说明服务地址、Token 配置方法以及如何在公网/内网环境接入。

**Step 4: 提交代码与完成任务**
