# 企业级应用集成与统一接口封装设计 (Mangli Enterprise Integration Design)

> **设计状态：** Approved (严格对齐 R1~R18 架构审查、安全边界与运行时闭环版)  
> **自治等级：** STABLE (外围插件 Seam/Provider 范式，严格守护底层核心单向依赖)  
> **设计日期：** 2026-11-17  
> **宪法约束：** 遵照根目录 `AGENTS.md`（C1 认知闭集、C2 双平面、C4 Reducer单写、C5 能力单调、C6 最小化、C10 执行窄门、C11 事件闭集、C13 信息血统闭合、C14 图与业务隔离）。

---

## 1. 架构定位：原生 URL 全盘复用与系统归属边界

### 1.1 拒绝双套 URL，全面复用既有标准端点
系统**坚决不新建平行冗余的 `/api/v1` URL 副本**。无论是公司前端组、公司 Gateway、Playground 还是既有的 LobeHub 测试端，统一直接复用成熟的原生端点：
- **发起任务**：`POST /runs`（直接复用 `command_endpoints:create_run`，返回 `run_id` 与 `ws_token`）
- **实时全双工流式输出**：`WS /v1/runs/{run_id}/ws`（直接复用原生基于 Redis Stream 的 WebSocket 通道，建连首帧发送 `{type: "auth", token: ws_token}` 进行 JWT 校验，带 30s 双向心跳保活防断连）
- **取消任务**：`POST /runs/{id}/cancel`（直接复用 `cancel_run`）
- **人机交互答复**：`POST /runs/{id}/answer`（直接复用 `answer_run`）
- **文件下载**：`GET /files/{attachment_id}`（直接复用 `_download_file`，见 `lca/plugins/transport/webserver/routes_1/routes_openai_compat_files.py:42, 56`）
- **模型枚举**：`GET /v1/models`（直接复用 `list_models`）
- **验证控制台**：`GET /playground`（纯静态 HTML 控制台，兼测两套身份与 WebSocket 打字机）

### 1.2 归属层架构决策（选定方案 A）(R4)
- **实体归属边界**：项目（Project）、会话（Session）与消息历史（Message）由公司前端组或公司 Java 后端统一持有并持久化存储；LCA 作为底层无状态认知执行内核，专注于单次执行（Runs）、流式推送（WS）和产物文件下载（Files）；
- **LCA 内部绝不引入 ProjectStore**：LCA 内部坚决不建任何项目或会话数据库表；
- **租户上下文透传预留**：`project_id` 仅作为外部租户审计与沙箱隔离的元数据标签，通过 `Principal.project_id` 上下文随请求透传，在 `POST /runs` 的 `options={"project_id": ...}` 中进入 Session 元数据，并在文件导出工具中用于隔离目录。

---

## 2. 自适应双轨鉴权与安全闭环 (Smart Adaptive Auth Bridge)

### 2.1 核心设计：标准化 `Principal` 模型与 ADR-0252 修订 (R1, R3, R5, R16)
为了彻底解决原生 `/runs` 不校验 Token 的安全缺陷，所有安全校验前移至最外层的 `SmartAdaptiveAuthMiddleware`。同时修订 ADR-0252 D4，将原有的 `(user_id, error)` 简单元组升级为强类型的不可变 `Principal` 身份对象（严格遵循 C13 信息血统闭合契约）：

```python
# lca/plugins/transport/webserver/handlers/auth/principal.py
from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
  """全仓跨边界传递的统一可信身份模型（修订 ADR-0252 D4 / C13 强类型闭合）。"""

  model_config = ConfigDict(frozen=True, extra="forbid")

  issuer: str  # "mangli" | "lobehub" | "system"
  subject: str  # 用户工号或身份唯一标识 (例如 "U888" 或 "usr_lobe")
  dept_id: str | None = None
  roles: tuple[str, ...] = ()
  project_id: str | None = None  # 外部租户项目标签
```

