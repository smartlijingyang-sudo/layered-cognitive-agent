# LCA 执行架构对齐计划 — 全覆盖 8 个 Gap

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

**Goal:** 全面对齐 LobeHub 执行架构，消除全部 8 个 gap，用 `lca` CLI（npm）替代 `python -m host`，模块化、架构优雅。

**Architecture:**
- `lca connect` CLI (npm) — 复用 `@lobechat/device-gateway-client`，heartbeat + 指数退避 + JWT
- Device-gateway HTTP routes — 标准 `/api/device/*` relay，替代自建 presence 协议
- Tool model — manifest + executor + observations 三层分离，一组工具一个模块
- executionTarget — sandbox / device / auto / none 三层决策，带 fallback
- SandboxPolicy — 可写根 / 禁写根 / 网络策略 / 环境白名单，SRT 进程隔离
- 用户模型 — JWT/serviceToken 认证，workspace 级设备池

**Tech Stack:** TypeScript (CLI + device-gateway-client), Python (Gateway + Run Engine + Tool Executors), SQLite (设备注册持久化), WebSocket

---

## Gap 覆盖矩阵

| Gap | 问题 | 对齐方案 | Phase |
|---|---|---|---|
| G1 | 自定义 presence 协议 | 用 `GatewayClient` 标准 WS 协议 (auth→heartbeat→tool_call) | P1 |
| G2 | 固定 2s 重连，无心跳 | GatewayClient 自带 heartbeat 30s + 指数退避 + token 刷新 | P1 |
| G3 | 设备发现无持久化 | SQLite 设备注册表 + `/api/device/*` HTTP routes | P2 |
| G4 | 工具模型（扁平 Python 类 vs manifest+executor） | manifest + executor + observations 三层，一组工具一模块 | P3 |
| G5 | 执行路由二选一无 fallback | executionTarget 三层决策 (sandbox/device/auto/none) + fallback | P4 |
| G6 | 硬编码用户，无认证 | serviceToken/JWT 认证 + workspace 设备池 | P5 |
| G7 | WS base64 传输 attachment，TOCTOU | HTTP relay 传文件，或 workspace mount 直接读 | P2 |
| G8 | 无沙箱策略层 | SandboxPolicy 模型 + SRT 进程隔离 + Docker 云沙箱 | P6 |

---

## Phase 1: LCA CLI (`lca connect`) — 覆盖 G1, G2

**目标：** npm CLI 替代 `python -m host`，用 LobeHub 标准 GatewayClient。

### Task 1.1: 脚手架 `@lca/cli` 包

**Files:**
- Create: `packages/lca-cli/package.json`
- Create: `packages/lca-cli/tsconfig.json`
- Create: `packages/lca-cli/src/index.ts`
- Create: `packages/lca-cli/src/commands/connect.ts`
- Create: `packages/lca-cli/src/daemon.ts`
- Create: `packages/lca-cli/src/tools/index.ts`
- Create: `packages/lca-cli/src/tools/fileOps.ts`
- Create: `packages/lca-cli/src/tools/shellOps.ts`
- Create: `packages/lca-cli/src/tools/codeOps.ts`

**核心依赖：**
```json
{
  "dependencies": {
    "@lobechat/device-gateway-client": "workspace:*",
    "@lobechat/local-file-shell": "workspace:*",
    "@lobechat/device-control": "workspace:*",
    "@lobechat/device-sandbox": "workspace:*",
    "commander": "^12.0.0"
  }
}
```

