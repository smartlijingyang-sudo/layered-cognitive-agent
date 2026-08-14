# ExecutionContext — 执行上下文统一架构

**日期**: 2026-08-14  
**状态**: Draft v3 (reviewer approved)  
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
│  - backend: BackendKind  # 类型安全的枚举                    │
│  - workspace: str   # THE real root                         │
│  - outputs_dir: str # workspace/outputs                      │
│  - execute(op, payload) -> OpResult                          │
│  - prompt_context() -> str                                   │
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

### 3.2 核心类型与 Protocol

```python
# lca/contracts/protocols/execution.py

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class BackendKind(str, Enum):
    HOST = "host"
    ONLYBOXES = "onlyboxes"
    SSH = "ssh"
    WINDOWS = "windows"


# ── 标准化操作结果 ──

@dataclass(frozen=True)
class OpResult:
    """所有 execute() 返回的统一结构。
    
    工具层只看 success + content + error。
    特定 op 的额外数据放在 data 里（类型安全的子类型见下方）。
    """
    success: bool
    content: str = ""         # 人类可读的结果文本
    error: str = ""
    data: dict[str, Any] = {}  # op-specific 结构化数据


# 各 op 的 data 契约（文档级约束，不强制类型）：
#
# list_files:
#   data.files: list[{name, path, size, is_directory, type, modified_time}]
#   data.total_count: int
#
# read_file:
#   data.content: str
#   data.filename: str
#   data.line_count: int
#   data.truncated: bool
#
# write_file:
#   data.path: str  (written path)
#
# run_command:
#   data.stdout: str
#   data.stderr: str
#   data.exit_code: int
#   data.shell_id: str  (for background)
#   data.duration_ms: int
#
# run (code execution):
#   data.stdout: str
#   data.stderr: str
#   data.exit_code: int
#   data.generated_files: list[{name, mime_type, size}]


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
    def backend(self) -> BackendKind:
        """类型安全的 backend 枚举。"""
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

    async def execute(self, op: str, payload: dict[str, Any]) -> OpResult:
        """执行操作。传输细节由实现处理。
        
        op: 操作名（list_files, read_file, write_file, edit_file, 
             run_command, run, move_files, rename_file, search_files,
             grep_content, glob_files）
        payload: 操作参数（各 op 的 schema 见 OpResult.data 契约）
        
        返回: OpResult（统一的 success/content/error/data 结构）
        """
        ...

    def prompt_context(self) -> str:
        """生成注入 system prompt 的执行环境描述。"""
        ...
```

### 3.3 与现有 Sandbox Protocol 的关系 — 迁移路径

**Sandbox Protocol 不变。** 它是底层执行传输（how to run code）。

**ExecutionContext 是上层抽象（who + where + how）。** 它包装 Sandbox 实例，加上身份和路径语义。

**迁移路径**（解决 reviewer 指出的 coexistence 问题）：

```
Phase 1 期间:
  - ExecutionContext 内部持有 Sandbox 引用
  - 新工具接收 ExecutionContext
  - 旧工具仍接收 Sandbox（通过 ComputerRuntime 适配）
  - ComputerRuntime 内部查询 ExecutionContext 获取 workspace 路径
  - 两套注入并存，旧工具逐步迁移

Phase 2 完成后:
  - 所有工具迁移到 ExecutionContext
  - Sandbox Protocol 仅作为 ExecutionContext 内部传输
  - 不再有 Sandbox 类型的外部注入
```

具体 wiring：

```python
class HostContext:
    """Host 实现 — 内部持有 HostSandbox（WebSocket RPC）。"""
    
    def __init__(self, sandbox: HostSandbox, settings: HostRuntimeSettings):
        self._sandbox = sandbox   # 内部传输，不暴露给工具
        self._settings = settings
    
    async def execute(self, op: str, payload: dict) -> OpResult:
        # 委托给 HostSandbox.computer_op()
        raw = await self._sandbox.computer_op(op, payload)
        return _to_op_result(raw)
    
    # 工具层只看到 ExecutionContext，不看到 Sandbox
```

### 3.4 四种实现

#### HostContext

```python
# lca/layer0_infra/execution/host_context.py

class HostContext:
    """本机 host sidecar — WebSocket RPC 到 host 进程。"""
    
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
    def backend(self) -> BackendKind:
        return BackendKind.HOST
    
    @property
    def workspace(self) -> str:
        return str(self._settings.workspace())
    
    @property
    def outputs_dir(self) -> str:
        return str(self._settings.outputs_dir())
    
    async def execute(self, op: str, payload: dict) -> OpResult:
        raw = await self._sandbox.computer_op(op, payload)
        return _to_op_result(raw)
    
    def prompt_context(self) -> str:
        return (
            f"你正在 **{self.label}** 上操作（本机 host，backend={self.backend.value}）。\n"
            f"工作区：`{self.workspace}`\n"
            f"交付物写到 `{self.outputs_dir}`\n"
            f"附件在 `{self.workspace}/<文件名>`\n"
        )
```

#### OnlyboxesContext

```python
# lca/layer0_infra/execution/onlyboxes_context.py

class OnlyboxesContext:
    """Onlyboxes 容器沙箱 — Docker exec / API。"""
    
    def __init__(self, sandbox: OnlyboxesSandboxAdapter, *, 
                 session_id: str = "", label: str = "Onlyboxes Sandbox"):
        self._sandbox = sandbox
        self._session_id = session_id
        self._label = label
    
    @property
    def id(self) -> str:
        return self._session_id or "onlyboxes"
    
    @property
    def label(self) -> str:
        return self._label
    
    @property
    def backend(self) -> BackendKind:
        return BackendKind.ONLYBOXES
    
    @property
    def workspace(self) -> str:
        return "/mnt/data"  # 容器内真实路径
    
    @property
    def outputs_dir(self) -> str:
        return "/mnt/data/outputs"
    
    async def execute(self, op: str, payload: dict) -> OpResult:
        # Onlyboxes 通过 Sandbox Protocol 执行
        # file ops → guest Python scripts
        # run → sandbox.run()
        ...
    
    def prompt_context(self) -> str:
        return (
            f"你正在 **{self.label}** 上操作（云端容器，backend={self.backend.value}）。\n"
            f"工作区：`{self.workspace}`\n"
            f"交付物写到 `{self.outputs_dir}`\n"
            f"这是一个隔离环境，非用户本机文件系统。\n"
        )
```

