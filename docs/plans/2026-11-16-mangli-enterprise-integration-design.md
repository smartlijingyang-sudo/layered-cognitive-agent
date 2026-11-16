# 企业级应用集成与统一接口封装设计 (Mangli Enterprise Integration Design)

> **设计状态：** Approved (针对架构评审意见完成全量硬伤修复与深化)  
> **设计日期：** 2026-11-16  
> **自治等级：** DRAFT (纯外围扩展与声明式编排，零侵入核心)  
> **宪法约束：** 遵照根目录 `AGENTS.md`（C1 认知闭集、C2 双平面、C4 Reducer单写、C5 能力单调、C6 最小化、C10 执行窄门、C13 信息血统闭合、C14 图与业务隔离）。

---

## 1. 架构定位：Thin Façade 聚合门面原则

### 1.1 明确与现有 API 的主从关系（拒绝造轮子）
系统**严禁重写或平行造一套运行执行逻辑**。现有 `lca/plugins/transport/webserver/` 已经具备成熟稳定的执行与流式基础设施：
- `/runs`（创建/查询/取消/answer/feedback/doctor/evidence/live SSE 流式）定义在 [`routes_runs_sessions.py`](file:///H:/Workspace/KLTB/SourceCode/tongbao-ai/layered-cognitive-agent/lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py)；
- `/files/{attachment_id}`（文件下载）与 `/v1/models`（模型枚举）定义在 [`routes_openai_compat_files.py`](file:///H:/Workspace/KLTB/SourceCode/tongbao-ai/layered-cognitive-agent/lca/plugins/transport/webserver/routes_1/routes_openai_compat_files.py)；
- `/v1/sessions` 具备 8 条完整的底层会话管理路由。

**`/api/v1` 的唯一正确定位是：企业级薄门面（Thin Façade）与上下文适配层：**
1. **纯转发复用**：`/api/v1/runs/{id}/stream` 直接复用底层的 `live_endpoint`（SSE）；`/api/v1/runs/{id}/cancel` 直接复用底层的 `cancel_run`；`/api/v1/models` 直接复用 `list_models`；`/api/v1/files/{id}/download` 直接复用 `download_file`；
2. **只增量补齐缺失域**：
   - **`Projects` 领域**（全仓此前无此概念，本方案独立提供持久化与成员隔离）；
   - **Mangli 企业专属鉴权**（解密 Gateway 请求头，获取权限并完成身份映射）；
   - **项目与会话关联绑定**（支持指定 `project_id` 过滤或查询个人游离会话）。

---

## 2. 职责边界与自治等级

### 2.1 强制责任边界 (AP-01)
- **Owns (本设计负责构建的内容)**：
  1. `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py`：AES-ECB-PKCS5Padding 解密、Java 向量对齐、权限服务调用、基于标准库的无依赖 `ExpiringLruCache`；
  2. `lca/plugins/transport/webserver/routes_mangli_api.py`：`/api/v1` 薄门面路由插件，仅补齐 Projects、会话过滤，其余直接代理复用已有 Handler；
  3. `lca/infrastructure/persistence/project_store.py`：`ProjectStore`（SQLite/Postgres 双后端）负责项目实体与 `project_id ↔ session_id` 关联映射；
  4. `lca/plugins/tools/mangli_enterprise_tools.py`：严格遵循 `ToolManifest` + `ParameterSpec` + `Tool` 契约（继承 `lca.contracts.protocols.Tool`，返回 `Observation`）的企业工具与 MCP 集群配置器；
  5. `lca/plugins/transport/webserver/static/mangli_playground.html`：**零外网依赖（纯内置现代化原生 CSS，无 Tailwind CDN）**的单页验证控制台；
  6. `bundles/mangli-enterprise.yaml` 与 `profiles/mangli-enterprise.yaml`：纯环境变量解耦的声明式编排；
  7. 全量自动化测试（含 Java 真实密文向量测试、真实 merge-base 核心零修改门禁）。

- **Does NOT Own (严格禁止侵入或交由外部负责的范围)**：
  1. 严格禁止修改 LCA 核心层代码（`lca/contracts/`, `lca/cognition/`, `lca/runtime/`, `lca/loop/`, `lca/framework/`, `lca_kernel/`, `vendor/`）；
  2. 严禁改动或破坏现有的 `/runs`、`/files`、`/v1/chat/completions` 等存量路由与鉴权逻辑。

### 2.2 自治等级 (AP-05)
- **评级：DRAFT 级**（纯外围插件与配置扩展，核心零侵入）。

---

## 3. 鉴权架构与双身份体系共存机制

### 3.1 路径隔离与中间件挂载机制
中间件必须严格实施**路径前缀隔离**，杜绝干扰存量接口：
1. **挂载点**：在 `routes_mangli_api.py` 的 `@plugin` `setup(ctx)` 中通过 `ctx.require("web_server").app.add_middleware(MangliAuthMiddleware)` 挂载；
2. **路径白名单/豁免规则**：
   - 中间件入口首先检查 `scope["path"]`；
   - **仅对 `/api/v1/*` 路径生效**；
   - 对 `/health`、`/runs`、`/files`、`/v1/chat/completions`、`/playground` 等非 `/api/v1` 请求，中间件**无条件直接放行（Pass-Through）**，完全不触碰现有鉴权体系。

### 3.2 双身份体系共存与优先级规范
现有身份体系基于 `x-lca-user-id` + `Bearer`（ADR-0252 D4），Mangli 引入 `X-Mangli-User` + `ticket`：
- **在 `/api/v1/*` 路径下**：
  - 生产环境：强制校验 `X-Mangli-User`。若缺失或解密失败，直接返回 401（Fail-Closed，安全优先）；
  - 身份桥接映射：从 `X-Mangli-User` 解密获取 `user_id` 后，中间件**主动在请求 scope 中注入 `scope["state"]["user_id"] = user_id` 与 `scope["headers"]` 映射**，从而使底层复用的 `create_run` 等现有 Handler 能够透明获取到合法的 LCA 用户身份；
  - 开发测试环境（`MANGLI_DEV_MOCK=true`）：允许通过直接填入 JSON Mock 用户调试；若 `MANGLI_DEV_MOCK=false`（生产默认），任何伪造或缺少加密头的请求必触发 Fail-Loud。
- **在非 `/api/v1/*` 路径下**：
  - 严格保持原有的 `x-lca-user-id` / Bearer 校验规则不变。

### 3.3 安全假设与加解密算法设计
- **安全假设明示**：`AES/ECB` 模式缺乏密文完整性校验（无 MAC/Tag）。**本方案明确建立在“统一 API Gateway 与 LCA 后端运行在企业安全内网/受控 VPC 互联环境下，网络层由内网防火墙保障不可篡改”的安全边界假设之上**。
- **解密双轨实现**：
  - **主路（推荐且最高可靠性）**：直接配置 16 字节 Hex 原始对称密钥（通过环境变量 `MANGLI_AES_KEY_HEX` 传入），避免 Python 复现 Sun JRE 内部 `SHA1PRNG` 随机数生成的平台与版本漂移风险；
  - **兼容辅路**：针对传入密码明文的情况，提供标准 SHA1PRNG 密钥派生算法；
  - **向量测试强制**：单测必须包含一组由真实 Java 编译运行产出的密文向量（已知明文 $\to$ Java 加密 $\to$ Python 解密并断言一致）。
- **零依赖高并发缓存**：
  - 不引入未在 `pyproject.toml` 中的 `cachetools`；
  - 使用 Python 标准库 `collections.OrderedDict` 与 `time.monotonic()` 编写轻量高效的 `ExpiringLruCache`（默认 5 分钟 TTL，上限 10,000 条），防止针对权限接口的网络穿透。

---

## 4. Projects 领域模型与存储设计

由于当前全仓无 Project 概念，在 `lca/infrastructure/persistence/project_store.py` 中引入标准的双后端持久化引擎（对齐已有的 `UserAssistantStore` 范式）：

### 4.1 存储 Schema 设计
- **本地/开发（SQLite，存放在 `~/.lca/lca.sqlite3`） / 生产（Postgres，由 `LCA_DATABASE_URL` 注入）**：
```sql
CREATE TABLE IF NOT EXISTS lca_projects (
    project_id    TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    owner_user_id TEXT NOT NULL,
    dept_id       TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lca_project_sessions (
    project_id    TEXT NOT NULL REFERENCES lca_projects(project_id) ON DELETE CASCADE,
    session_id    TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_lca_projects_owner ON lca_projects(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_lca_project_sessions_proj ON lca_project_sessions(project_id);
```

### 4.2 项目与会话权限规则
1. **项目隔离**：用户仅可查询自己创建的项目（`owner_user_id == current_user.user_id`）或所属部门共享的项目（`dept_id == current_user.dept_id`）；
2. **游离会话支持**：当创建会话传入 `project_id = null` 或缺省时，不向 `lca_project_sessions` 写入关联记录。查询会话列表时：
   - 传 `project_id`：仅返回该项目关联的会话；
   - 传 `unassigned=true`：仅返回该用户不属于任何项目的游离会话；
   - 不传参：返回该用户有权限的全部会话。

---

## 5. 对外 API 契约全景 (Thin Façade 代理矩阵)

统一挂载在 `/api/v1/` 下，底层复用关系严格映射如下：

| 方法 | 路径 | 业务说明 | 架构实现方式 (复用 vs 新增) |
|---|---|---|---|
| `GET` | `/api/v1/projects` | 查询用户有权访问的项目列表 | **新增**：查询 `ProjectStore` |
| `POST` | `/api/v1/projects` | 创建新项目 | **新增**：写入 `ProjectStore` |
| `GET` | `/api/v1/sessions` | 查询会话列表（支持 project_id / 游离筛选） | **薄封装**：查询底层 Session 列表 + `ProjectStore` 关联过滤 |
| `POST` | `/api/v1/sessions` | 创建会话（可指定 project_id） | **薄封装**：调用底层创建会话 + 若传 project_id 写入绑定表 |
| `GET` | `/api/v1/sessions/{id}/messages` | 会话消息历史分页 | **薄封装**：复用底层 `/runs` 事实读取逻辑 |
| `POST` | `/api/v1/sessions/{id}/runs` | 发起任务运行 | **直接复用**：`command_endpoints.create_run` |
| `GET` | `/api/v1/runs/{id}/stream` | SSE 流式输出（15s心跳防超时） | **直接复用**：`live.py:live_endpoint`（带有 `: ping\n\n` 心跳） |
| `POST` | `/api/v1/runs/{id}/cancel` | 取消任务运行 | **直接复用**：`command_endpoints.cancel_run` |
| `GET` | `/api/v1/models` | 可用模型枚举 | **直接复用**：`openai.shim:list_models` |
| `GET` | `/api/v1/files/{id}/download` | 文件下载 | **直接复用**：`files.files:download_file` |
| `GET` | `/playground` | 本地验证控制台单页 | **静态挂载**：返回无外部依赖的自包含 HTML |

---

## 6. 工具体系：契约对齐与 MCP 集群

### 6.1 严格对齐真实的 LCA Tool 模型
工具实现类继承 `lca.contracts.protocols.Tool`（参考 [`file_write.py`](file:///H:/Workspace/KLTB/SourceCode/tongbao-ai/layered-cognitive-agent/lca/plugins/tools/file_write.py)），杜绝伪造 API：
```python
class MangliTool(Tool):
  name: str
  namespace: str
  description: str
  parameters: ClassVar[dict[str, Any]]
  is_idempotent: bool
  default_timeout_s: int

  def validate(self, args: dict[str, Any]) -> str | None:
    ...

  async def execute(self, args: dict[str, Any]) -> Observation:
    ...
```
返回对象必须是 `lca.contracts.models.core.execution.decision.Observation`。

### 6.2 MCP-First 外部集群集成
- OA、Wiki、Jira、企业知识库通过标准 MCP 协议挂载；
- 采用 LCA 原生 `MCPClient`（`lca/infrastructure/mcp/`），支持 HTTP/SSE 与 stdio；
- 启动时自动完成 `tools/list` 动态拉取，零手写业务胶水代码。

---

## 7. 离线自包含的 Playground 验证控制台

文件路径：`lca/plugins/transport/webserver/static/mangli_playground.html`。
- **零外部 CDN 依赖**：严禁引用 `cdn.tailwindcss.com`。采用纯手写的现代化原生 CSS（CSS Grid/Flexbox + System Fonts），在任何离线机房或受控内网均能保证 100% 完美渲染；
- **自包含功能**：
  1. 顶部 Header 调试模拟（AES 密文输入框 / Mock 身份切换）；
  2. 左侧项目与会话树形导航；
  3. 中间打字机实时文本输出与工具调用卡片；
  4. 右侧生成文件下载列表与“一键取消运行”按钮。

---

## 8. 自动化测试不变量矩阵 (AP-02)

| 不变量编号 | 守护规则与断言 | 验证实现用例 |
|---|---|---|
| **INV-01** | Java 真实密文向量解密一致性（包含 Java SHA1PRNG 生成的静态向量及纯 Hex 密钥模式） | `tests/plugins/transport/test_mangli_auth.py::test_java_cross_compatibility_vector` |
| **INV-02** | 权限接口 5 分钟 TTL 缓存命中与网络容灾降级（纯标准库 `ExpiringLruCache`） | `tests/plugins/transport/test_mangli_auth.py::test_permission_cache_ttl_and_error_handling` |
| **INV-03** | 中间件路径隔离（非 `/api/v1` 100% 豁免，不干扰存量 Bearer/x-lca-user-id） | `tests/plugins/transport/test_routes_mangli_api.py::test_middleware_path_exemption` |
| **INV-04** | Projects 持久化 CRUD、游离会话与项目成员权限隔离 | `tests/plugins/persistence/test_project_store.py::test_project_isolation_and_unassigned_sessions` |
| **INV-05** | Thin Façade 接口调用与真实底层 Handler 复用性（Runs/Stream/Cancel/Models/Files） | `tests/plugins/transport/test_routes_mangli_api.py::test_thin_facade_endpoints_and_sse_stream` |
| **INV-06** | 真实工具契约符合性（继承 `Tool`，返回 `Observation`） | `tests/plugins/tools/test_mangli_enterprise_tools.py::test_tool_conforms_to_lca_contract` |
| **INV-07** | **真实分支合并基线零修改铁律**：`git diff --name-only origin/main...HEAD -- lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel vendor` 退出码必为 0 且输出必为空！ | `tests/plugins/test_mangli_core_zero_mutation_guard.py::test_core_zero_mutation_against_merge_base` |
| **INV-08** | 单页 Playground 接口访问断言（`GET /playground` 返回 200，纯内网离线自包含无外部 CDN） | `tests/plugins/transport/test_playground_endpoint.py::test_playground_offline_render` |