**`connect.ts` 核心逻辑：**
```typescript
import { GatewayClient } from '@lobechat/device-gateway-client';
// GatewayClient 自带：
// - auth → auth_success 握手
// - heartbeat 30s + heartbeat_ack
// - 指数退避重连 1s→2s→4s→…→30s
// - 3 missed heartbeat → 强制重连
// - token 过期 → auth_expired 事件 → 刷新重连
// - workspace 设备共享

const client = new GatewayClient({
  deviceId: identity.deviceId,
  gatewayUrl: options.gateway,
  token: connectToken,
  tokenType: 'serviceToken',  // 或 'jwt'
  channel: 'cli',
  connectionId: loadOrCreateConnectionId(),
  // GatewayClient 内部处理全部连接生命周期
});

client.on('tool_call_request', async (request) => {
  const result = await executeToolCall(request.toolCall.apiName, request.toolCall.arguments);
  client.sendToolCallResponse({ requestId: request.requestId, result });
});

client.on('rpc_request', async (request) => {
  const data = await executeDeviceRpc(request.method, request.params);
  client.sendRpcResponse({ requestId: request.requestId, result: { data, success: true } });
});

client.on('agent_run_request', async (request) => {
  const ack = await spawnAgentRun(request);
  client.sendAgentRunAck({ operationId: request.operationId, ...ack });
});

await client.connect();
```

**daemon 模式：**
- `lca connect --daemon` → spawn detached child, write PID to `~/.lca/connect.pid`
- `lca connect stop` → SIGTERM to PID
- `lca connect status` → show PID, connection status, gateway URL
- `lca connect service install` → systemd user service（Linux）

- [x] 创建包，实现 connect/stop/status/daemon
- [x] 验证：`lca connect --daemon` 启动并自动重连
- [x] Commit

---

### Task 1.2: 工具执行层

**Files:**
- Create: `packages/lca-cli/src/tools/index.ts` — dispatch by apiName
- Create: `packages/lca-cli/src/tools/fileOps.ts` — 复用 `@lobechat/local-file-shell`
- Create: `packages/lca-cli/src/tools/shellOps.ts` — subprocess with background support
- Create: `packages/lca-cli/src/tools/codeOps.ts` — Python/JS/TS code execution

**对齐 LobeHub 的 apiName：**
```typescript
// 与 LobeHub builtin-tool-local-system 的 apiName 完全一致
const API_MAP = {
  listFiles: 'listFiles',
  readFile: 'readFile',
  writeFile: 'writeFile',
  editFile: 'editFile',
  searchFiles: 'searchFiles',
  moveFiles: 'moveFiles',
  grepContent: 'grepContent',
  globFiles: 'globFiles',
  runCommand: 'runCommand',
  getCommandOutput: 'getCommandOutput',
  killCommand: 'killCommand',
  executeCode: 'executeCode',   // cloud-sandbox 也有
  exportFile: 'exportFile',     // cloud-sandbox 也有
};
```

- [x] 实现全部 API 的执行逻辑
- [x] workspace 统一 `/home/sandbox-user`
- [x] Commit

---

## Phase 2: Device Gateway in LCA Gateway — 覆盖 G3, G7

**目标：** 标准 `/api/device/*` HTTP routes + WS endpoint + SQLite 设备注册 + HTTP 文件传输。

### Task 2.1: 设备注册表（SQLite 持久化）

**Files:**
- Create: `gateway/device_gateway/__init__.py`
- Create: `gateway/device_gateway/registry.py` — SQLite-backed device registry
- Create: `gateway/device_gateway/models.py` — Device 数据模型

