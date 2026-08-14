# ExecutionContext — 执行上下文统一架构

**日期**: 2026-08-14  
**状态**: Draft  
**动机**: 消除 `/mnt/data` 虚拟路径映射层，让 agent、前端、工具、附件共享真实文件系统路径；统一 4 种执行环境（Host / Onlyboxes / SSH / Windows）为同一抽象。

---

## 1. 第一性原理

**一个 AI agent 需要在某个计算环境上执行操作。** 这个环境有自己的文件系统、自己的路径、自己的身份。Agent 操作的就是那台机器上的**真实路径**。

**业界范式**：

| 系统 | 路径语义 |
|---|---|
| Docker | exec 进去，看到容器真实文件系统 |
| SSH | 连到远程，操作远程真实路径 |
| LobeHub CLI | local-file-shell 操作本机真实路径 |
| LobeHub Cloud Sandbox | Docker 容器，agent 操作容器内真实路径 |
| GitHub Codespaces | agent 操作 codespace 真实文件系统 |

**共同点**: 每个执行上下文有且只有一个文件系统，agent 看到的就是真实路径。不存在翻译层。

---

## 2. 现有问题

### 2.1 虚拟路径映射（核心问题）

当前为本机 host 维护了一层假的 `/mnt/data` 命名空间：

- Agent 被告知其工作区是 `/mnt/data`
- 物理目录实际是 `/home/sandbox-user`
- `host/paths.py` 的 `rewrite_guest_refs` 负责把 `/mnt/data` 翻译成真实路径
- `list_files` 回写真实路径（`str(child)`），导致路径泄漏

结果：agent 以为自己在 `/mnt/data`，工具结果报 `/home/sandbox-user`，前端混着两种地址。

### 2.2 执行面与身份分离

- `ExecutionSurface` 只有 `backend` + `guest_root`
- 没有 `device_id`、`label`、`hostname`
- Agent 不知道自己在哪台机器上
- 前端不知道当前连的是哪个 host

### 2.3 垃圾节点清单

| 节点 | 问题 |
|---|---|
| `rewrite_guest_refs()` | 虚拟路径 → 真实路径翻译，不应存在 |
| `resolve_guest_path()` | 同上 |
| `guest_root()` / `guest_mount()` | 虚构的 guest 路径概念 |
| `ExecutionSurface.guest_root` | 应该是 `workspace`，直接是真实路径 |
| `COMPUTER_WORKSPACE_ROOT = "/mnt/data"` | 硬编码常量，应来自 context |
| `SANDBOX_MOUNT_ROOT = "/mnt/data"` | 同上（Onlyboxes 保留为默认值） |
| `host/paths.py` | 大量路径翻译逻辑，应简化为 "resolve relative to workspace" |
| Prompt 中的 "Cloud Sandbox" | host 模式不应出现 |
| Skill 中的 `/mnt/data` | 应参数化 |

---

## 3. 架构设计

### 3.1 分层

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (layer1_cognitive, layer2_runtime, layer3)     │
│  - Tools: list_files, read_file, run_command, ...           │
│  - Prompt: context 注入（label, workspace, backend）         │
│  - Skills: 参数化路径（不硬编码）                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  ExecutionContext (contracts/protocols)                      │
│  - id: str          # 唯一标识                               │
│  - label: str       # 显示名                                 │
│  - backend: str     # "host" | "onlyboxes" | "ssh" | "windows"│
│  - workspace: str   # THE real root（那台机器上的真实路径）    │
│  - outputs_dir: str # workspace/outputs                      │
│  - execute(op, payload) -> ExecResult                        │
│  - prompt_context() -> str   # 注入 prompt 的结构化信息       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────┬───────┴───────┬──────────────┐
        ▼           ▼               ▼              ▼