#### SSHContext

```python
# lca/layer0_infra/execution/ssh_context.py

import asyncio
import subprocess
from pathlib import PurePosixPath


class SSHContext:
    """远程 SSH — ssh user@host。
    
    连接策略：每次 execute 独立 ssh 调用（简单、无状态、可并发）。
    对于高频场景可后续加连接池，但 MVP 不需要。
    
    文件传输：小文件走 ssh cat / ssh tee（避免 sftp 依赖）。
    大文件（>1MB）走 scp。
    """
    
    def __init__(self, config: SSHConfig):
        self._config = config
    
    @property
    def id(self) -> str:
        return f"ssh-{self._config.alias}"
    
    @property
    def label(self) -> str:
        return self._config.alias
    
    @property
    def backend(self) -> BackendKind:
        return BackendKind.SSH
    
    @property
    def workspace(self) -> str:
        return self._config.workspace  # 配置或探测得到
    
    @property
    def outputs_dir(self) -> str:
        return f"{self.workspace}/outputs"
    
    def _ssh_argv(self) -> list[str]:
        """构建 ssh 命令前缀。"""
        argv = ["ssh", "-o", "StrictHostKeyChecking=accept-new"]
        if self._config.key_path:
            argv.extend(["-i", self._config.key_path])
        if self._config.port != 22:
            argv.extend(["-p", str(self._config.port)])
        argv.append(f"{self._config.user}@{self._config.host}")
        return argv
    
    async def execute(self, op: str, payload: dict) -> OpResult:
        """SSH execute 映射：
        
        run_command:
          ssh host "cd workspace && command"
          → 捕获 stdout/stderr/exit_code
        
        list_files:
          ssh host "ls -la path" → parse
          或 ssh host "find path -maxdepth 1 -printf ..." → structured
        
        read_file:
          ssh host "cat path"
        
        write_file:
          echo content | ssh host "cat > path"
          或 scp tempfile host:path（大文件）
        
        run (code):
          ssh host "cd workspace && python3 -c 'code'"
        """
        if op == "run_command":
            return await self._run_command(payload)
        elif op == "read_file":
            return await self._read_file(payload)
        elif op == "write_file":
            return await self._write_file(payload)
        elif op == "list_files":
            return await self._list_files(payload)
        elif op == "run":
            return await self._run_code(payload)
        else:
            return OpResult(success=False, error=f"unsupported op for SSH: {op}")
    
    async def _run_command(self, payload: dict) -> OpResult:
        command = payload.get("command", "")
        cwd = payload.get("cwd", self.workspace)
        full_cmd = f"cd {_shell_quote(cwd)} && {command}"
        
        proc = await asyncio.create_subprocess_exec(
            *self._ssh_argv(), full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), 
            timeout=payload.get("timeout_s", 60)
        )
        
        return OpResult(
            success=proc.returncode == 0,
            content=stdout.decode("utf-8", errors="replace"),
            error=stderr.decode("utf-8", errors="replace") if proc.returncode != 0 else "",
            data={
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode or 0,
            }
        )
    
    async def _read_file(self, payload: dict) -> OpResult:
        path = payload.get("path", "")
        abs_path = self._resolve_path(path)
        
        proc = await asyncio.create_subprocess_exec(
            *self._ssh_argv(), f"cat {_shell_quote(abs_path)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return OpResult(
                success=False,
                error=stderr.decode("utf-8", errors="replace"),
            )
        
        content = stdout.decode("utf-8", errors="replace")
        lines = content.splitlines()
        return OpResult(
            success=True,
            content=content,
            data={
                "content": content,
                "filename": PurePosixPath(abs_path).name,
                "line_count": len(lines),
                "truncated": False,
            }
        )
    
    def _resolve_path(self, path: str) -> str:
        """解析相对路径到 workspace 下。"""
        p = PurePosixPath(path)
        if p.is_absolute():
            return str(p)
        return str(PurePosixPath(self.workspace) / path)
    
    def prompt_context(self) -> str:
        return (
            f"你正在 **{self.label}** 上操作（远程 SSH，backend={self.backend.value}）。\n"
            f"工作区：`{self.workspace}`\n"
            f"交付物写到 `{self.outputs_dir}`\n"
            f"这是远程机器的真实文件系统。\n"
        )


class SSHConfig:
    """SSH 连接配置。"""
    alias: str          # 显示名 / 标识
    host: str
    user: str
    port: int = 22
    key_path: str = ""  # SSH 私钥路径
    workspace: str = "" # 空则连接后探测 $HOME
    
    def __init__(self, alias: str, host: str, user: str, 
                 port: int = 22, key_path: str = "", workspace: str = ""):
        self.alias = alias
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path
        self.workspace = workspace


def _shell_quote(s: str) -> str:
    """Shell 转义。"""
    return "'" + s.replace("'", "'\"'\"'") + "'"
```

#### WindowsContext — 对齐 LobeHub 原生架构

**关键洞察**：LobeHub 的 `@lobehub/cli` 是一个 Node.js sidecar，跑在用户机器上，通过 `@lobechat/local-file-shell` 包处理跨平台差异。我们的 `host/` sidecar 是它的 **Python 对等物**。