**对齐 LobeHub 的 GatewayDevice 结构：**
```python
@dataclass
class DeviceConnection:
    """一次 WebSocket 连接"""
    connection_id: str          # per-install UUID（去重用）
    channel: str                # 'cli' | 'desktop' | 'desktop-dev'
    connected_at: datetime
    websocket: WebSocket

@dataclass
class Device:
    """一台物理设备，可有多个连接"""
    device_id: str              # stable per-machine ID
    hostname: str
    platform: str               # linux | darwin | win32
    home: str
    workspace: str              # /home/sandbox-user
    channels: list[DeviceConnection]
    registered_at: datetime
    user_id: str                # 设备归属用户
    workspace_id: str | None    # workspace 级设备（共享）

class DeviceRegistry:
    """SQLite 持久化设备注册表"""
    
    def __init__(self, db_path: str) -> None:
        self._db = sqlite3.connect(db_path)
        self._live: dict[str, Device] = {}  # device_id → Device (内存在线状态)
    
    async def register_device(self, device_id: str, ...) -> Device:
        """持久化注册（幂等 upsert）"""
    
    async def attach_channel(self, device_id: str, conn: DeviceConnection) -> None:
        """设备上线，添加 channel"""
    
    async def detach_channel(self, device_id: str, connection_id: str) -> None:
        """设备下线，移除 channel"""
    
    def list_online(self, user_id: str | None = None) -> list[Device]:
        """列出在线设备（可按用户过滤）"""
    
    async def call_tool(self, device_id: str, tool_call: dict, timeout_s: float) -> dict:
        """路由工具调用到设备，等待响应"""
```

**关键设计：**
- 设备注册持久化到 SQLite → gateway 重启后设备记录不丢
- 在线状态在内存 → channel 断开即 offline
- 一个 device_id 可以有多个 channel（desktop + cli 同时连接）
- 对齐 LobeHub 的 `GatewayDevice` 结构（channels 嵌套在 device 下）

- [x] 实现 SQLite 注册表
- [x] 设备注册幂等 upsert
- [x] Commit

---

### Task 2.2: HTTP 路由 + WS endpoint

**Files:**
- Create: `gateway/device_gateway/routes.py`

**对齐 LobeHub 的 `/api/device/*` 路由：**

| 路由 | LobeHub 原生 | LCA 实现 |
|---|---|---|
| `POST /api/device/status` | 查询设备在线状态 | ✅ 查 registry |
| `POST /api/device/devices` | 列出设备 | ✅ 查 registry |
| `POST /api/device/tool-call` | 路由工具调用到设备 | ✅ WS relay |
| `POST /api/device/system-info` | 查询设备系统信息 | ✅ WS relay |
| `POST /api/device/rpc` | 通用 RPC relay | ✅ WS relay |
| `POST /api/device/agent/run` | 派发 agent run | ✅ WS relay |
| `WS /api/device/ws` | 设备连接 | ✅ GatewayClient 协议 |
| `POST /api/device/files/upload` | 文件上传到设备 | ✅ 新增，解决 G7 |

**WS 协议完全对齐 LobeHub：**
```
Client → Server:
  { type: "auth", token, tokenType, serverUrl }
  { type: "heartbeat" }
  { type: "tool_call_response", requestId, result }
  { type: "rpc_response", requestId, result }
  { type: "system_info_response", requestId, result }
  { type: "agent_run_ack", operationId, status }

Server → Client:
  { type: "auth_success" }
  { type: "auth_failed", reason }
  { type: "auth_expired" }
  { type: "heartbeat_ack" }
  { type: "tool_call_request", requestId, toolCall, timeout }
  { type: "rpc_request", requestId, method, params }
  { type: "system_info_request", requestId }
  { type: "agent_run_request", operationId, agentType, prompt, ... }
```

**Attachment 传输对齐 (G7)：**
```python
# POST /api/device/files/upload
# 把 attachment 文件通过 HTTP 发到设备 workspace
async def upload_files(request: Request) -> JSONResponse:
    body = await request.json()
    device_id = body["deviceId"]
    files = body["files"]  # { name: { b64: "..." } | { url: "..." } }
    base_dir = body.get("baseDir", "/home/sandbox-user")

    result = await registry.call_tool(
        device_id,
        {
            "identifier": "lca-computer",
            "apiName": "writeFiles",
            "arguments": json.dumps({"files": files, "base_dir": base_dir}),
        },
        timeout_s=60,
    )

    return JSONResponse(result)
```