```mermaid
flowchart TD
    Req[客户端请求进入 Web 容器] --> TraceMW[1. TraceIdMiddleware 最外层<br>生成全局 trace_id]
    TraceMW --> AuthMW[2. SmartAdaptiveAuthMiddleware<br>自适应双轨鉴权与安全防护]
    
    AuthMW --> CheckHeader{Header 中是否包含<br>X-Mangli-User ?}
    
    CheckHeader -->|包含: 公司 Gateway 流量| MangliTrack[公司专属网关轨]
    CheckHeader -->|不包含: 内网直连 / LobeHub 流量| LobeHubTrack[内网 / LobeHub 轨]

    subgraph MangliTrack [公司网关流量处理]
        HexDec[a. Hex解码 + AES/ECB/PKCS5Padding 解密<br>失败直接拦截返回 401]
        PermFetch[b. 透传 ticket 查权限 Code（默认关闭）<br>5min LRU 缓存; 查询失败降级为空权限<br>ticket 明确无效返回 401]
        StripSpoof[c. 强制剥离客户端伪造的 x-lca-user-id / authorization]
        InjectReal[d. 注入真实 x-lca-user-id 与合法 Bearer expected_token<br>构造 Principal(issuer='mangli')<br>写入 request.state.principal 与 ContextVar]
        HexDec --> PermFetch --> StripSpoof --> InjectReal
    end

    subgraph LobeHubTrack [内网直连处理]
        CheckDev{是否处于生产环境<br>dev_mode == False ?}
        CheckDev -->|是: 生产环境| VerifyBearer[强制校验 Authorization: Bearer<br>缺 Token 或 Token 错误直接拦截返回 401]
        CheckDev -->|否: 本地开发| AllowDev[放行或回落 local-dev-user]
        VerifyBearer --> ConstructLobe[构造 Principal(issuer='lobehub')<br>写入 request.state.principal 与 ContextVar]
        AllowDev --> ConstructLobe
    end

    InjectReal --> Router[3. 进入路由层: create_run / ws / files]
    ConstructLobe --> Router
```

### 2.2 中间件挂载顺序与 Starlette 运行时实测 (R16)
Starlette 的 `app.add_middleware` 内部使用 `insert(0, ...)`，因此**后添加的中间件在请求到达时先执行（处于更外层）**。  
在 `lca/plugins/transport/webserver/server/server.py` 中，执行如下挂载顺序：
1. 先执行 `install_adaptive_auth_middleware(app)`（挂载到内层）；
2. 后执行 `install_trace_middleware(app)`（挂载到最外层）。  
**实际执行顺序（从外到内）**：
`TraceIdMiddleware`（最先进入，生成全局 `trace_id`） → `SmartAdaptiveAuthMiddleware`（安全守门，即使返回 401/503 也带有合法 `trace_id`） → 路由层 Handler。

### 2.3 伪造头剔除与 Bearer 注入规范 (R1, R5)
1. **伪造头强制剥离（Header Spoofing 防御）**：
   * 客户端在携带 `X-Mangli-User` 时，可能恶意附加 `x-lca-user-id: admin`；
   * 中间件在重构 `scope["headers"]` 时，首先剔除所有客户端传入的 `x-lca-user-id`、`authorization`、`x-lca-token`，绝不允许伪造头透传；
2. **合法 Bearer 动态桥接**：
   * 中间件从 `request.app.state` 读取 `lca_auth_expected_token`，并在桥接时注入 `Authorization: Bearer <expected_token>`，使网关流量能够 100% 通过下游原生鉴权；
3. **生产环境关闭 `dev_mode` 绝不敞开**：
   * 在 `profiles/mangli-enterprise.yaml` 中将 `dev_mode` 设为 `false`；对于未带 `X-Mangli-User` 的请求，缺少合法 Bearer 直接返回 401，彻底消除内网伪造身份绕过的隐患。

