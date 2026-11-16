# 企业级应用集成与统一接口封装设计 (Mangli Enterprise Integration Design)

> **设计状态：** Approved (用户已确认)  
> **设计日期：** 2026-11-16  
> **自治等级：** DRAFT (纯外围扩展与声明式编排，零侵入核心)  
> **核心原则：** 核心封板零修改；外围插件化；声明式编排；强类型契约闭环；开箱即用单页验证。

---

## 1. 业务目标与第一性原理

### 1.1 业务诉求
针对企业生产环境下的智能体落地，本方案解决以下核心诉求：
1. **企业统一鉴权对齐**：支持通过公司统一 API Gateway 传入的 `X-Mangli-User`（AES/ECB/PKCS5Padding 经 Hex 编码）进行解密，并使用透传的 `ticket` 调用内部权限微服务拉取角色与权限点，将身份安全注入运行上下文；
2. **多数据源自主编排**：支持无缝集成智能问数 Agent（A2A）、OA 系统（MCP 协议）、Wiki/Jira（REST API）、企业知识库（RAG）以及受控文件沙箱（安全读写与回执）；
3. **接口高度收敛与时序解耦**：彻底消除前端直接面对数十个异构业务接口的复杂性，由 Agent 认知闭环自主完成时序规划，对外统一封装为项目、会话、消息流式（SSE）与文件四大标准 REST+SSE 接口；
4. **灵活多维隔离**：支持基于“项目（Project）”的团队隔离空间，同时天然兼容不属于任何项目的“游离会话（个人独立会话）”；
5. **极简开箱即用验证**：提供独立的单页测试控制台（Playground），支持模拟 Header 输入、项目/会话切换、打字机流式查看、工具调用折叠卡片与文件一键下载。

---

## 2. 职责边界与自治等级

### 2.1 强制责任边界 (AP-01)
- **Owns (本设计负责构建的内容)**：
  1. `lca/plugins/transport/webserver/routes_mangli_api.py`：企业网关专属路由与鉴权插件；
  2. `lca/plugins/tools/mangli_enterprise_tools.py`：5 大企业数据与能力工具插件；
  3. `bundles/mangli-enterprise.yaml`：企业 Bundle 组合清单；
  4. `profiles/mangli-enterprise.yaml`：企业 Profile 配置与参数补丁；
  5. `lca/infrastructure/web/static/mangli_playground.html`：轻量单页测试控制台；
  6. `tests/plugins/transport/test_routes_mangli_api.py` 与 `tests/plugins/tools/test_mangli_tools.py`：全量自动化回归与不变量测试。

- **Does NOT Own (严格禁止修改或外部系统范围)**：
  1. 严格禁止修改 LCA 核心层代码（`lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/`）；
  2. 严格禁止修改企业内部已有的 Spring Cloud Gateway、权限服务、OA MCP Server、问数 Agent 的代码实现，仅以标准化客户端协议对接。

### 2.2 自治等级 (AP-05)
- **评级：DRAFT 级**。
- **依据**：新功能完全落在外围插件层与配置文件中，遵守 C14（图与业务隔离）、C6（最小化）与 C13（强类型契约），不引发核心架构退化与冲突。

---

## 3. 架构全景与组件设计

```mermaid
flowchart TD
    subgraph ClientLayer [客户端接入层]
        SCG[企业 Spring Cloud Gateway]
        Playground[轻量单页验证控制台 /playground]
    end

    subgraph TransportLayer [LCA 传输与网关层 (routes_mangli_api.py)]
        AuthMid[MangliAuthMiddleware<br>AES解密 + ticket查权限 + 5min LRU缓存]
        ContextVar[MangliUserContext 注入]
        
        subgraph APIRoutes [标准 REST + SSE 路由]
            R_Proj["/api/v1/projects (项目)"]
            R_Sess["/api/v1/sessions (会话与历史)"]
            R_Run["/api/v1/sessions/{id}/runs (发起任务)"]
            R_Stream["/api/v1/runs/{id}/stream (SSE 流式输出)"]
            R_Cancel["/api/v1/runs/{id}/cancel (取消任务)"]
            R_Model["/api/v1/models (模型列表)"]
            R_File["/api/v1/files (文件清单与下载)"]
        end
    end

    subgraph CoreEngine [LCA 封板微内核 (零修改)]
        MTK[MTK 图解释器 & 认知循环]
        Spine[Session.append 追加式事实日志流]
        SafeExec[SafeExecutor 隔离沙箱]
    end

    subgraph EnterpriseTools [企业数据工具池 (mangli_enterprise_tools.py)]
        T_Data[1. 问数 Agent A2A 委托]
        T_OA[2. OA 协同 MCP 客户端]
        T_Wiki[3. Wiki / Jira 检索工具]
        T_KB[4. 企业知识库 RAG 检索]
        T_File[5. 受控工作区文件读写]
    end

    SCG -->|携带 X-Mangli-User & ticket| AuthMid
    Playground -->|模拟 Header| AuthMid
    AuthMid --> ContextVar
    ContextVar --> APIRoutes
    
    APIRoutes --> CoreEngine
    CoreEngine --> EnterpriseTools
    EnterpriseTools --> CoreEngine
    CoreEngine -->|SSE 打字机增量 + 工具回执| R_Stream
```