- [x] 实现全部 HTTP 路由
- [x] 实现 WS endpoint（对齐 LobeHub 协议）
- [x] 实现文件上传路由
- [x] 注册到 `gateway/app.py`
- [x] Commit

---

### Task 2.3: GatewayHttpClient — 替代 HostSandbox

**Files:**
- Create: `lca/infrastructure/device_gateway/__init__.py`
- Create: `lca/infrastructure/device_gateway/client.py`

```python
class GatewayHttpClient:
    """对齐 LobeHub 的 GatewayHttpClient"""
    
    async def query_device_status(self, user_id: str) -> DeviceStatusResult: ...
    async def query_device_list(self, user_id: str) -> list[GatewayDevice]: ...
    async def execute_tool_call(self, params, tool_call) -> DeviceToolCallResult: ...
    async def execute_mcp_call(self, mcp_call) -> DeviceToolCallResult: ...
    async def invoke_rpc(self, params, rpc) -> DeviceRpcResult: ...
    async def upload_files(self, device_id, files, base_dir) -> ToolCallResult: ...
    async def dispatch_agent_run(self, params) -> AgentRunResult: ...
```

**Attachment staging 改用 HTTP：**
```python
async def _stage_machine_attachments(session: RunSession) -> None:
    # 通过 HTTP relay 传文件，不走 WS base64
    client = get_device_gateway_client()
    result = await client.upload_files(
        device_id=machine.id,
        files=encoded_files,
        base_dir=machine.root,
    )
    if not result.success:
        raise RuntimeError(f"failed to stage: {result.error}")
```

- [x] 实现 GatewayHttpClient
- [x] 更新 execute.py 的 attachment staging
- [x] Commit

---

## Phase 3: 工具模型对齐 — 覆盖 G4

**目标：** manifest + executor + observations 三层分离，一组工具一模块。对齐 LobeHub 的 `builtin-tool-cloud-sandbox` / `builtin-tool-local-system` 结构。

### 当前 LCA 工具结构（问题）

```
lca/infrastructure/tools/
  computer/
    specs.py          # 所有工具定义挤在一个文件
    handlers.py       # 所有 handler 挤在一个文件
    descriptions.py   # 描述文本
    observations.py   # journal observations
    tool_set.py       # 工具集组装
```

**问题：** 
- 一个文件塞所有工具，违反单一职责
- 工具定义（manifest）和执行逻辑（handler）混在一起
- 没有标准化 manifest 格式，不能和 LobeHub UI 共享

### 目标结构（对齐 LobeHub）

```
lca/infrastructure/tools/
  lca_computer/                    # = builtin-tool-local-system
    __init__.py                    # re-export manifest + executor
    manifest.py                    # Tool manifest (JSON schema for LLM)
    executor.py                    # 路由到 device via GatewayHttpClient
    system_role.py                 # system prompt
    types.py                       # ApiName enum, param types
    apis/                          # 每个 API 一个文件
      list_files.py
      read_file.py
      write_file.py
      edit_file.py
      search_files.py
      move_files.py
      grep_content.py
      glob_files.py
      run_command.py
      get_command_output.py
      kill_command.py
    observations.py                # journal observations
  
  lca_sandbox/                     # = builtin-tool-cloud-sandbox
    __init__.py
    manifest.py                    # 包含 executeCode, exportFile 等沙箱独有 API
    executor.py                    # 路由到 sandbox
    system_role.py
    types.py
    apis/
      execute_code.py
      export_file.py
    observations.py
  
  web_search/                      # = builtin-tool-web-browsing (简化版)
    __init__.py
    manifest.py
    executor.py
  
  ask_user/                        # human-in-the-loop
    __init__.py
    manifest.py
    executor.py
```

### Manifest 格式（对齐 LobeHub BuiltinToolManifest）