### 2.4 非 HTTP 场景身份语义规范 (R11)
- **HITL 审批恢复**：当处于 Human-In-The-Loop 审批恢复阶段时，系统从持久化的 `AgentState` 中还原创建该 Run 时的原始 `Principal`，防止权限漂移；
- **Cron 调度任务**：后台定时调度任务使用受限的系统主体：
  ```python
  SYSTEM_PRINCIPAL = Principal(
      issuer="system",
      subject="cron-daemon",
      roles=("system",),
  )
  ```
  对租户敏感资源（如特定用户沙箱文件）执行严格的 Fail-Closed 访问拦截。

---

## 3. 多租户 Run 并发去重隔离 (M9, R10)

### 3.1 漏洞根因与当期修复 (M9)
原生 `run_dedup_key`（[index.py](lca/plugins/transport/webserver/handlers/runs/session/index/index.py#L27-L42)）哈希字段仅包含 `mode`、`principal`（`agent_id`）、`normalized`（`user_text`）和 `attachments`，遗漏了 `user_id`。  
**修复方案**：将 `user_id` 作为哈希首要维度：
```python
payload = f"{user_id}\0{mode}\0{principal}\0{normalized}\0{attachments}"
```
并在 `find_inflight_run` 和 `create_and_dispatch` 中全链路透传。

### 3.2 多租户隔离二期跟进点 (R10)
- **FileStore 租户隔离**：二期在 `FileRecord` 增加 `owner_principal` 字段，跨租户尝试下载非自己所属的附件时返回 404 Not Found；
- **topic_id 命名空间隔离**：二期对 `topic_id` 自动加上 `principal.issuer:principal.subject` 前缀，实现会话域严格隔离。

---

## 4. WebSocket 流式通信原生协议标准 (R6)

LCA 生产环境的原生流式协议由 `agent_gateway.py` 支撑，严格遵循首帧鉴权长连接规范：

1. **建立 WebSocket**：
   客户端发起连接 `ws://<host>:<port>/v1/runs/{run_id}/ws`（**URL 不带 Token 参数**）；
2. **首帧认证握手**：
   客户端必须发送的第一帧报文为：
   ```json
   {"type": "auth", "token": "<ws_token>"}
   ```
   * 服务端调用 `verify_user_jwt(token, expected_operation_id=run_id)` 验证；
   * 若 Token 的 `sub` 与该 Run 的所属用户不一致，服务端直接回送 `{"type": "auth_failed"}` 并切断连接；
   * 校验通过回发 `{"type": "auth_success"}`；
3. **心跳保活与重放**：
   * 客户端每 30 秒发送 `{"type": "heartbeat"}`，服务端回复 `{"type": "heartbeat_ack"}`，防止网关连接超时断开；
   * 实时事件以 `{"type": "agent_event", "event": ...}` 推送，执行结束以 `{"type": "session_complete"}` 关闭连接。

---

## 5. 工具体系、执行窄门与 MCP 集群 (M5, M6, R8, R9)

### 5.1 严格符合 LCA `Tool` 协议 (M5, R8)
工具必须实现 `Tool(Protocol)`（`lca/contracts/protocols/runtime/infra/infra.py:60-79`）声明的 7 项 ClassVar：
```python
class MangliWorkspaceExportTool(Tool):
  name: ClassVar[str] = "mangli_workspace_export"
  namespace: ClassVar[str] = "workspace"
  description: ClassVar[str] = (
      "Export text/data content to user workspace file."
  )
  parameters: ClassVar[dict[str, Any]] = {
      "type": "object",
      "properties": {
          "path": {"type": "string", "description": "Relative filename"},
          "content": {"type": "string", "description": "File text content"},
      },
      "required": ["path", "content"],
  }
  is_idempotent: ClassVar[bool] = False
  effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = (
      "persistent"
  )
  default_timeout_s: ClassVar[int] = 30

  async def execute(self, args: dict[str, Any]) -> Observation:
    ...
```
并通过 `tools_seam.register_factory("mangli_workspace_export", factory)` 注册，工厂入参为 `bindings: BindingsView`。

### 5.2 执行窄门与租户边界防越权 (M6, R8)
1. **租户参数隔离**：模型的调用参数（`parameters`）中**严禁包含 `project_id`、`session_id` 或 `user_id`**，防止模型注入造成跨租户越权访问；租户上下文统一在工厂构造工具实例时从 `bindings: BindingsView` / 运行时上下文静默注入；
2. **遵守 C10/C11 窄门与事件闭集**：工具执行统一交由 `SimpleSafeExecutor` 调度并自动记录 `ToolStarted` / `ToolInvoked`，工具内部严禁私自发射非白名单的自定义 Journal 事件；
3. **复用原生 `LocalFileStore`**：文件落地调用成熟的 `file_store.put(data=..., name=..., mime_type=..., origin="agent_created")`，返回标准的 `attachment_id`，前端统一通过原生 `/files/{attachment_id}` 接口下载。

### 5.3 外部数据 MCP 集群规范与跟进点 (R9)
- **凭据与鉴权规范**：OA、Wiki、Jira、企业知识库走标准 MCP 协议，采用服务账号（Service Account）+ `_meta` 签名断言鉴权；`ticket` 严禁进模型参数，严禁在 Spine 日志中明文打印；
- **配置与维护责任**：`mcp.yaml` 由网关与部署团队统一维护连接地址与签名密钥；
- **启动检查**：若配置了必选 MCP Server，启动时执行健康检查，不可达则 fail-closed 告警。

---

## 6. 声明式编排与插件元数据规范 (M1, M2, M3, R2, R7, Q2)

### 6.1 标准 Bundle 定义 (`bundles/mangli-enterprise.yaml`) (M1, R7)
遵循解析器 `entries:` 结构，严格钉死插件 ID：
```yaml
entries:
  - id: mangli-enterprise-playground-route
    name: mangli_enterprise_playground_route
    $module: lca.plugins.transport.webserver.routes_mangli_playground
    config: {}
  - id: mangli-enterprise-tools
    name: mangli_enterprise_tools
    $module: lca.plugins.tools.mangli_enterprise_tools
    config: {}
```

### 6.2 生产级 Profile 声明 (`profiles/mangli-enterprise.yaml`) (M2, R2, Q2)
挂载生产级所需的 14 个 bundles + `bundles/assistant-runtime.yaml`，并在末尾挂载专属 bundle；通过官方真实 ID `lca.plugins.assistant.ownership` 准确 patch 生产环境配置：
```yaml
bundles:
  - bundles/base.yaml
  - bundles/observability-default.yaml
  - bundles/observation-9module.yaml
  - bundles/web-app.yaml
  - bundles/scenario-cordis-creator.yaml
  - bundles/loop_cursor.spine_default.yaml
  - bundles/session-runtime.yaml
  - bundles/event-bus-components.yaml
  - bundles/outer/phase_main.yaml
  - bundles/think/think_subgraph.yaml
  - bundles/act/act_subgraph.yaml
  - bundles/perceive/perceive_subgraph.yaml
  - bundles/reflect/reflect_subgraph.yaml
  - bundles/remember/remember_subgraph.yaml
  - bundles/assistant-runtime.yaml
  - bundles/mangli-enterprise.yaml

patch:
  - id: spine.sink.file
    config:
      boot_path: .lca/spine/boot-spine.jsonl
      runs_root: {from_env: LCA_RUNS_ROOT}
  - id: lca-effect-permission-manifest-default
    disabled: true
  - id: lca.plugins.assistant.ownership
    config:
      dev_mode: false
      expected_token:
        from_env: LCA_AUTH_EXPECTED_TOKEN
        required: true
```

### 6.3 `@plugin` 完整装饰器契约 (M3, R7)
所有新增插件严格满足 `layer="L1"`、`kind=PluginKind.PROVIDER`、`effects="none"`、`contract=PluginContract(...)`、`ownership=OwnershipDeclaration(...)`，插件 ID 严格与 Bundle 保持一致。

---

## 7. 边界划分与 Owns 清单 (AP-01 & M8)

### 7.1 负向边界 (Does NOT own)
严禁触碰任何核心层代码：
- `lca/contracts/`
- `lca/cognition/`
- `lca/runtime/`
- `lca/loop/`
- `lca/framework/`
- `lca_kernel/`
- `vendor/`

### 7.2 正向职责 (Owns)
本次集成仅允许修改或创建以下范围内的文件：
- **身份模型与鉴权中间件**：
  - `lca/plugins/transport/webserver/handlers/auth/principal.py` (新增)
  - `lca/plugins/transport/webserver/handlers/auth/mangli_auth.py` (新增)
  - `lca/plugins/transport/webserver/server/server.py` (修改：规范挂载中间件 Seam)
- **多租户去重安全修复**：
  - `lca/plugins/transport/webserver/handlers/runs/session/index/index.py` (修改：加入 user_id)
  - `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py` (修改：透传 user_id)
- **工具与静态控制台**：
  - `lca/plugins/tools/mangli_enterprise_tools.py` (新增)
  - `lca/plugins/transport/webserver/routes_mangli_playground.py` (新增：挂载 /playground 路由)
  - `lca/plugins/transport/webserver/static/mangli_playground.html` (新增)
- **编排配置**：
  - `bundles/mangli-enterprise.yaml` (新增)
  - `profiles/mangli-enterprise.yaml` (新增)
- **测试套件**：
  - `tests/plugins/transport/test_mangli_auth.py`
  - `tests/plugins/transport/test_multitenant_inflight_run_dedup.py`
  - `tests/plugins/tools/test_mangli_enterprise_tools.py`
  - `tests/plugins/transport/test_mangli_playground.py`
  - `tests/scenario/test_mangli_enterprise_bundle_invariants.py`

---

## 8. 自动化测试不变量矩阵 (AP-02, M7, R17, R18)

| 不变量编号 | 守护规则与断言 | 验证用例 |
|---|---|---|
| **INV-01** | Java 原生静态密文向量解密一致性（包含 16 字节 Hex 密钥主路与固定 Java 向量三元组） | `test_java_cross_compatibility_vector` |
| **INV-02** | 权限 Code 5 分钟 TTL 缓存命中与非阻断降级（查询失败降级为空权限、不阻断身份；ticket 明确无效返回 401） | `test_permission_cache_ttl_and_error_handling` |
| **INV-03** | 自适应双轨鉴权隔离（生产无 Token 拦截、有网关头解密 + 伪造头剥离 + 合法 Bearer 注入 + 建立 Principal）与解密失败 401 阻断 | `test_adaptive_auth_double_track` |
| **INV-04** | 多租户 In-flight Run 并发去重隔离（不同用户的相同提问互不干扰） | `test_multitenant_inflight_run_dedup_isolation` |
| **INV-05** | 真实工具契约符合性（继承 `Tool`，声明 7 项 ClassVar，返回 `Observation`，沙箱文件写入生成 `FileStore` 凭证） | `test_tool_conforms_to_lca_contract` |
| **INV-06** | Playground 离线自包含与真实 200 响应（通过 TestClient 真实调用 `GET /playground` 返回 200，且无外网 CDN） | `test_playground_offline_render` |
| **INV-07** | **分支基线零修改铁律**：`git diff --name-only origin/main...HEAD -- lca/contracts lca/cognition lca/runtime lca/loop lca/framework lca_kernel vendor` 退出码必为 0 且输出必为空！ | `test_core_zero_mutation_against_merge_base` |