---

## 4. 详细模块设计

### 4.1 认证与用户上下文链路

#### 4.1.1 Java 对齐的 AES 解密算法
- **算法模式**：`AES/ECB/PKCS5Padding`（对应 Python `AES.MODE_ECB` + PKCS7 填充，无 IV）。
- **密钥推导兼容**：针对 Java `KeyGenerator + SecureRandom("SHA1PRNG")`，Python 提供等价推导函数，同时支持直接配置 16 字节 Hex 密钥，双重保险。
- **输入流**：提取请求头 `X-Mangli-User` $\to$ `bytes.fromhex()` $\to$ AES 解密 $\to$ 反序列化为 JSON：
  ```json
  {
    "user_id": "U10086",
    "name": "张三",
    "title": "系统架构师",
    "dept_id": "D003",
    "dept_name": "研发中心"
  }
  ```

#### 4.1.2 权限补全与 LRU 缓存
- **权限接口**：`http://host:port/inner/api/app/permissions`
- **请求头**：自动透传 Gateway 传入的 `ticket` Header。
- **性能优化**：采用 `cachetools.TTLCache(maxsize=10000, ttl=300)`（5 分钟过期），避免频繁请求权限微服务。
- **用户模型定义**：
  ```python
  class MangliUserContext(BaseModel):
    user_id: str
    name: str
    title: str
    dept_id: str
    dept_name: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
  ```
- **注入生命周期**：封装进 Python `ContextVar[MangliUserContext]`，下游所有 Tool 执行均可通过 `get_current_user()` 获取当前调用者身份。

---

### 4.2 统一 API 契约全景 (REST + SSE)

所有接口统一挂载在 `/api/v1/` 命名空间下：

#### 4.2.1 项目域 (Projects)
- `GET /api/v1/projects`：获取当前用户所属/有权限的项目列表。
- `POST /api/v1/projects`：创建项目 `{ "name": "...", "description": "..." }`。

#### 4.2.2 会话域 (Sessions)
- `GET /api/v1/sessions?project_id={id}&unassigned={bool}`：获取会话列表。支持按项目筛选；`unassigned=true` 或不传 `project_id` 则查询个人游离会话。
- `POST /api/v1/sessions`：创建会话 `{ "title": "...", "project_id": null }`。
- `DELETE /api/v1/sessions/{session_id}`：删除/归档指定会话。
- `GET /api/v1/sessions/{session_id}/messages?limit=50&cursor=...`：分页获取会话消息历史，包含用户输入、模型回答、工具卡片快照及生成的文件。

#### 4.2.3 对话运行与流式 (Runs & Streaming)
- `POST /api/v1/sessions/{session_id}/runs`：发起一次对话任务。
  - Body: `{ "content": "查询上月华东区销售额并输出 markdown 报告", "attachments": [] }`
  - Response: `{ "run_id": "run_01J9...", "status": "running" }`