```python
# lca/infrastructure/tools/lca_computer/manifest.py
from lca.contracts.models.core.tool import ToolManifest, ToolApi

IDENTIFIER = "lca-computer"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    executors=["client", "server"],  # 可以在 device (client) 或 gateway (server) 执行
    meta=ToolMeta(
        avatar="📁",
        title="Local Computer",
        description="Access files, run commands on this machine",
    ),
    system_role=system_prompt,
    api=[
        ToolApi(
            name="listFiles",
            description="List files and folders in a directory",
            parameters={
                "type": "object",
                "properties": {
                    "directoryPath": {
                        "type": "string",
                        "description": "The directory path to list",
                    },
                },
                "required": ["directoryPath"],
            },
            default_timeout_ms=30_000,
        ),
        ToolApi(
            name="readFile",
            description="Read the content of a file",
            parameters={...},
            human_intervention=HumanInterventionPolicy.PATH_SCOPE_AUDIT,
        ),
        # ...
    ],
)
```

### 契约层新增 ToolManifest

```python
# lca/contracts/models/core/tool.py (新增)
@dataclass(frozen=True)
class ToolApi:
    name: str
    description: str
    parameters: dict[str, Any]
    human_intervention: str | dict = "never"
    default_timeout_ms: int = 30_000


@dataclass(frozen=True)
class ToolMeta:
    avatar: str = ""
    title: str = ""
    description: str = ""


@dataclass(frozen=True)
class ToolManifest:
    identifier: str
    type: str  # "builtin"
    api: tuple[ToolApi, ...]
    executors: tuple[str, ...] = ("server",)
    meta: ToolMeta = ToolMeta()
    system_role: str = ""
```

### Executor 模式

```python
# lca/infrastructure/tools/lca_computer/executor.py
from lca.infrastructure.device_gateway.client import GatewayHttpClient


class LcaComputerExecutor:
    """Routes tool calls to the connected device via device-gateway."""

    identifier = "lca-computer"

    def __init__(self, client: GatewayHttpClient, device_id: str) -> None:
        self._client = client
        self._device_id = device_id

    async def invoke(self, api_name: str, params: dict, ctx: dict) -> dict:
        result = await self._client.execute_tool_call(
            api_name=api_name,
            arguments=params,
            device_id=self._device_id,
        )
        return {
            "content": result.content,
            "state": result.state,
            "success": result.success,
            "error": result.error,
        }

    async def list_files(self, params, ctx):
        return await self.invoke("listFiles", params, ctx)

    async def read_file(self, params, ctx):
        return await self.invoke("readFile", params, ctx)

    # ...
```

### 工具注册

```python
# lca/infrastructure/tools/default_set.py (重写)
from lca.infrastructure.tools.lca_computer import MANIFEST as COMPUTER_MANIFEST
from lca.infrastructure.tools.lca_sandbox import MANIFEST as SANDBOX_MANIFEST


def build_default_tools(store, bindings):
    tools = []

    # 根据 executionTarget 选择工具集
    if machine_plane:
        # 添加 computer 工具（manifest.api 里的每个 API 变成一个 Tool）
        for api in COMPUTER_MANIFEST.api:
            tools.append(ComputerTool(api, executor))

    if sandbox_plane:
        # 添加 sandbox 工具
        for api in SANDBOX_MANIFEST.api:
            tools.append(SandboxTool(api, executor))

    return tools
```