┌──────────┐ ┌──────────┐ ┌───────────────┐ ┌──────────┐
│ Host     │ │ Onlyboxes│ │ SSH           │ │ Windows  │
│ Context  │ │ Context  │ │ Context       │ │ Context  │
│          │ │          │ │               │ │          │
│ ws:/8765 │ │ Docker/  │ │ ssh user@host │ │ powershell│
│ RPC      │ │ API      │ │ + key/password│ │ .exe     │
│          │ │          │ │               │ │          │
│ /home/   │ │ /mnt/data│ │ /home/        │ │ C:\Users\│
│ sandbox- │ │ (容器内  │ │ smartljy      │ │ lichao\  │
│ user     │ │  真实)   │ │               │ │ workspace│
└──────────┘ └──────────┘ └───────────────┘ └──────────┘
```

### 3.2 核心 Protocol

```python
# lca/contracts/protocols/execution.py

from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class ExecutionContext(Protocol):
    """一个 agent 可以操作的计算环境。
    
    身份 + 文件系统 + 执行能力。Agent、前端、工具、附件共享同一个 workspace。
    不存在虚拟路径映射。workspace 是那台机器上的真实路径。
    """

    @property
    def id(self) -> str:
        """唯一标识 — device_id, session_id, ssh host alias, etc."""
        ...

    @property
    def label(self) -> str:
        """人类可读名 — hostname, session label, SSH alias, etc."""
        ...

    @property
    def backend(self) -> str:
        """实现方式标识（纯元数据，不影响执行语义）。
        "host" | "onlyboxes" | "ssh" | "windows"
        """
        ...

    @property
    def workspace(self) -> str:
        """真实文件系统根。Agent/前端/工具/附件全用这个。
        
        - Host: /home/sandbox-user (或 LCA_HOST_ROOT)
        - Onlyboxes: /mnt/data (容器内真实路径)
        - SSH: 远程 home 或配置路径
        - Windows: C:\\Users\\lichao\\workspace
        """
        ...

    @property
    def outputs_dir(self) -> str:
        """交付物目录 = workspace/outputs。"""
        ...

    async def execute(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行操作。传输细节由实现处理。
        
        op: 操作名（list_files, read_file, run_command, run, write_files, ...）
        payload: 操作参数
        
        返回: {"success": bool, ...} 结构化结果
        """
        ...

    def prompt_context(self) -> str:
        """生成注入 system prompt 的执行环境描述。"""
        ...
```

### 3.3 与现有 Sandbox Protocol 的关系

**Sandbox Protocol 不变。** 它是执行传输层（how to run code）。  
**ExecutionContext 是上层抽象（who + where + how）。**

关系：
- `ExecutionContext.execute()` 内部委托给 `Sandbox`（或自己实现传输）
- Host: `HostContext` 内部用 WebSocket RPC（现有 `HostSandbox`）
- Onlyboxes: `OnlyboxesContext` 内部用 Docker exec（现有 `OnlyboxesSandboxAdapter`）
- SSH: `SSHContext` 内部用 `ssh` subprocess
- Windows: `WindowsContext` 内部用 `powershell.exe` / `subprocess`

```python
class HostContext:
    def __init__(self, sandbox: HostSandbox, settings: HostRuntimeSettings):
        self._sandbox = sandbox
        self._settings = settings
    
    @property
    def id(self) -> str:
        return self._settings.device_id
    
    @property
    def label(self) -> str:
        return self._settings.display_name()
    
    @property
    def backend(self) -> str:
        return "host"
    
    @property
    def workspace(self) -> str:
        return str(self._settings.workspace())
    
    @property
    def outputs_dir(self) -> str:
        return str(self._settings.outputs_dir())
    
    async def execute(self, op: str, payload: dict) -> dict:
        return await self._sandbox.computer_op(op, payload)
    
    def prompt_context(self) -> str:
        return (
            f"你正在 **{self.label}** 上操作（本机 host）。\n"
            f"工作区：`{self.workspace}`\n"
            f"交付物写到 `{self.outputs_dir}`\n"
        )
```

### 3.4 四种实现

#### HostContext

```python
# lca/layer0_infra/execution/host_context.py

class HostContext:
    """本机 host sidecar — WebSocket RPC 到 host 进程。"""
    
    id: str           # device_id from settings
    label: str        # hostname from settings
    backend = "host"
    workspace: str    # LCA_HOST_ROOT → /home/{user}
    outputs_dir: str  # workspace/outputs
    
    # execute → HostSandbox.computer_op() (现有 WebSocket RPC)
    # 不需要 rewrite_guest_refs — agent 直接操作真实路径
```

#### OnlyboxesContext

```python
# lca/layer0_infra/execution/onlyboxes_context.py

class OnlyboxesContext:
    """Onlyboxes 容器沙箱 — Docker exec / API。"""
    
    id: str           # session_id or box_id
    label: str        # "Onlyboxes Sandbox" or configurable
    backend = "onlyboxes"
    workspace = "/mnt/data"  # 容器内真实路径
    outputs_dir = "/mnt/data/outputs"
    
    # execute → OnlyboxesSandboxAdapter (现有)
```

#### SSHContext

```python
# lca/layer0_infra/execution/ssh_context.py

class SSHContext:
    """远程 SSH — ssh user@host。"""
    
    id: str           # ssh alias (e.g. "smartljy")
    label: str        # display name
    backend = "ssh"
    workspace: str    # 远程真实路径（配置或 ssh 后探测）
    outputs_dir: str  # workspace/outputs
    
    # execute → subprocess: ssh smartljy "command"
    # file ops → sftp / scp / ssh cat
    
    host: str
    user: str
    port: int = 22
    key_path: str = ""  # SSH key
```

#### WindowsContext

```python
# lca/layer0_infra/execution/windows_context.py

class WindowsContext:
    """本机 Windows PowerShell。"""
    
    id: str           # device identifier
    label: str        # display name
    backend = "windows"
    workspace: str    # C:\Users\lichao\workspace
    outputs_dir: str  # workspace\outputs
    
    # execute → subprocess: powershell.exe -Command "..."
    # file ops → 直接本地文件系统操作
    
    # 注意：路径用 Windows 格式，agent 看到的就是 C:\...
```

### 3.5 Factory

```python
# lca/layer0_infra/execution/factory.py

class ExecutionContextFactory:
    """根据配置和运行时状态创建 ExecutionContext。"""
    
    def resolve(self) -> ExecutionContext:
        """优先级：
        1. 在线 host sidecar（Presence 有 sandbox capability）→ HostContext
        2. SSH 配置存在 → SSHContext
        3. Onlyboxes 配置存在 → OnlyboxesContext
        4. Windows 本地 → WindowsContext
        5. None（无执行环境）
        """
        ...
```

### 3.6 配置

每种环境独立配置节，由 pydantic-settings 加载：

```bash
# .env — 通用
LCA_EXECUTION_BACKEND=auto  # auto | host | onlyboxes | ssh | windows

# Host
LCA_HOST_USER=sandbox-user
LCA_HOST_ROOT=              # 空 → /home/${LCA_HOST_USER}
LCA_HOST_DEVICE_ID=local-host
LCA_HOST_TOKEN=lca-local-host

# SSH
LCA_SSH_HOST=smartljy
LCA_SSH_USER=smartljy
LCA_SSH_PORT=22
LCA_SSH_KEY=~/.ssh/id_rsa
LCA_SSH_WORKSPACE=          # 空 → 远程 $HOME

# Windows
LCA_WINDOWS_WORKSPACE=C:\Users\lichao\workspace

# Onlyboxes
ONLYBOXES_BASE_URL=http://127.0.0.1:8089
ONLYBOXES_ACCESS_TOKEN=obx_...
```

### 3.7 Agent 感知

Prompt 模板不再硬编码路径，而是由 `context.prompt_context()` 注入：

```markdown
<execution_context>
{context.prompt_context()}
</execution_context>

<uploaded_files>
附件已挂载到 `{context.workspace}/<filename>`。
</uploaded_files>

<output_policy>
交付物写到 `{context.outputs_dir}`。
</output_policy>
```

Host 示例输出：
```
你正在 **lichao-mbp** 上操作（本机 host）。
工作区：`/home/sandbox-user`
交付物写到 `/home/sandbox-user/outputs`
```

Onlyboxes 示例输出：
```
你正在 **Onlyboxes Sandbox** 上操作（云端容器）。
工作区：`/mnt/data`
交付物写到 `/mnt/data/outputs`
```

SSH 示例输出：
```
你正在 **smartljy** 上操作（远程 SSH）。
工作区：`/home/smartljy`
交付物写到 `/home/smartljy/outputs`
```

Windows 示例输出：
```
你正在 **lichao-pc** 上操作（本机 Windows）。
工作区：`C:\Users\lichao\workspace`
交付物写到 `C:\Users\lichao\workspace\outputs`
```

### 3.8 Skills 参数化

Skill 不再硬编码 `/mnt/data`，改用占位符 `{workspace}` 和 `{outputs_dir}`：

```markdown
# officecli SKILL.md

| 工作区 | 附件在 `{workspace}/<文件名>`；交付物写 **`{outputs_dir}/`** |

officecli create {outputs_dir}/report.pptx --json
```

Skill 激活时，根据当前 `ExecutionContext` 替换占位符。

### 3.9 Tools

工具接收 `ExecutionContext`，不再接收 `Sandbox` + mount 参数：

```python
class ListFilesTool(Tool):
    def __init__(self, context: ExecutionContext):
        self._context = context
    
    async def execute(self, args):
        result = await self._context.execute("list_files", args)
        # result 中的路径已经是真实路径（context.workspace 下的）
        return Observation(...)
```

工具不需要知道 backend、不需要做路径翻译。`execute()` 返回的就是真实路径。

### 3.10 前端

前端从 gateway 获取 context 信息：

```json
{
  "context_id": "local-host",
  "context_label": "lichao-mbp",
  "context_backend": "host",
  "context_workspace": "/home/sandbox-user"
}
```

- 状态栏显示："Running on: lichao-mbp (host)"
- 下载卡：`/home/sandbox-user/outputs/report.pdf` → gateway 转 download URL
- 附件路径：和 agent 看到的一致

---

## 4. 删除清单

| 模块 | 动作 |
|---|---|
| `host/paths.py::rewrite_guest_refs` | **删除** |
| `host/paths.py::resolve_guest_path` | **简化**为 "resolve relative to workspace" |
| `host/local_shell/paths.py` | **简化**，去掉 `mount` 参数 |
| `host/local_shell/dispatch.py` | 去掉 `mount` 参数 |
| `host/local_shell/file/*.py` | 所有 handler 去掉 `mount` 参数 |
| `host/local_shell/shell/runner.py` | 去掉 `mount` 参数 |
| `host/exec.py` | 去掉 `mount` 参数 |
| `lca/layer0_infra/sandbox/surface.py` | **替换**为 ExecutionContext |
| `lca/layer0_infra/sandbox/host_settings.py` | 合并进 ExecutionContext config |
| `lca/layer0_infra/computer/constants.py::COMPUTER_WORKSPACE_ROOT` | **删除**硬编码，从 context 取 |
| `lca/layer0_infra/sandbox/bootstrap.py` | 从 context.workspace 构建路径 |
| `lca/layer0_infra/sandbox/runtime_mount.py` | 从 context.workspace 构建路径 |
| `lca/layer0_infra/sandbox/output_collect.py` | 从 context.outputs_dir 构建路径 |
| `lca/layer0_infra/sandbox/inspect_prelude.py` | 从 context.workspace 构建路径 |
| `lca/layer0_infra/sandbox/error_parse.py` | 从 context.workspace 构建路径 |
| `lca/layer0_infra/sandbox/prompt.py` | 用 context.prompt_context() 替换硬编码 |
| `lca/layer0_infra/computer/runtime.py::_normalize_path` | 从 context.workspace 解析 |
| `lca/layer0_infra/computer/guest/preamble.py::ROOT` | 从 context.workspace 注入 |
| `skills/officecli/SKILL.md` | `/mnt/data` → `{workspace}` / `{outputs_dir}` |
| `lca/contracts/models/core/sandbox.py::SANDBOX_MOUNT_ROOT` | 保留作为 Onlyboxes 默认值，不再作为全局常量 |

---

## 5. 保留清单

| 模块 | 理由 |
|---|---|
| `lca/contracts/protocols/infra.py::Sandbox` | 执行传输层 Protocol，不变 |
| `host/local_shell/file/*.py` | 本机文件操作实现，简化后保留 |
| `host/local_shell/shell/*.py` | 本机 shell 操作实现，简化后保留 |
| `host/local_shell/dispatch.py` | 操作路由表，简化后保留 |
| `gateway/host_sandbox.py` | Host → Sandbox 适配层 |
| `gateway/presence/` | Presence 注册/路由 |
| `lca/layer0_infra/sandbox/onlyboxes_adapter.py` | Onlyboxes 实现 |
| `lca/layer0_infra/sandbox/factory.py` | 改为解析 ExecutionContext |

---

## 6. 新增清单

| 模块 | 说明 |
|---|---|
| `lca/contracts/protocols/execution.py` | `ExecutionContext` Protocol |
| `lca/layer0_infra/execution/__init__.py` | 包入口 |
| `lca/layer0_infra/execution/host_context.py` | Host 实现 |
| `lca/layer0_infra/execution/onlyboxes_context.py` | Onlyboxes 实现 |
| `lca/layer0_infra/execution/ssh_context.py` | SSH 实现 |
| `lca/layer0_infra/execution/windows_context.py` | Windows 实现 |
| `lca/layer0_infra/execution/factory.py` | Context factory |
| `lca/layer0_infra/execution/config.py` | 配置加载 |

---

## 7. 迁移策略

**渐进式**，分 3 步：

1. **Phase 1: 建 Protocol + Host/Onlyboxes 实现**
   - 新增 `ExecutionContext` Protocol
   - 实现 `HostContext`、`OnlyboxesContext`
   - 新增 `ExecutionContextFactory`
   - Prompt 切换到 `context.prompt_context()`
   - 工具切换到接收 `ExecutionContext`
   - **不改 host sidecar 和 Onlyboxes adapter 内部**

2. **Phase 2: 去 remap 层**
   - 删除 `rewrite_guest_refs`、`resolve_guest_path`
   - 简化 `host/paths.py`、`local_shell/paths.py`
   - 所有 handler 去掉 `mount` 参数
   - Skill 参数化

3. **Phase 3: 加 SSH / Windows**
   - 实现 `SSHContext`
   - 实现 `WindowsContext`
   - 端到端验证 4 种环境

---

## 8. 验证标准

- [ ] Host 环境：agent 操作 `/home/sandbox-user/...`，前端显示真实路径
- [ ] Onlyboxes 环境：agent 操作 `/mnt/data/...`（容器内真实路径）
- [ ] SSH 环境：agent 操作远程真实路径，文件通过 sftp 传输
- [ ] Windows 环境：agent 操作 `C:\...`，PowerShell 执行
- [ ] 不存在任何 `/mnt/data` 硬编码（除 Onlyboxes 内部）
- [ ] 不存在 `rewrite_guest_refs` 或等价翻译层
- [ ] Skill 不含硬编码路径
- [ ] 前端能显示当前 context 的 id/label/backend
- [ ] Journal 记录 context.id

---

## 9. 设计原则

1. **真实路径**: agent 操作的就是那台机器上的真实文件系统路径
2. **单一命名空间**: 不存在 guest/host 双路径，workspace 就是 THE path
3. **身份一等公民**: context.id + label 流入 prompt、前端、Journal
4. **传输无关**: Protocol 只承诺 execute(op, payload)，不关心传输细节
5. **开闭原则**: 新增 backend 只需实现 ExecutionContext Protocol
6. **无补丁**: 不在垃圾机制上做修补，直击本质