**架构对齐**：

| LobeHub | LCA |
|---|---|
| `@lobehub/cli` (Node.js sidecar) | `host/` (Python sidecar) |
| `@lobechat/local-file-shell` | `host/local_shell/` |
| `os.platform()` 分发 | `sys.platform` 分发 |
| `detectWindowsShell()` | 待实现 |
| `normalizeEnvVarRefs()` | 待实现 |
| `windowsHide: true` | 待实现 |
| Device registration (`platform` field) | Presence hello (`capabilities` + 待加 `platform`) |

**模式 B 完整流程**（Gateway Linux → Windows 远程）：

```
Gateway (Linux)                         Windows Machine
┌─────────────────┐                     ┌──────────────────────────┐
│ PresenceRegistry│◄── WebSocket ──────│ python -m host           │
│                 │                     │   host/client.py         │
│ HostSandbox     │── RPC (WS) ───────►│   host/exec.py           │
│                 │                     │   host/local_shell/      │
│ HostContext     │                     │     (跨平台 Python)      │
└─────────────────┘                     └──────────────────────────┘
```

**不需要 npm 进程**。现有 Python sidecar 就是 LobeHub CLI 的对等物。

**Windows 适配清单**（在 `host/` sidecar 内部）：

1. **`host/pty.py`**：`pty` 模块不存在于 Windows → 用 `subprocess` + `conpty`（Windows 10+）或降级为非交互模式
2. **Shell 检测**：Windows 上可能是 PowerShell、cmd.exe、Git Bash → 实现 `detect_windows_shell()`
3. **环境变量引用**：`$VAR` 在 cmd.exe 不工作 → 实现 `normalize_env_var_refs()` for `%VAR%` / `$env:VAR`
4. **进程创建**：`windows_hide=True` 防止控制台窗口闪烁
5. **路径格式**：`pathlib.Path` 在 Windows 上自动用 `\` → 大部分代码无需改动

**HostContext 就是 Windows 远程访问的 Context**：
- 远程 Windows 机器跑 `python -m host`
- Gateway 通过 Presence 发现它，创建 `HostContext`
- **不需要单独的 `WindowsContext`**
- `HostContext` 不知道远程机器是 Linux 还是 Windows — 它只是 RPC

**WindowsContext 仅用于 gateway 本机是 Windows 的场景**（模式 A，极少用）。

**Presence 注册增加 platform 字段**：

```python
# host/client.py HELLO 消息增加 platform
{
    "type": HELLO,
    "device_id": settings.device_id,
    "token": settings.token,
    "name": settings.display_name(),
    "capabilities": ["console", "sandbox"],
    "platform": sys.platform,  # 新增：linux | darwin | win32
}
```

Gateway 据此知道设备类型，前端可以显示 "Windows PC" / "Mac" / "Linux Server"。

### Host Sidecar 部署 — 统一 CLI（所有平台）

**所有平台统一用 `npx @lca/host`**。`python -m host` 是 npm 包内部实现细节，不是用户接口。

| 场景 | 命令 |
|---|---|
| 本机 sidecar（Linux/Mac/Windows） | `npx @lca/host start` |
| 远程 sidecar（连接到远程 gateway） | `npx @lca/host connect --gateway ws://... --token ...` |
| 查看状态 | `npx @lca/host status` |
| 停止 | `npx @lca/host stop` |
| 重启 | `npx @lca/host restart` |
| 日志 | `npx @lca/host logs` |

**`start_lobehub_stack.sh` 也应改用**：

```bash
# 之前
uv run python -m host

# 之后
npx @lca/host start
```

**重要：不再创建 `sandbox_user`（向后兼容策略）**

旧的 `setup_host_runtime.sh` 会创建 `sandbox_user` 系统用户来隔离 sidecar。npm CLI 采用更简单的策略：

**默认**：直接用当前用户（`os.userInfo().username`），workspace 在 `~/workspace`。

**向后兼容**：检测已有的 `sandbox_user` 配置，提供迁移选项。

```typescript
async function resolveWorkspace(options: { workspace?: string }) {
  // 1. 显式指定 → 用它
  if (options.workspace) return options.workspace;
  
  // 2. 检测已有 setup
  const existingSetup = await detectExistingSetup();
  
  if (existingSetup?.type === "sandbox-user") {
    // 已有 /home/sandbox-user 配置
    console.log("发现已有配置: /home/sandbox-user");
    console.log("选项:");
    console.log("  1. 继续使用 /home/sandbox-user (推荐，保持兼容)");
    console.log("  2. 迁移到 ~/workspace (当前用户)");
    
    const choice = await prompt("选择 [1/2]: ");
    if (choice === "1") {
      return "/home/sandbox-user";
    } else {
      await migrateWorkspace("/home/sandbox-user", path.join(os.homedir(), "workspace"));
      return path.join(os.homedir(), "workspace");
    }
  }
  
  // 3. 无已有 setup → 用当前用户
  return path.join(os.homedir(), "workspace");
}
```

**使用场景**：

```bash
# 场景 A: 全新安装（无 sandbox_user）
npx @lca/host start
# → 创建 ~/workspace，用当前用户

# 场景 B: 已有 sandbox_user
npx @lca/host start
# → 检测到 /home/sandbox-user
# → 问用户：继续用还是迁移？

# 场景 C: 显式指定（跳过检测）
npx @lca/host start --workspace /home/sandbox-user
# → 直接用，不问

# 场景 D: 强制迁移
npx @lca/host migrate
# → 从 /home/sandbox-user 迁移到 ~/workspace
# → 移动文件、更新配置、可选删除旧用户
```

**迁移命令**：