- [x] 新增 `ToolManifest` 契约
- [x] 创建 `lca_computer/` 模块结构
- [x] 创建 `lca_sandbox/` 模块结构
- [x] 迁移 specs.py → apis/*.py
- [x] 迁移 handlers.py → executor.py
- [x] 更新 default_set.py 使用 manifest
- [x] 更新 LcaRunDriver.ts 的 WIRE mapping
- [x] Commit

---

## Phase 4: executionTarget 路由对齐 — 覆盖 G5

**目标：** 三层决策 + fallback，对齐 LobeHub 的 `resolveExecutionTarget()`。

### 对齐 LobeHub 的 executionTarget 决策

```python
# lca/infrastructure/plane/execution_target.py (新增)
from enum import Enum


class ExecutionTarget(str, Enum):
    SANDBOX = "sandbox"  # 云沙箱
    DEVICE = "device"  # 远程设备（通过 device-gateway）
    AUTO = "auto"  # 自动选择
    NONE = "none"  # 纯对话，无执行环境


class ExecutionPlan:
    target: ExecutionTarget
    device_id: str | None
    fallback: ExecutionTarget | None


def resolve_execution_target(
    requested: ExecutionTarget,
    device_online: bool,
    sandbox_available: bool,
    client_execution_available: bool,  # 有 device-gateway 连接
    device_id: str | None = None,
) -> ExecutionPlan:
    """对齐 LobeHub 的 resolveExecutionTarget()"""

    if requested == ExecutionTarget.NONE:
        return ExecutionPlan(target=ExecutionTarget.NONE)

    if requested == ExecutionTarget.SANDBOX:
        if sandbox_available:
            return ExecutionPlan(target=ExecutionTarget.SANDBOX)
        # sandbox 不可用 → fallback 到 device
        if device_online:
            return ExecutionPlan(target=ExecutionTarget.DEVICE, device_id=device_id)
        return ExecutionPlan(target=ExecutionTarget.NONE)  # 都没了

    if requested == ExecutionTarget.DEVICE:
        if device_online:
            return ExecutionPlan(target=ExecutionTarget.DEVICE, device_id=device_id)
        # device 不在线 → fallback 到 sandbox
        if sandbox_available:
            return ExecutionPlan(target=ExecutionTarget.SANDBOX, fallback=ExecutionTarget.SANDBOX)
        return ExecutionPlan(target=ExecutionTarget.NONE)

    if requested == ExecutionTarget.AUTO:
        # 优先 device（本地电脑），其次 sandbox
        if device_online:
            return ExecutionPlan(target=ExecutionTarget.DEVICE, device_id=device_id)
        if sandbox_available:
            return ExecutionPlan(target=ExecutionTarget.SANDBOX)
        return ExecutionPlan(target=ExecutionTarget.NONE)
```

### 更新 plane resolution

```python
# lca/infrastructure/plane/resolve.py (更新)
def resolve_plane_bindings(
    execution_target: ExecutionTarget,
    device_id: str | None = None,
) -> PlaneBindings:
    plan = resolve_execution_target(
        requested=execution_target,
        device_online=_check_device_online(device_id),
        sandbox_available=_check_sandbox_available(),
        client_execution_available=_check_gateway_client_available(),
        device_id=device_id,
    )
    
    if plan.target == ExecutionTarget.DEVICE:
        machine = resolve_machine(plan.device_id)
        return PlaneBindings(primary=machine)
    
    if plan.target == ExecutionTarget.SANDBOX:
        sandbox = resolve_sandbox()
        return PlaneBindings(primary=sandbox_ref_from(sandbox))
    
    return PlaneBindings(primary=None)  # 纯对话
```

- [x] 实现 execution_target.py
- [x] 更新 resolve.py 使用 executionTarget 决策
- [x] 更新 execute.py 传入 executionTarget
- [x] 更新 LcaRunDriver.ts 传递 executionTarget
- [x] 测试 fallback 逻辑
- [x] Commit

---

## Phase 5: 用户认证 + Workspace — 覆盖 G6

**目标：** JWT/serviceToken 认证 + workspace 级设备池。

### Task 5.1: Token 验证中间件

```python
# gateway/device_gateway/auth.py (新增)
from dataclasses import dataclass


@dataclass
class AuthenticatedUser:
    user_id: str
    workspace_id: str | None
    token_type: str  # 'jwt' | 'apiKey' | 'serviceToken'


def verify_token(token: str, token_type: str) -> AuthenticatedUser:
    """验证连接 token"""
    if token_type == "serviceToken":
        if token == settings.service_token:
            return AuthenticatedUser(
                user_id="local-dev-user",
                workspace_id=None,
                token_type="serviceToken",
            )
        raise AuthError("Invalid service token")

    if token_type == "jwt":
        payload = decode_jwt(token)
        return AuthenticatedUser(
            user_id=payload["sub"],
            workspace_id=payload.get("workspace_id"),
            token_type="jwt",
        )

    if token_type == "apiKey":
        # 查 API key 表
        user = lookup_api_key(token)
        if user:
            return user
        raise AuthError("Invalid API key")

    raise AuthError(f"Unknown token type: {token_type}")
```

### Task 5.2: Workspace 设备池

```python
# 设备可以属于个人或 workspace
# 个人设备：只有 owner 能看到
# workspace 设备：workspace 所有成员能看到

# DeviceRegistry 增加 workspace 过滤
def list_online(self, user_id: str, workspace_id: str | None = None) -> list[Device]:
    if workspace_id:
        # workspace 设备池：返回 workspace 级 + 个人的
        return [
            d for d in self._live.values() if d.workspace_id == workspace_id or d.user_id == user_id
        ]
    else:
        # 个人设备池
        return [d for d in self._live.values() if d.user_id == user_id]
```

- [x] 实现 token 验证
- [x] 设备注册关联 user_id / workspace_id
- [x] HTTP 路由传入认证信息
- [x] Commit

---

## Phase 6: 沙箱策略层 — 覆盖 G8

**目标：** SandboxPolicy 模型 + SRT 进程隔离 + Docker 云沙箱。对齐 LobeHub 的 `device-sandbox` 包。

### Task 6.1: SandboxPolicy 模型

```python
# lca/contracts/models/core/sandbox_policy.py (新增)
@dataclass(frozen=True)
class SandboxPolicy:
    """对齐 LobeHub 的 SandboxPolicy"""

    writable_roots: tuple[str, ...]  # 可写目录
    readable_roots: tuple[str, ...] | None  # 可读目录（None = 全部可读）
    denied_write_roots: tuple[str, ...] | None  # 禁写目录
    denied_read_roots: tuple[str, ...] | None  # 禁读目录
    allow_network: bool  # 是否允许网络
    allowed_network_domains: tuple[str, ...] | None  # 网络域名白名单
    env_allowlist: tuple[str, ...] | None  # 环境变量白名单
    on_unavailable: str = "warn-allow"  # 沙箱不可用时的行为


# 默认策略
DEFAULT_POLICY = SandboxPolicy(
    writable_roots=("/home/sandbox-user",),
    readable_roots=None,
    denied_write_roots=("/home/sandbox-user/.ssh", "/home/sandbox-user/.lca"),
    allow_network=True,
    allowed_network_domains=None,  # 全部允许
)
```

### Task 6.2: lca connect 中的沙箱隔离

在 `lca connect` CLI 中，工具执行前应用 SandboxPolicy：

```typescript
// packages/lca-cli/src/tools/executor.ts
import { createSandboxLaunchPlan, type SandboxPolicy } from '@lobechat/device-sandbox';

const POLICY: SandboxPolicy = {
  writableRoots: ['/home/sandbox-user'],
  deniedWriteRoots: ['/home/sandbox-user/.ssh', '/home/sandbox-user/.lca'],
  allowNetwork: true,
  onUnavailable: 'warn-allow',
};

async function executeWithSandbox(command: string, cwd: string): Promise<ToolResult> {
  const plan = await createSandboxLaunchPlan({
    command: { cmd: '/bin/sh', args: ['-c', command] },
    cwd,
    policy: POLICY,
  });
  
  // plan.sandboxed === true → SRT 隔离执行
  // plan.sandboxed === false → 直接执行（带 warning）
  const child = spawn(plan.cmd, plan.args, {
    cwd,
    env: plan.env,
  });
  
  // ... collect output
  
  plan.release?.();
}
```

### Task 6.3: 云沙箱策略

```python
# lca/infrastructure/sandbox/policy.py (新增)
# Onlyboxes/Docker 沙箱也应用同样的 SandboxPolicy


def apply_sandbox_policy(sandbox: Sandbox, policy: SandboxPolicy) -> None:
    """配置沙箱的文件系统和网络策略"""
    # Docker: --volume, --network, --env
    # Onlyboxes: API 参数
```

- [x] 实现 SandboxPolicy 模型
- [x] lca connect 集成 SRT 沙箱
- [x] 云沙箱应用同样的策略
- [x] Commit

---

## Phase 7: 清理

### Task 7.1: 删除旧代码

```bash
# 删除 Python sidecar
rm -rf host/

# 删除 presence 模块
rm -rf gateway/presence/

# 删除旧的 host_sandbox
rm gateway/host_sandbox.py

# 删除旧的 plane_bind
rm gateway/plane_bind.py

# 删除旧测试
rm tests/test_presence_*.py
rm tests/test_host_sandbox.py

# 删除旧的 computer tool 结构
rm lca/infrastructure/tools/computer/specs.py
rm lca/infrastructure/tools/computer/handlers.py
rm lca/infrastructure/tools/computer/descriptions.py
```

### Task 7.2: 更新 start script

```bash
# scripts/start_lobehub_stack.sh
# 替换 start_host() → start_lca_cli()
start_lca_cli() {
  lca connect --daemon --gateway "ws://127.0.0.1:${GATEWAY_PORT}"
}
```

### Task 7.3: 全量验证

```bash
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest -q
uv run vulture lca --min-confidence 80
```

---

## 最终架构

```
┌──────────────────┐       ┌──────────────────────┐       ┌──────────────────┐
│  LobeHub UI      │       │  LCA Gateway          │       │  lca connect     │
│  (最小 patch)    │──HTTP─▶│                       │◀─WS───│  (npm CLI)       │
│                  │       │  /api/device/*        │       │                  │
│  executionTarget │       │  /runs/*              │       │  GatewayClient   │
│  sandbox|device  │       │  /files/*             │       │  ├ heartbeat 30s │
│  |auto|none      │       │                       │       │  ├ exp backoff   │
│                  │       │  DeviceRegistry (SQLite)│      │  ├ token refresh │
│  LcaRunDriver    │       │  GatewayHttpClient    │       │  └ workspace     │
│  Journal→UI      │       │  executionTarget      │       │    /home/sandbox- │
│                  │       │  SandboxPolicy        │       │    user           │
│                  │       │                       │       │                  │
│                  │       │  Tools:               │       │  Tool execution: │
│                  │       │  lca_computer/        │       │  ├ SRT sandbox   │
│                  │       │  lca_sandbox/         │       │  ├ file ops      │
│                  │       │  web_search/          │       │  ├ shell ops     │
│                  │       │                       │       │  └ code exec     │
└──────────────────┘       └──────────────────────┘       └──────────────────┘
```

---

## 删除代码量估算

| 删除 | 行数 | 替代 |
|---|---|---|
| `host/` | ~1200 行 | `lca connect` (npm) |
| `gateway/presence/` | ~600 行 | `gateway/device_gateway/` |
| `gateway/host_sandbox.py` | ~180 行 | `GatewayHttpClient` |
| `gateway/plane_bind.py` | ~70 行 | `execution_target.py` |
| `lca/infrastructure/tools/computer/specs.py` | ~400 行 | `lca_computer/apis/*.py` |
| `lca/infrastructure/tools/computer/handlers.py` | ~300 行 | `lca_computer/executor.py` |
| 旧测试 | ~400 行 | 新测试 |
| **总计** | **~3150 行** | 干净的新架构 |

---

Plan saved to `docs/plans/2026-08-14-execution-alignment.md`. Ready to execute?