- `GET /api/v1/runs/{run_id}/stream`：**核心 SSE 长连接通道**。
  - 响应头包含：`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
  - **防 Spring Cloud Gateway 超时机制**：每 15 秒自动发送一次 `: ping\n\n` 心跳包。
  - **事件类型**：
    - `event: text_delta`：打字机文本增量；
    - `event: tool_start`：工具执行开始（含入参摘要）；
    - `event: tool_end`：工具执行结束（含回执与状态）；
    - `event: file_created`：生成文件通知（含 `file_id`、文件名、大小）；
    - `event: done`：任务收敛完成；
    - `event: error`：异常中断提示。

#### 4.2.4 任务控制与模型服务 (Control & Models)
- `POST /api/v1/runs/{run_id}/cancel`：取消正在运行的任务（复用核心取消状态机）。
- `GET /api/v1/models`：获取当前可用的模型列表（复用核心模型枚举）。

#### 4.2.5 文件服务域 (Files)
- `GET /api/v1/files?project_id={id}&session_id={id}`：列出指定范围内的生成或上传文件。
- `POST /api/v1/files/upload`：上传本地文件挂载至当前会话或项目。
- `GET /api/v1/files/{file_id}/download`：流式下载文件二进制流。

---

### 4.3 五大企业数据工具与能力集成

所有工具定义在 `lca/plugins/tools/mangli_enterprise_tools.py` 中，严格遵循 LCA 强类型输入/输出契约：

1. **智能问数 Agent 工具 (`query_data_agent`)**：
   - 走 HTTP 委托协议调用外部问数 Agent。
   - 自动附带调用者的 `user_id` 与 `dept_id` 作为数据查询过滤条件，防止越权。
2. **OA 协同工具 (`oa_mcp_tools`)**：
   - 复用 LCA 原生内置的 `_mcp_factory`，连接 OA MCP Server。
   - 动态暴露待办审批查询、流程发起等标准能力。
3. **Wiki & Jira 协同工具 (`search_wiki`, `search_jira`)**：
   - 基于 REST API 封装对企业 Wiki 与 Jira 的只读检索与状态追踪。
4. **企业知识库工具 (`search_knowledge_base`)**：
   - 连接企业内部 RAG 检索服务，返回带原文出处与溯源链接的切片。
5. **受控工作区文件读写工具 (`read_workspace_file`, `write_workspace_file`)**：
   - 基于当前 `session_id` 与 `project_id` 的受控沙箱目录读写。
   - 写入文件自动向事实日志追加回执，并生成对外的下载 `file_id`。

---

### 4.4 极简单页验证控制台 (Playground UI)

文件路径：`lca/infrastructure/web/static/mangli_playground.html`。通过路由插件挂载于 `GET /playground`。
- **免依赖打包**：采用现代标准纯 HTML + 原生 ES Module / Tailwind CDN，无需安装任何 Node.js/npm 模块；
- **核心交互视图**：
  1. **身份模拟器**：支持输入测试用 `X-Mangli-User` 十六进制串，或开启开发 Mock 模式一键切换角色；
  2. **项目与会话树**：左侧展示“项目会话”与“游离会话”，支持一键新建和删除；
  3. **对话主视窗**：支持流式打字机逐字渲染，动态展示工具调用的折叠卡片（状态、入参、执行耗时），提供红色的“终止任务”按钮；
  4. **资产侧边栏**：展示当前会话生成的所有报表和文件卡片，点击直接下载。

---

## 5. 声明式编排配置 (YAML)

### 5.1 `bundles/mangli-enterprise.yaml`
```yaml
name: mangli-enterprise
description: 企业专属插件与核心能力组合清单
requires:
  - base
  - session-runtime
  - observability-default
plugins:
  - mangli-enterprise-routes
  - mangli-enterprise-tools
```

### 5.2 `profiles/mangli-enterprise.yaml`
```yaml
name: mangli-enterprise
description: 企业运行配置与环境注入
bundles:
  - bundles/base.yaml
  - bundles/session-runtime.yaml
  - bundles/observability-default.yaml
  - bundles/mangli-enterprise.yaml
patch:
  - id: mangli-enterprise-routes
    config:
      aes_password:
        from_env: MANGLI_AES_PASSWORD
      permission_api_url: "http://10.36.6.252:8080/inner/api/app/permissions"
      dev_mock:
        from_env: MANGLI_DEV_MOCK
        required: false
```

---

## 6. 测试与架构不变量守护 (AP-02)

新增自动化测试套件必须严格覆盖以下核心不变量：

| 不变量编号 | 守护规则与断言 | 验证用例 |
|---|---|---|
| **INV-01** | Java `AES/ECB/PKCS5Padding` 加解密一致性，包含 Hex 编解码 | `test_mangli_aes_decrypt_java_interop` |
| **INV-02** | 权限服务调用与 5 分钟 TTL 缓存命中与过期刷新 | `test_mangli_permission_cache_ttl` |
| **INV-03** | 项目会话与游离会话（`project_id is None`）隔离与访问边界 | `test_mangli_session_project_isolation` |
| **INV-04** | SSE 6 类事件流式契约闭环与 15 秒心跳包格式 | `test_mangli_sse_event_stream_closure` |
| **INV-05** | 5 大数据工具强类型入参校验与上下文透传 | `test_mangli_tools_context_injection` |
| **INV-06** | **核心零修改铁律**：`git diff lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel` 必须退出码为 0 且输出为空 | `test_core_zero_mutation_guard` |

---

## 7. 实施路线规划

1. **Phase 1**：实现 AES 解密与权限获取中间件，建立单测对齐 Java 加解密；
2. **Phase 2**：实现对外 REST + SSE 路由插件（项目、会话、文件、取消、模型）；
3. **Phase 3**：实现 5 大数据与能力插件，完成上下文透传；
4. **Phase 4**：编排 YAML 配置，完成静态门禁校验（`kernel_check`）；
5. **Phase 5**：实现单页 Playground 静态页面，端到端联调全链路。