```typescript
async function migrate() {
  const from = "/home/sandbox-user";
  const to = path.join(os.homedir(), "workspace");
  
  if (!await fileExists(from)) {
    console.log("无旧配置需要迁移");
    return;
  }
  
  console.log(`迁移 ${from} → ${to}`);
  
  // 1. 复制文件
  await exec(`cp -r ${from}/* ${to}/`);
  
  // 2. 更新 .env
  const env = await readEnv(from);
  await writeEnv({ ...env, workspace: to, user: os.userInfo().username });
  
  // 3. 重启服务
  await restartService();
  
  // 4. 可选：删除旧目录和用户
  const cleanup = await prompt("删除旧的 /home/sandbox-user 和用户? [y/N]: ");
  if (cleanup === "y") {
    await exec(`sudo rm -rf ${from}`);
    await exec(`sudo userdel sandbox-user`);
  }
  
  console.log(`✓ 迁移完成`);
}
```

**目标**：一行命令搞定，和 LobeHub 的 `npx @lobehub/cli` 一样简单。

```bash
# 本机 Linux/Mac
npx @lca/host start

# 远程 Windows（连接到 Linux gateway）
npx @lca/host connect --gateway ws://10.36.6.252:8765 --token lca-local-host
```

**npm 包 `@lca/host`**：

```
@lca/host (npm package)
├── bin/lca-host              # CLI 入口
├── src/
│   ├── commands/
│   │   ├── start.ts          # `start` — 本机 sidecar
│   │   ├── connect.ts        # `connect` — 远程 sidecar（连接指定 gateway）
│   │   ├── migrate.ts        # `migrate` — 从 sandbox_user 迁移到当前用户
│   │   ├── stop.ts           # `stop`
│   │   ├── status.ts         # `status`
│   │   └── logs.ts           # `logs`
│   ├── platform/
│   │   ├── python-installer  # 检查/安装 Python + uv
│   │   ├── service-manager   # 注册 systemd / Task Scheduler / launchd
│   │   └── shell-detector    # Windows shell 检测
│   └── sidecar/              # 打包的 Python sidecar 代码
│       ├── host/
│       └── lca/
└── package.json
```

**`start` 命令（本机）**：

```typescript
// src/commands/start.ts
async function start(options: { workspace?: string }) {
  // 本机 sidecar：gateway 在本机或已知地址
  const gateway = await detectLocalGateway();  // 检查 localhost:8765
  
  // 默认 workspace = ~/workspace（当前用户，不创建新用户）
  const workspace = options.workspace || path.join(os.homedir(), "workspace");
  
  // 幂等检查
  if (await isAlreadyRunning()) {
    console.log("✓ Host sidecar already running");
    return;
  }
  
  await ensurePython();
  await ensureSidecarCode();
  await writeEnv({ 
    gateway, 
    token: "lca-local-host",
    device_id: os.hostname(),
    workspace,
    user: os.userInfo().username  // 当前用户，不是 sandbox_user
  });
  await registerService();
  await startService();
  console.log(`✓ Host sidecar running (workspace: ${workspace})`);
}
```

**`connect` 命令（远程）**：

```typescript
// src/commands/connect.ts
async function connect(options: { 
  gateway: string; 
  token: string;
  device_id?: string;
  workspace?: string;
}) {
  // 默认 device_id = hostname（每台机器自动不同）
  const deviceId = options.device_id || os.hostname();
  
  // 默认 workspace = ~/workspace
  const workspace = options.workspace || path.join(os.homedir(), "workspace");
  
  // 幂等检查
  if (await isAlreadyRunning(deviceId)) {
    console.log(`✓ Device ${deviceId} already connected`);
    return;
  }
  
  await ensurePython();
  await ensureSidecarCode();
  await writeEnv({ 
    gateway: options.gateway, 
    token: options.token,
    device_id: deviceId,
    workspace,
    user: os.userInfo().username
  });
  await registerService(deviceId);
  await startService();
  console.log(`✓ Connected as ${deviceId} (workspace: ${workspace})`);
}
```

**使用示例**：

```bash
# 本机 Linux（默认 workspace = ~/workspace，device_id = hostname）
npx @lca/host start

# 本机 Linux（自定义 workspace）
npx @lca/host start --workspace /data/lca-workspace

# 远程 Windows（默认 device_id = hostname）
npx @lca/host connect --gateway ws://10.36.6.252:8765

# 远程 Windows（显式 device_id，区分多台机器）
npx @lca/host connect --gateway ws://10.36.6.252:8765 --device-id "windows-dev-1"
npx @lca/host connect --gateway ws://10.36.6.252:8765 --device-id "windows-dev-2"

# 同一台机器多个实例（不同 workspace + device_id）
npx @lca/host connect --gateway ws://... --device-id "win-pc-work" --workspace C:\work
npx @lca/host connect --gateway ws://... --device-id "win-pc-personal" --workspace C:\personal
```

**幂等性**：
- 同一 device_id 多次运行 → 检测已存在，提示 "already connected"
- 不同 device_id → 创建新设备
- 同一 device_id 但 workspace 变了 → 更新配置，重启服务

**实现策略**：

1. **MVP（Phase 3）**：npm 包只是 wrapper
   - 检查 Python 是否已安装，未安装则提示用户手动安装
   - 下载 sidecar 代码（从 GitHub release 或 bundle in npm）
   - 运行 `uv run python -m host`
   - 注册 systemd / Task Scheduler / launchd

2. **V2（后续）**：更好的体验
   - 自动安装 Python（通过 winget / embedded Python）
   - 或用 PyInstaller 打包成单文件 .exe，完全不需要 Python

**跨平台**：

```bash
# Linux / macOS
npx @lca/host connect --gateway ws://10.36.6.252:8765 --token lca-local-host
```

同样的命令，同样的体验。npm 包检测平台，选择正确的安装策略。

---

**对比**：

| 方式 | 步骤 | 用户体验 |
|---|---|---|
| 手动（§3.4 原始方案） | 5+ 步，需要懂 Python/uv/PowerShell | ❌ 复杂 |
| `npx @lca/host connect` | 1 步 | ✅ 和 LobeHub CLI 一样 |

### 3.5 Factory

```python
# lca/layer0_infra/execution/factory.py

import os
from typing import Optional

from lca.layer0_infra.execution.config import ExecutionConfig, load_execution_config


class ExecutionContextFactory:
    """根据配置和运行时状态创建 ExecutionContext。
    
    解析规则（LCA_EXECUTION_BACKEND 环境变量）：
    - "host": 强制 Host（无在线 host → 报错）
    - "onlyboxes": 强制 Onlyboxes（无配置 → 报错）
    - "ssh": 强制 SSH（无配置 → 报错）
    - "windows": 强制 Windows
    - "auto"（默认）: 
      1. Presence 有在线 host（sandbox capability）→ HostContext
      2. SSH 配置存在（LCA_SSH_HOST 非空）→ SSHContext  
      3. Onlyboxes 配置存在（ONLYBOXES_BASE_URL + TOKEN）→ OnlyboxesContext
      4. 检测到 Windows 平台 → WindowsContext
      5. None（无可用执行环境）
    """
    
    def __init__(self, config: ExecutionConfig | None = None):
        self._config = config or load_execution_config()
    
    async def resolve(self) -> Optional[ExecutionContext]:
        backend = self._config.backend
        
        if backend == "host":
            return await self._resolve_host()
        elif backend == "onlyboxes":
            return self._resolve_onlyboxes()
        elif backend == "ssh":
            return self._resolve_ssh()
        elif backend == "windows":
            return self._resolve_windows()
        elif backend == "auto":
            return await self._resolve_auto()
        else:
            raise ValueError(f"unknown backend: {backend}")
    
    async def _resolve_auto(self) -> Optional[ExecutionContext]:
        """Auto-detect 优先级。
        
        理由：Host 在线意味着用户显式连接了一台机器（最明确意图）；
        SSH 配置意味着用户想连远程机器；
        Onlyboxes 通常是后台默认值，不覆盖显式配置。
        Windows 仅在 gateway 跑在 Windows 上且无远程 host 时触发。
        """
        # 1. Host: 检查 Presence（含远程 Windows/Linux/Mac sidecar）
        host_ctx = await self._resolve_host()
        if host_ctx is not None:
            return host_ctx
        
        # 2. SSH: 检查配置（远程 Linux/Mac 无 sidecar 场景）
        ssh_ctx = self._resolve_ssh()
        if ssh_ctx is not None:
            return ssh_ctx
        
        # 3. Onlyboxes: 检查配置（云端容器）
        onlyboxes_ctx = self._resolve_onlyboxes()
        if onlyboxes_ctx is not None:
            return onlyboxes_ctx
        
        # 4. Windows: 仅当 gateway 本身跑在 Windows 上
        windows_ctx = self._resolve_windows()
        if windows_ctx is not None:
            return windows_ctx
        
        return None
    
    async def _resolve_host(self) -> Optional[ExecutionContext]:
        """检查 Presence 是否有在线 host。"""
        from gateway.presence.registry import PresenceRegistry
        from gateway.host_sandbox import HostSandbox
        
        # 注入 PresenceRegistry（由 gateway 启动时设置）
        registry = _get_presence_registry()
        if registry is None:
            return None
        
        sandbox = HostSandbox.from_presence(registry, _get_exec_hub())
        if sandbox is None:
            return None
        
        from lca.layer0_infra.sandbox.host_settings import load_host_settings
        settings = load_host_settings()
        return HostContext(sandbox, settings)
    
    def _resolve_ssh(self) -> Optional[ExecutionContext]:
        if not self._config.ssh_host:
            return None
        return SSHContext(SSHConfig(
            alias=self._config.ssh_alias or self._config.ssh_host,
            host=self._config.ssh_host,
            user=self._config.ssh_user,
            port=self._config.ssh_port,
            key_path=self._config.ssh_key_path,
            workspace=self._config.ssh_workspace,
        ))
    
    def _resolve_onlyboxes(self) -> Optional[ExecutionContext]:
        if not self._config.onlyboxes_base_url or not self._config.onlyboxes_token:
            return None
        from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter
        sandbox = OnlyboxesSandboxAdapter(
            base_url=self._config.onlyboxes_base_url,
            access_token=self._config.onlyboxes_token,
        )
        return OnlyboxesContext(sandbox)
    
    def _resolve_windows(self) -> Optional[ExecutionContext]:
        """Windows 只在 gateway 本机时使用。远程 Windows 通过 HostContext 访问。"""
        import sys
        if sys.platform != "win32":
            return None
        return WindowsContext(WindowsConfig(
            device_id="local-windows",
            label="Local Windows",
            workspace=self._config.windows_workspace or self._default_windows_workspace(),
        ))
    
    def _default_windows_workspace(self) -> str:
        import os
        home = os.environ.get("USERPROFILE", "C:\\Users\\Default")
        return os.path.join(home, "lca-workspace")


# 全局注入点（由 gateway 启动时设置）
_presence_registry = None
_exec_hub = None

def _get_presence_registry():
    return _presence_registry

def _get_exec_hub():
    return _exec_hub

def set_gateway_services(registry, hub):
    global _presence_registry, _exec_hub
    _presence_registry = registry
    _exec_hub = hub
```

### 3.6 配置

```python
# lca/layer0_infra/execution/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionConfig(BaseSettings):
    """执行环境统一配置。
    
    合并 host / ssh / windows / onlyboxes 的配置，
    由 factory 按需读取。
    """
    model_config = SettingsConfigDict(
        env_prefix="LCA_",
        env_file=(".env", "deploy/lobehub/.env.lca"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # 通用
    execution_backend: str = "auto"  # auto | host | onlyboxes | ssh | windows
    
    # Host
    host_user: str = "sandbox-user"
    host_root: str = ""  # 空 → /home/${host_user}
    host_device_id: str = "local-host"
    host_token: str = "lca-local-host"
    
    # SSH
    ssh_host: str = ""
    ssh_user: str = ""
    ssh_port: int = 22
    ssh_key_path: str = ""
    ssh_workspace: str = ""  # 空 → 远程 $HOME
    ssh_alias: str = ""      # 显示名，空 → ssh_host
    
    # Windows
    windows_workspace: str = ""  # 空 → USERPROFILE/lca-workspace
    
    # Onlyboxes (复用现有环境变量名)
    onlyboxes_base_url: str = ""
    onlyboxes_token: str = ""


def load_execution_config() -> ExecutionConfig:
    return ExecutionConfig()
```

环境变量映射：

```bash
# .env
LCA_EXECUTION_BACKEND=auto

# Host
LCA_HOST_USER=sandbox-user
LCA_HOST_ROOT=
LCA_HOST_DEVICE_ID=local-host
LCA_HOST_TOKEN=lca-local-host

# SSH
LCA_SSH_HOST=smartljy
LCA_SSH_USER=smartljy
LCA_SSH_PORT=22
LCA_SSH_KEY_PATH=~/.ssh/id_rsa
LCA_SSH_WORKSPACE=
LCA_SSH_ALIAS=smartljy

# Windows
LCA_WINDOWS_WORKSPACE=C:\Users\lichao\workspace

# Onlyboxes (保持现有变量名兼容)
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

**Host 示例**：
```
你正在 **lichao-mbp** 上操作（本机 host，backend=host）。
工作区：`/home/sandbox-user`
交付物写到 `/home/sandbox-user/outputs`
附件在 `/home/sandbox-user/<文件名>`
```

**Onlyboxes 示例**：
```
你正在 **Onlyboxes Sandbox** 上操作（云端容器，backend=onlyboxes）。
工作区：`/mnt/data`
交付物写到 `/mnt/data/outputs`
这是一个隔离环境，非用户本机文件系统。
```

**SSH 示例**：
```
你正在 **smartljy** 上操作（远程 SSH，backend=ssh）。
工作区：`/home/smartljy`
交付物写到 `/home/smartljy/outputs`
这是远程机器的真实文件系统。
```

**Windows 示例**：
```
你正在 **lichao-pc** 上操作（本机 Windows，backend=windows）。
工作区：`C:\Users\lichao\workspace`
交付物写到 `C:\Users\lichao\workspace\outputs`
路径使用 Windows 格式。
```

### 3.8 Skills 参数化

Skill 不再硬编码 `/mnt/data`，改用占位符 `{workspace}` 和 `{outputs_dir}`：

```markdown
# officecli SKILL.md

| 工作区 | 附件在 `{workspace}/<文件名>`；交付物写 **`{outputs_dir}/`** |

officecli create {outputs_dir}/report.pptx --json
```

**占位符替换机制**：

在 skill 加载时（`SkillPackageStore.get()` 或 `activate_skill` tool 执行时），
根据当前 `ExecutionContext` 替换占位符：

```python
# lca/layer0_infra/skills/skill_renderer.py

def render_skill_content(content: str, context: ExecutionContext) -> str:
    """替换 skill 内容中的路径占位符。"""
    return (
        content
        .replace("{workspace}", context.workspace)
        .replace("{outputs_dir}", context.outputs_dir)
    )
```

**调用点**：
- `SkillActivateTool.execute()` 激活 skill 时调用 `render_skill_content()`
- `run_skill_script` 执行 skill 脚本时调用 `render_skill_content()`

### 3.9 Tools

工具接收 `ExecutionContext`，不再接收 `Sandbox` + mount 参数：

```python
class ListFilesTool(Tool):
    name = "list_files"
    description = "List files in a directory."
    parameters = {
        "type": "object",
        "properties": {
            "directory_path": {"type": "string", "description": "Directory path"}
        },
        "required": ["directory_path"],
    }
    
    def __init__(self, context: ExecutionContext):
        self._context = context
    
    async def execute(self, args: dict) -> Observation:
        result = await self._context.execute("list_files", args)
        
        if not result.success:
            return Observation(
                success=False,
                error=result.error,
                payload=None,
            )
        
        return Observation(
            success=True,
            payload=result.data,  # {files: [...], total_count: int}
        )
```

**工具不再知道 backend、不做路径翻译。`execute()` 返回的 `OpResult` 已经是统一结构。**

### 3.10 前端与 Gateway 集成

前端从 gateway 获取 context 信息：

```json
// GET /lca-api/context
{
  "context_id": "local-host",
  "context_label": "lichao-mbp",
  "context_backend": "host",
  "context_workspace": "/home/sandbox-user",
  "context_outputs_dir": "/home/sandbox-user/outputs"
}
```

**Gateway 如何获取 context**：
- 调用 `ExecutionContextFactory.resolve()`
- 结果缓存在 gateway state，Presence 变化时刷新

**文件下载 URL 生成**：

```python
# gateway/runs/file_download.py

async def generate_download_url(
    context: ExecutionContext, 
    workspace_path: str
) -> str:
    """将 workspace 路径转为可下载的 URL。
    
    策略：
    - Host / Windows: 路径在 gateway 本机，直接读文件返回
    - SSH: 通过 ssh cat 读取，流式返回
    - Onlyboxes: 通过 sandbox adapter 读取
    """
    if context.backend == BackendKind.HOST:
        # 直接读本地文件
        local_path = workspace_path  # workspace 就是本机路径
        return _serve_local_file(local_path)
    
    elif context.backend == BackendKind.WINDOWS:
        # Windows 路径，直接读
        return _serve_local_file(workspace_path)
    
    elif context.backend == BackendKind.SSH:
        # 通过 SSH 读取
        return _serve_ssh_file(context, workspace_path)
    
    elif context.backend == BackendKind.ONLYBOXES:
        # 通过 Onlyboxes adapter 读取
        return _serve_onlyboxes_file(context, workspace_path)
```

**新增模块**：
- `gateway/runs/file_download.py`: 文件下载代理（SSH / Onlyboxes 需要远程读取）
- `gateway/runs/context_api.py`: `/lca-api/context` endpoint

---

## 4. 删除清单

| 模块 | 动作 |
|---|---|
| `host/paths.py::rewrite_guest_refs` | **删除** |
| `host/paths.py::resolve_guest_path` | **简化**为 "resolve relative to workspace"，去掉 `mount` 参数 |
| `host/local_shell/paths.py` | **简化**，去掉 `mount` 参数 |
| `host/local_shell/dispatch.py` | 去掉 `mount` 参数 |
| `host/local_shell/file/*.py` | 所有 handler 去掉 `mount` 参数 |
| `host/local_shell/shell/runner.py` | 去掉 `mount` 参数 |
| `host/exec.py` | 去掉 `mount` 参数 |
| `lca/layer0_infra/sandbox/surface.py` | **替换**为 ExecutionContext（保留文件但内容迁移） |
| `lca/layer0_infra/sandbox/host_settings.py` | 合并进 `ExecutionConfig` |
| `lca/layer0_infra/computer/constants.py::COMPUTER_WORKSPACE_ROOT` | **删除**硬编码，从 context 取 |
| `lca/layer0_infra/sandbox/bootstrap.py` | 从 `context.workspace` 构建路径 |
| `lca/layer0_infra/sandbox/runtime_mount.py` | 从 `context.workspace` 构建路径 |
| `lca/layer0_infra/sandbox/output_collect.py` | 从 `context.outputs_dir` 构建路径 |
| `lca/layer0_infra/sandbox/inspect_prelude.py` | 从 `context.workspace` 构建路径 |
| `lca/layer0_infra/sandbox/error_parse.py` | 从 `context.workspace` 构建错误提示 |
| `lca/layer0_infra/sandbox/prompt.py` | 用 `context.prompt_context()` 替换硬编码 |
| `lca/layer0_infra/computer/runtime.py::_normalize_path` | 从 `context.workspace` 解析 |
| `lca/layer0_infra/computer/guest/preamble.py::ROOT` | 从 `context.workspace` 注入 |
| `skills/officecli/SKILL.md` | `/mnt/data` → `{workspace}` / `{outputs_dir}` |
| `lca/contracts/models/core/sandbox.py::SANDBOX_MOUNT_ROOT` | 保留作为 Onlyboxes 内部常量，不再作为全局注入 |

---

## 5. 保留清单

| 模块 | 理由 |
|---|---|
| `lca/contracts/protocols/infra.py::Sandbox` | 执行传输层 Protocol，不变。仅作为 ExecutionContext 内部传输 |
| `host/local_shell/file/*.py` | 本机文件操作实现，简化后保留 |
| `host/local_shell/shell/*.py` | 本机 shell 操作实现，简化后保留 |
| `host/local_shell/dispatch.py` | 操作路由表，简化后保留 |
| `gateway/host_sandbox.py` | Host → Sandbox 适配层，被 HostContext 内部使用 |
| `gateway/presence/` | Presence 注册/路由 |
| `lca/layer0_infra/sandbox/onlyboxes_adapter.py` | Onlyboxes Sandbox 实现，被 OnlyboxesContext 内部使用 |
| `lca/layer0_infra/sandbox/factory.py` | 改为解析 ExecutionContext（或废弃，由新 factory 替代） |

---

## 6. 新增清单

| 模块 | 说明 |
|---|---|
| `lca/contracts/protocols/execution.py` | `ExecutionContext` Protocol + `BackendKind` + `OpResult` |
| `lca/layer0_infra/execution/__init__.py` | 包入口 |
| `lca/layer0_infra/execution/host_context.py` | Host 实现 |
| `lca/layer0_infra/execution/onlyboxes_context.py` | Onlyboxes 实现 |
| `lca/layer0_infra/execution/ssh_context.py` | SSH 实现 |
| `lca/layer0_infra/execution/windows_context.py` | Windows 实现 |
| `lca/layer0_infra/execution/factory.py` | Context factory |
| `lca/layer0_infra/execution/config.py` | 统一配置（pydantic model） |
| `lca/layer0_infra/skills/skill_renderer.py` | Skill 占位符替换 |
| `gateway/runs/file_download.py` | 文件下载代理 |
| `gateway/runs/context_api.py` | `/lca-api/context` endpoint |
| `packages/host-sidecar/` | `@lca/host` npm 包 — 一键安装 sidecar |

---

## 7. 迁移策略

**分 3 步，每步可独立交付和测试。**

### Phase 1: 建 Protocol + Host/Onlyboxes 实现（核心迁移）

1. 新增 `ExecutionContext` Protocol + `BackendKind` + `OpResult`
2. 实现 `HostContext`、`OnlyboxesContext`
3. 新增 `ExecutionContextFactory` + `ExecutionConfig`
4. 新工具接收 `ExecutionContext`；旧工具通过 `ComputerRuntime` 适配
5. Prompt 切换到 `context.prompt_context()`
6. `ComputerRuntime` 内部查询 context 获取 workspace

**Phase 1 结束状态**：
- 两套注入并存（ExecutionContext + Sandbox）
- Host 和 Onlyboxes 走真实路径
- 旧工具仍可工作（通过适配层）
- 新增测试覆盖 4 种 backend 的 prompt 输出

### Phase 2: 去 remap 层

1. 删除 `rewrite_guest_refs`、`resolve_guest_path`
2. 简化 `host/paths.py`、`local_shell/paths.py`（去掉 `mount`）
3. 所有 handler 去掉 `mount` 参数
4. Skill 参数化（`{workspace}` / `{outputs_dir}`）
5. Skill 渲染机制（`skill_renderer.py`）

**Phase 2 结束状态**：
- 不存在任何路径翻译层
- 所有路径都是 workspace 下的真实路径
- Skill 不含硬编码路径

### Phase 3: 加 SSH / Windows

1. 实现 `SSHContext`（含端到端测试）
2. 实现 `WindowsContext`（含端到端测试）
3. 文件下载代理（SSH / Onlyboxes 远程读取）
4. `/lca-api/context` endpoint
5. 前端集成 context 显示

**Phase 3 结束状态**：
- 4 种环境全部可用
- 前端能显示当前 context 信息
- 下载卡在 4 种环境下都能工作

---

## 8. 验证标准

### 功能验证

- [ ] Host 环境：agent 操作 `/home/sandbox-user/...`，前端显示真实路径
- [ ] Onlyboxes 环境：agent 操作 `/mnt/data/...`（容器内真实路径）
- [ ] SSH 环境：agent 操作远程真实路径，文件通过 ssh cat / scp 传输
- [ ] Windows 环境：agent 操作 `C:\...`，PowerShell 执行
- [ ] 不存在任何 `/mnt/data` 硬编码（除 Onlyboxes 内部常量）
- [ ] 不存在 `rewrite_guest_refs` 或等价翻译层
- [ ] Skill 不含硬编码路径（用 `{workspace}` 占位符）
- [ ] 前端能显示当前 context 的 id/label/backend/workspace
- [ ] Journal 记录 context.id

### 负面验证

- [ ] Agent 尝试访问 `/mnt/data` 在 host 环境 → 得到 `FileNotFoundError`（不 remap）
- [ ] Tool 收到不存在的 op → 返回结构化错误 `OpResult(success=False, error=...)`，不抛异常
- [ ] Factory 无 backend 配置 → 返回 `None`，系统优雅降级（提示用户配置）
- [ ] SSH host 不可达 → `OpResult(success=False, error="connection failed")`，不 crash
- [ ] Windows PowerShell 不存在 → 启动时 warning，运行时优雅报错

---

## 9. 设计原则

1. **真实路径**: agent 操作的就是那台机器上的真实文件系统路径
2. **单一命名空间**: 不存在 guest/host 双路径，workspace 就是 THE path
3. **身份一等公民**: context.id + label 流入 prompt、前端、Journal
4. **传输无关**: Protocol 只承诺 `execute(op, payload) -> OpResult`，不关心传输细节
5. **类型安全**: `BackendKind` 枚举 + `OpResult` 统一结构，myPy 可检查
6. **开闭原则**: 新增 backend 只需实现 ExecutionContext Protocol
7. **无补丁**: 不在垃圾机制上做修补，直击本质
8. **渐进迁移**: 新旧并存，逐步切换，不 break 现有功能

---

## 10. 实现备注（来自 reviewer 建议）

1. **Observation 需要 observation_id**: `ListFilesTool.execute()` 示例中创建 `Observation` 时需要生成 `observation_id`（如 `new_id("obs")`），这是 `Observation` dataclass 的必需字段。

2. **Factory 层级隔离**: `layer0_infra/execution/factory.py` **不得**在模块顶层 import gateway 类型。所有 gateway 引用必须通过 `set_gateway_services()` 注入点传入，保持 L0 → gateway 的单向依赖清洁。

3. **OnlyboxesContext.execute()**: 参考现有 `OnlyboxesSandboxAdapter` 的 `run()`、`run_terminal()`、`write_files()` 方法构建 op dispatch。File ops 走 guest Python scripts（与现有 ComputerRuntime 一致）。

4. **Auto-detect 优先级理由**: SSH > Onlyboxes 因为 SSH 暗示用户显式意图（配置了远程机器就是要用）；Onlyboxes 通常是后台默认值，不应覆盖显式配置。

5. **ONLYBOXES 环境变量**: `ONLYBOXES_BASE_URL` 和 `ONLYBOXES_ACCESS_TOKEN` 不使用 `LCA_` 前缀，保持与现有代码兼容。实现时不要重命名。

6. **ComputerRuntime 获取 ExecutionContext**: 通过构造函数注入或 factory 查找。Phase 1 期间，`ComputerRuntime.__init__` 接受可选的 `ExecutionContext` 参数；若为 None，则通过全局 factory 查找。

---

## 11. 与 Reviewer 反馈的对应

| Reviewer Issue | 解决方案 |
|---|---|
| Sandbox Protocol lifetime / migration seam | §3.3 明确 coexistence + 分阶段迁移 |
| execute() return contract | §3.2 `OpResult` + data 契约文档 |
| SSH/Windows under-specified | §3.4 完整实现代码 + 端到端映射 |
| Factory resolution logic | §3.5 明确的 auto-detect 优先级 + env var 语义 |
| backend as bare str | §3.2 `BackendKind` 枚举 |
| Prompt/Skill placeholder | §3.7 prompt_context() + §3.8 skill_renderer.py |
| Phase 2 replacement API | §4 简化后的路径解析 + §3.9 工具直接调 context.execute() |
| Gateway file proxy for SSH/Windows | §3.10 file_download.py 模块 |
