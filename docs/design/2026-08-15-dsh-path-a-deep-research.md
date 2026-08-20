# 路径 A 深入研究：DSH 作为 LCA 的高级工具后端

**日期**: 2026-08-15
**状态**: 研究草案（已本地实测）
**前置**: [`2026-08-14-deepseek-harness-integration-analysis.md`](./2026-08-14-deepseek-harness-integration-analysis.md)

---

## 0. 本地实测结论（先看这个）

在 LCA 工作区安装了源码版 `deepseek-harness-sdk` + `deepseek-harness-runtime-bin`，并用 `scripts/build-exe-for-python-sdk.ts --skip-build` 打出了 linux-x64 单文件运行时（约 197 MB）。

| 测量 | 结果 |
|---|---|
| 默认组合 `initialize`（无 prompt） | **0.41–0.52 s** |
| 自定义 `examples/jsonrpc-agent/cordis.yml` 启动 | **0.24 s** |
| `session/prompt` → `turn/end` 协议闭环 | 通 |
| 真实模型 turn | 请求发出后 **429 QUOTA**（DashScope Coding Plan 额度用尽），不是 SDK / 运行时故障 |
| 进程复用 | `DeepSeekHarness` 一次 `start()` 后可多次 `run()`，启动成本只付一次 |

默认 bundled `cordis.yml` 实际暴露给模型的工具是：

- `bash`
- `job_kill` / `job_list` / `job_output`
- `skill`

**没有** `read` / `write` / `edit` / `glob` / `grep` / 持久 bash。那些要换组合。

`jsonrpc-agent/cordis.yml` 经 bundled exe 加载成功，模型侧工具变成：

- `bash`
- `read` / `write` / `edit`
- `subagent`
- `todo_write`

SDK **没有** `tool/execute`。公开入口只有 `initialize` + `session/prompt` + `shutdown`。路径 A 今天能做的，只有「把一整个自然语言任务交给 DSH 再跑一轮它自己的 agent loop」，不能零开销地当 LCA 的 `run_command` 替身。

DeepSeek adapter 在未指定 `max_tokens` 时会物化自己的默认值：这次请求头是 `maxTokens: 256000`、`reasoningEffort: high`。接到非 DeepSeek 的 OpenAI 兼容口时，这两个默认值会一起带过去。

**对路径 A 的判断**：做成「一个 LCA 工具 = 一次 DSH turn」不划算，也不是 SDK 设计意图。唯一合理的第一刀是 **一个委派工具**（`delegate_to_harness`）：LCA 把整段执行子任务交给 DSH，DSH 用自己的 bash / fs / subagent 做完再交回文本。精细工具桥（A3）要等 DSH 暴露直接执行面，或我们自己改它的 JSON-RPC server。

---

## 1. DSH Python SDK 接口解剖

### 1.1 核心类

```python
from deepseek_harness import DeepSeekHarness, RunResult, Session

# 高级 API —— 一个实例持有一个长驻子进程
with DeepSeekHarness(
    provider="deepseek-official",   # LLM provider 路由名
    model="deepseek-v4-flash",       # 模型 id
    max_tokens=49_152,               # 可选输出 token 上限
    cwd="/path/to/workspace",        # agent 工作目录（真实路径）
    session_root="/path/.sessions",  # JSONL session 持久化目录
    cordis="path/to/cordis.yml",     # 插件组合配置
    base_url="https://api.deepseek.com",  # 可选，覆盖 DEEPSEEK_BASE_URL
    api_key="sk-...",                # 可选，覆盖 DEEPSEEK_API_KEY
) as harness:
    result: RunResult = harness.run("你的任务描述")
    print(result.final_response)     # 最终 assistant 文本
    print(result.finish_reason)      # "completed" | "max-tokens" | "error"
    print(result.events)             # 完整 session event 列表
    print(result.notifications)      # 包含子 agent 事件
```

### 1.2 RunResult 结构

```python
@dataclass
class RunResult:
    session_id: str           # 持久化 session 标识
    final_response: str       # 最后一条非空 assistant 文本
    finish_reason: str | None # turn 结束原因
    events: list[JsonObject]  # 根 session 的所有事件
    notifications: list[Notification]  # 含子 agent 全量通知
    session_root: str | None  # 持久化根路径
```

### 1.3 Session 多轮对话

```python
session = harness.start_session("my-session-id")
r1 = session.run("第一步：列出文件")
r2 = session.run("第二步：读取 main.py")  # 同一 session，上下文保持
```

### 1.4 底层 HarnessClient（JSON-RPC）

```python
from deepseek_harness import HarnessClient

client = HarnessClient(HarnessConfig(runtime_bin="/path/to/dsh-jsonrpc-agent"))
client.start()
client.initialize(cwd="/workspace", provider="deepseek-official", model="deepseek-v4-flash")
msg_id = client.session_prompt("session-1", [{"type": "text", "text": "hello"}])
# 通过 notification subscription 监听事件流
```

### 1.5 JSON-RPC Wire Protocol

| 方法 | 方向 | 说明 |
|---|---|---|
| `initialize` | client→server | 设置 cwd、provider、model、max_tokens |
| `session/prompt` | client→server | 向 session 发送 content blocks，返回 messageId |
| `shutdown` | client→server | 优雅关闭 |
| `session.event` | server→client (notification) | session 事件（turn/start, assistant/chunk, tool/call 等） |
| `session.status` | server→client (notification) | session 状态变化（idle/running） |
| `subagent.started` | server→client (notification) | 子 agent 启动 |
| `subagent.finished` | server→client (notification) | 子 agent 结束 |

---

## 2. DSH 提供的工具清单（jsonrpc-agent 组合）

通过 `cordis.yml` 组合，DSH jsonrpc-agent 向模型暴露以下工具：

| 工具名 | 包 | 能力 | LCA 是否有对等 |
|---|---|---|---|
| `bash` | `dsh-tool-bash` | 一次性 shell 命令，sandbox 隔离，超时控制 | ✅ `run_command`（但无 sandbox policy、无 background job） |
| `bash`（persistent） | `dsh-tool-bash-persistent` | 持久 PTY 会话，状态跨调用保持 | ❌ LCA 无对等 |
| `read` | `dsh-tool-fs` | 读文件（行号），UTF-8 | ✅ `read_file` |
| `write` | `dsh-tool-fs` | 创建/覆盖文件 | ✅ `write_file` |
| `edit` | `dsh-tool-fs` | 精确文本替换（read-before-write 策略） | ✅ `edit_file` |
| `read_image` | `dsh-tool-fs` | 读图片，需模型支持 image input | ❌ LCA 无对等 |
| `glob` | `dsh-tool-fs-search` | 基于 ripgrep 的文件发现，大结果自动 spill | 部分 ✅ `glob_files`（不用 ripgrep） |
| `grep` | `dsh-tool-fs-search` | 基于 ripgrep 的内容搜索，大结果自动 spill | 部分 ✅ `grep_content`（不用 ripgrep） |
| `subagent` | `dsh-tool-subagent` | 子 agent 委派（spawn/fork/acp/codex/claude-code） | ❌ LCA 无对等 |
| `todo_write` | `dsh-tool-todo` | 结构化 todo list | ❌ LCA 无对等（有外部 todo 工具） |
| `str_replace_editor` | `dsh-tool-str-replace-editor` | view/create/str_replace/insert 四合一 | ❌ LCA 无对等 |
| `terminal_*`（6 个） | `dsh-tool-terminal` | 持久 PTY 会话管理 | ❌ LCA 无对等 |

**LCA 没有但 DSH 有的关键能力**：
- 持久 bash 会话（PTY state 跨调用保持）
- ripgrep-backed 搜索（不需要安装 rg，自带 `@vscode/ripgrep`）
- read-before-write 强制策略（事件驱动，不改 schema）
- spill store（大结果溢出到文件，返回 locator）
- 子 agent 委派
- sandbox policy（`danger-full-access` / workspace 限制）

---

## 3. 集成架构设计

### 3.1 核心思路

```
LCA Agent Loop                    DSH Runtime (子进程)
┌───────────────┐                ┌─────────────────────────────┐
│               │  JSON-RPC      │                             │
│  LCA Brain    │ ────────────>  │  Agent Loop (DSH)           │
│  (决策层)      │   stdio        │  ├── LLM Adapter            │
│               │  <──────────── │  ├── Tool Pipeline           │
│  ┌──────────┐ │  notifications │  ├── Session Log             │
│  │ DshTool  │ │                │  └── Bash/FS/Terminal/...   │
│  │ Adapter  │ │                │                             │
│  └──────────┘ │                └─────────────────────────────┘
│               │
│  LCA Tools    │
│  (其他工具)    │
└───────────────┘
```

**关键设计决策**：DSH 不是被当作"一个工具"来用，而是当作"一组工具的执行引擎"。LCA 的 agent loop 仍然做决策（何时调用工具、何时响应），但具体的文件操作、shell 命令等"脏活"委派给 DSH。

### 3.2 两种集成模式

#### 模式 A1：DSH-as-Tool-Executor（推荐起步）

LCA 的每个 DSH-backed 工具直接发一个独立的 `session.run()` 给 DSH，DSH 执行后返回结果。

```python
class DshBashTool(Tool):
    """通过 DSH 执行 bash 命令。"""
    name = "dsh_bash"
    description = "在隔离环境中执行 bash 命令"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout_ms": {"type": "integer", "description": "超时毫秒数"},
        },
        "required": ["command"],
    }

    def __init__(self, harness: DeepSeekHarness):
        self._harness = harness

    async def execute(self, args: dict) -> Observation:
        # 每次调用启动一个独立 session
        session = self._harness.start_session()
        result = session.run(f"Run this bash command and return stdout only: {args['command']}")
        return Observation(content=result.final_response, success=True)
```

**问题**：每调一个工具就启动一个完整的 agent loop（包含 LLM 调用），太重了。DSH 的 agent 会"思考"再执行，一次 bash 调用可能消耗数百 token。

#### 模式 A2：DSH-as-Shared-Session（更实际）

LCA 维护一个长期 DSH session，所有 DSH-backed 工具共享这个 session 的上下文。DSH agent 有持久 bash 会话，状态跨工具调用保持。

```python
class DshToolBackend:
    """DSH 共享 session 后端 —— 管理一个持久 session。"""

    def __init__(self, harness: DeepSeekHarness):
        self._harness = harness
        self._session: Session | None = None

    def ensure_session(self) -> Session:
        if self._session is None:
            self._session = self._harness.start_session("lca-dsh-shared")
        return self._session

    def execute_task(self, task_description: str) -> str:
        session = self.ensure_session()
        result = session.run(task_description)
        return result.final_response

    def close(self):
        if self._session is not None:
            self._session = None
```

```python
class DshBashTool(Tool):
    """通过 DSH 的持久 bash 执行命令。"""
    name = "bash"
    description = "在持久 bash 会话中执行命令，状态跨调用保持"

    def __init__(self, backend: DshToolBackend):
        self._backend = backend

    async def execute(self, args: dict) -> Observation:
        result = self._backend.execute_task(
            f"Run this command in bash and return ONLY stdout: {args['command']}"
        )
        return Observation(content=result, success=True)


class DshGrepTool(Tool):
    """通过 DSH 的 ripgrep 搜索文件内容。"""
    name = "grep"
    description = "用正则搜索文件内容"

    def __init__(self, backend: DshToolBackend):
        self._backend = backend

    async def execute(self, args: dict) -> Observation:
        result = self._backend.execute_task(
            f"Search for pattern '{args['pattern']}' in {args.get('path', '.')} "
            f"and return the matching lines with line numbers."
        )
        return Observation(content=result, success=True)
```

**优势**：
- bash 状态（cwd、变量、进程）跨调用保持
- 搜索用真正的 ripgrep
- 文件系统操作有 read-before-write 策略保护
- 所有 DSH 工具共享同一个 session log，可审计

**代价**：
- 每次工具调用 = 一次 DSH agent loop turn = 一次 LLM 调用
- 需要额外的 API 费用（DSH 内部用 DeepSeek 模型来理解工具调用指令）
- 延迟增加（LCA → DSH LLM → 工具执行 → 返回）

### 3.3 更优的模式 A3：直接调用 DSH 工具管线（跳过 DSH 的 LLM）

DSH 的 `HarnessClient` 底层是 JSON-RPC。如果我们可以直接调用 DSH 的工具而不经过其 agent loop，就能避免额外的 LLM 调用。

但查看 SDK 源码发现，**DSH 的 Python SDK 没有暴露直接调用工具的方法**。`session/prompt` 是唯一入口，它总是走完整的 agent loop（LLM 决策 → 工具执行 → 返回结果）。

**可能的绕过方案**：

1. **自定义 cordis.yml**：配置一个极简 agent，禁用 LLM reasoning，让工具调用指令直接透传
2. **扩展 SDK**：在 DSH 侧增加一个 `tool/execute` JSON-RPC 方法，直接路由到 `ctx.tools`
3. **用 DSH 的 code mode**：通过 `run_code` 工具直接执行 TypeScript 代码调用工具

方案 2 最干净，但需要修改 DSH 源码。方案 3 最 hack 但最快可以验证。

---

## 4. 成本-收益量化分析

### 4.1 模式 A2 的每次工具调用成本

已测到的部分：

| 阶段 | 实测 / 估计 | Token |
|---|---|---|
| 首次 `DeepSeekHarness.start()` | **0.24–0.52 s** | 0 |
| 后续 `run()` 的 JSON-RPC 往返 | 毫秒级 | 0 |
| DSH 组装 prompt + 发模型请求 | 本次 429 在 **0.49 s** 内返回（含 HTTP） | 请求已发出；成功 turn 未测到 |
| DSH LLM 推理 + 工具 + 总结 | 未测到（额度 429） | 默认请求头带 `maxTokens=256000`、`reasoningEffort=high` |

未测到成功 turn 之前，不能把「2–5 s / 1000–3000 token」写成事实。能确定的是：

- 启动成本可接受，适合 **长驻一个子进程**，不适合每次工具调用 spawn。
- 每一次 `run()` 都是完整 agent turn，不是一次本地 `exec`。
- 把 `ls` / `read_file` 这种 LCA 已有工具转给 DSH，一定亏。

---

### 4.2 什么场景下值得

| 场景 | 是否值得用 DSH | 理由 |
|---|---|---|
| 简单文件读写 | ❌ | LCA 自己的工具够用，不需要额外开销 |
| 复杂 bash 脚本（需要状态保持） | ✅ | DSH 的 persistent bash 是杀手级能力 |
| 大范围代码搜索 | ✅ | ripgrep + spill store 远优于 LCA 当前实现 |
| 需要 agent 自主探索的任务 | ✅✅ | 委派给 DSH 的完整 agent loop，它可以多步推理 |
| 子任务委派 | ✅ | DSH 的 subagent 系统成熟 |

---

## 5. 推荐落地方案

### 5.1 第一阶段：DSH 作为「委派执行器」

不把 DSH 拆成单独的工具，而是作为一个**委派目标**。LCA 的 agent 判断"这个任务需要更强的执行能力"时，把整个子任务发给 DSH。

```python
class DshDelegationTool(Tool):
    """把复杂执行任务委派给 DeepSeek Harness。"""
    name = "delegate_to_harness"
    description = (
        "把需要复杂文件操作、代码搜索、bash 脚本的任务委派给 DSH 执行。"
        "DSH 有持久 bash、ripgrep 搜索、文件系统策略等高级能力。"
        "输入是自然语言任务描述，输出是执行结果。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "任务描述"},
            "workspace": {"type": "string", "description": "工作目录（绝对路径）"},
        },
        "required": ["task"],
    }

    def __init__(self, backend: DshToolBackend):
        self._backend = backend

    async def execute(self, args: dict) -> Observation:
        result = self._backend.execute_task(args["task"])
        return Observation(content=result, success=True)
```

**优势**：
- 集成成本最低（一个工具）
- 不需要修改 DSH
- LCA 保持决策权，DSH 负责执行
- 可以利用 DSH 的完整工具链和 agent 推理能力

### 5.2 第二阶段：按需拆分精细工具

当发现「委派整个任务」太粗粒度时，再拆出特定工具：

```python
# 只在需要持久 bash 的场景下用
class DshPersistentBashTool(Tool): ...

# 只在需要大范围搜索时用
class DshCodeSearchTool(Tool): ...

# 只在需要子 agent 委派时用
class DshSubagentTool(Tool): ...
```

### 5.3 第三阶段：直接调用 DSH 工具管线

如果需要零开销地调用 DSH 的工具（不经过 DSH 的 LLM），需要：

1. 给 DSH 的 JSON-RPC server 增加 `tool/execute` 方法
2. 或者使用 DSH 的 `code mode`（`run_code` 工具），通过 TypeScript 代码直接调用 `ctx.tools`

```python
# 通过 code mode 直接调用 DSH 工具
result = session.run("""
请使用 run_code 工具执行以下 TypeScript 代码：
const fs = await tools.read({ file_path: "/path/to/file.py" });
return fs;
""")
```

---

## 6. 具体实施步骤

### 6.1 前置条件

```bash
# 构建 DSH（已完成 pnpm install）
cd ~/deepseek-harness
pnpm run build

# 安装 Python SDK
cd python/sdk
uv pip install -e .
# 或从源码
uv pip install -e ../sdk -e ../sdk-runtime
```

### 6.2 最小可运行验证

```python
# dsh_poc.py — 验证 DSH 作为 LCA 工具后端是否可行
from deepseek_harness import DeepSeekHarness

def main():
    with DeepSeekHarness(
        provider="deepseek-official",
        model="deepseek-v4-flash",
        cwd="/tmp/dsh-test-workspace",
        session_root="/tmp/dsh-test-sessions",
    ) as harness:
        # 模拟 LCA 委派一个文件操作任务
        result = harness.run(
            "List all Python files in the current directory and count their total lines."
        )
        print(f"Response: {result.final_response}")
        print(f"Finish reason: {result.finish_reason}")
        print(f"Events: {len(result.events)}")

if __name__ == "__main__":
    main()
```

### 6.3 LCA 集成骨架

```python
# lca/layer0_infra/tools/dsh_backend.py

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from typing import Any, ClassVar

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool

log = structlog.get_logger(__name__)


@dataclass
class DshConfig:
    provider: str = "deepseek-official"
    model: str = "deepseek-v4-flash"
    max_tokens: int | None = None
    workspace: str = "/tmp/lca-dsh-workspace"
    session_root: str = "/tmp/lca-dsh-sessions"
    cordis: str | None = None  # 自定义 cordis.yml 路径


class DshToolBackend:
    """DSH 子进程后端 —— 生命周期管理。"""

    def __init__(self, config: DshConfig | None = None):
        self._config = config or DshConfig()
        self._harness: Any = None  # DeepSeekHarness, lazy init

    def _ensure_harness(self):
        if self._harness is None:
            from deepseek_harness import DeepSeekHarness
            self._harness = DeepSeekHarness(
                provider=self._config.provider,
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                cwd=self._config.workspace,
                session_root=self._config.session_root,
                cordis=self._config.cordis,
            )
            self._harness.start()
        return self._harness

    def execute(self, task: str, session_id: str | None = None) -> str:
        harness = self._ensure_harness()
        result = harness.run(task, session_id=session_id)
        log.info("dsh.execution_complete",
                 finish_reason=result.finish_reason,
                 event_count=len(result.events))
        return result.final_response

    def close(self):
        if self._harness is not None:
            self._harness.close()
            self._harness = None


# ─── LCA Tool 包装 ───────────────────────────────────


class DshDelegationTool(Tool):
    """委派复杂执行任务给 DSH。"""
    name = "delegate_to_harness"
    description = (
        "把需要高级文件操作、代码搜索、持久 bash 的任务委派给 DSH 执行。"
        "DSH 拥有持久 bash 会话、ripgrep 搜索、文件系统保护策略等能力。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "自然语言任务描述"},
        },
        "required": ["task"],
    }
    is_idempotent = False
    default_timeout_s = 120

    def __init__(self, backend: DshToolBackend):
        self._backend = backend

    async def execute(self, args: dict[str, Any]) -> Observation:
        task = str(args["task"])
        try:
            response = self._backend.execute(task)
            return Observation(content=response, success=True)
        except Exception as e:
            log.error("dsh.delegation_failed", error=str(e))
            return Observation(content=f"DSH 执行失败: {e}", success=False)


def build_dsh_tools(backend: DshToolBackend) -> list[Tool]:
    """构建 DSH-backed 工具列表。"""
    return [DshDelegationTool(backend)]
```

---

## 7. 需要注意的坑

### 7.1 双 Agent Loop 问题

LCA 和 DSH 各自有一个 agent loop。当 LCA 委派任务给 DSH 时，DSH 的 LLM 会推理并调用工具。这意味着：
- 两层 LLM 调用，成本翻倍
- 两层推理可能产生不一致的决策
- DSH 的 LLM 可能做 LCA 已经做过的决策

**缓解**：用明确的指令模板约束 DSH 的行为，让它只做执行不做决策。

### 7.2 Session 持久化冲突

LCA 有自己的 Journal 系统，DSH 有自己的 Session Log。两套日志：
- 不互通，调试时需要交叉参照
- 存储路径可能冲突
- 可观测性链路断裂

**缓解**：DSH 的 session log 作为"执行证据"归档到 LCA 的 FileStore。

### 7.3 路径语义

DSH 操作的是真实路径（它的 `cwd`）。LCA 的 sandbox 模式使用 `/mnt/data` 虚拟路径。如果 DSH 在 host 上运行，它看不到 sandbox 里的文件。

**缓解**：DSH 只在 machine plane 下使用，sandbox plane 用 LCA 自己的工具。

### 7.4 DSH 还在 Developer Preview

DSH 明确标注了 "THERE WILL BE COMPATIBILITY-BREAKING CHANGES"。Python SDK 的 API 和 JSON-RPC 协议都可能变。

**缓解**：集成层做薄，只依赖 `DeepSeekHarness.run()` 这个最稳定的入口。

---

## 8. 与 LCA Execution Planes 的关系

```
PlaneBindings
├── primary: PlaneRef
│   ├── kind: MACHINE → 用 DSH 作为执行后端 ✅
│   └── kind: SANDBOX → 用 LCA 自己的 Sandbox 工具
└── secondary: PlaneRef | None
    └── 同上规则
```

DSH 只在 machine plane 下激活。这是因为：
- DSH 的 bash/fs 工具操作的是 host 真实文件系统
- sandbox plane 需要隔离执行，DSH 的 sandbox 策略与 LCA 的不同
- 两种环境的路径语义不兼容

---

## 9. 总结与建议

| 维度 | 评估 |
|---|---|
| **可行性** | 已证实。bundled exe + Python SDK 可在 LCA venv 里启动；自定义 `cordis.yml` 也能加载 |
| **公开 API** | 只有整轮 `session/prompt`。没有单工具执行面 |
| **价值** | 不在替换 `read_file` / `run_command`，而在委派「需要多步 bash / 编辑 / 子 agent」的整段任务 |
| **启动成本** | 0.2–0.5 s，一次进程可复用 |
| **成功 turn 成本** | 尚未测到（本机 Coding Plan 429）。补测前不要写死 token 数字 |
| **风险** | DSH 仍是 developer preview；adapter 默认按 DeepSeek 物化 `maxTokens` / `reasoningEffort` |
| **推荐** | **做薄委派工具，不要拆细工具桥。** 组合用 `jsonrpc-agent/cordis.yml`，不要用 bundled 默认那套（缺 fs 工具） |

**下一步（按顺序）**：

1. 等有可用的 DeepSeek / OpenAI 兼容额度，补一次成功 turn：记录墙钟、`finish_reason`、event 数、实际 usage。
2. 若成功 turn 可接受，在 LCA **machine plane** 加一个可选 `DshDelegationTool`，不进默认工具表。
3. `cordis` 指向 `examples/jsonrpc-agent/cordis.yml`（或我们裁过的副本）；`cwd` 绑 Run 的 machine `root`。
4. 不要做 A3，除非愿意给 DSH 的 JSON-RPC server 加 `tool/execute`。
5. sandbox plane 继续走 LCA 自己的 `SandboxComputer`，DSH 不进沙箱。

---

## 10. 产品形态：输入栏「用 DSH」，整题转发，事件灌回 LobeHub

这比拆细工具桥更对。要对比的是 **两个 agent**，不是两个 `bash` 实现。

### 10.1 它不是第三种 plane

`用电脑` / `云沙箱` 回答的是「操作哪块磁盘」。  
`用 DSH` 回答的是「这一轮谁当 agent」。

不要把 `dsh` 塞进 `ExecutionTarget` 当 `sandbox|device` 的兄弟去绑 `PlaneBindings`。plane 仍可以是 machine（给 DSH 的 `cwd`）。driver 换成 DSH 之后，LCA 的 `Agent`/`Team` 本轮不跑。

```
LobeHub chip:  用电脑 | 云沙箱 | 用 DSH | 自动
                    │
                    │ POST /runs  execution_target=dsh
                    ▼
gateway/runs/execute.py
    target != dsh  →  现有 assemble + Agent/Team
    target == dsh  →  DshRunDriver（跳过 layer1/2）
                    │
                    │ DeepSeekHarness.run(prompt, on_notification=…)
                    ▼
DSH session.event  ──投影──►  Journal record()
                    │
                    │ GET /runs/{id}/live   （现成 SSE）
                    ▼
LcaRunDriver + lcaJournal  （现成卡片）
```

前端几乎不用新渲染器。`LcaRunDriver` 已经会把 `ReasoningDelta` / `StepTextDelta` / `ToolStarted` / `ToolInvoked` 画成思考块、正文和 LobeHub 工具卡。

### 10.2 前端改哪里

现成入口是 `HeteroDeviceSwitcher`（patch：`deploy/lobehub/patches/ui/execution_target.py`）。再加一行 OptionRow，文案「用 DSH」。

`LcaRunDriver.planeFieldsFromAgent` 今天只认 `local|device|sandbox|auto|none`。加：

```ts
if (target === 'dsh') return { plane: 'machine', execution_target: 'dsh' };
```

`POST /runs` 已经透传 `execution_target`（`gateway/runs/api.py`）。gateway 在 `execute` 开头分流即可。

不要新开一条 `/dsh/live`。同一条 Run Live 才能和 LCA 跑在同一套 UI 账本上。

### 10.3 DSH 事件怎么灌

SDK 的 `on_notification` 已经是流。把 `session.event` 投影成现有 Journal 类型，**不要**让前端认识 DSH 的 `assistant/chunk`。

| DSH | Journal | LobeHub |
|---|---|---|
| `assistant/chunk` reasoning-delta | `ReasoningDelta` | 思考块 |
| `assistant/chunk` text-delta | `StepTextDelta` | 正文流 |
| `tool/call` | `ToolStarted` + `plugin_state` | 工具卡开始 |
| `tool/result` | `ToolInvoked` + `plugin_state` | 工具卡结果 |
| `turn/end` | `AgentRunFinished` | 收轮 |

工具名对齐现成 `WIRE`，卡片才能亮：

| DSH 工具 | 投到 |
|---|---|
| `bash` | `local_runCommand` → `lobe-local-system` / `runCommand` |
| `read` | `local_readFile` |
| `write` | `local_writeFile` |
| `edit` | `local_editFile` |
| `todo_write` / `subagent` / `skill` | 先通用卡，或只在正文里呈现 |

`plugin_state` 尽量填 LobeHub Inspector 认识的字段（`command`、`stdout`、`exitCode`），不要塞 DSH 原 JSON。

### 10.4 「用 DSH 事件做比较」——对，但分两层

DSH 的 session log 比 LCA Journal 更适合当 **agent 行为对照表**：

- 一条原则：进模型的东西必须能从 log 重建
- turn / step 边界清楚
- chunk 可 replay
- `tool/call` 与 `tool/result` 成对
- 请求头（provider、model、tools、system）落在 `request/header`

所以比较 **效果和事件质量** 时，应以 **DSH 原 log** 对 **LCA Journal 原 log**，不要拿「投影后的假 Journal」去跟 LCA 比事件设计。投影层会丢掉 DSH 的 seq、request header、chunk 时序。

两层并存：

| 层 | 给谁 | 存什么 |
|---|---|---|
| 投影 Journal | LobeHub 同一条 SSE / 同一套卡片 | 只够把这一轮画出来 |
| 原始 DSH JSONL | 对比、复盘、写报告 | `session_root` 里 DSH 自己的文件，原样留 |

对比方式先做最笨的：同一句话发两次，chip 一次 LCA、一次 DSH，两个话题并排看。不要第一期做双栏同屏双 Run，UI 成本远大于信号。

### 10.5 不要做的

- 不要把 DSH 收成 LCA 的一个 `Tool`（双 loop，比不出 agent）。
- 不要让 DSH 事件直接进浏览器（LobeHub 不认 `assistant/chunk`）。
- 不要为了对比新写一套 DSH 前端。
- 不要改 `PlaneKind`。driver ≠ 磁盘。
- 不要默认双开。一次 Run 一个 driver，对照靠两次发送。

### 10.6 落地顺序

1. `DshRunDriver`：gateway 在 `execution_target=dsh` 时启动/复用 SDK，订阅 notification，投影 Journal，原始 JSONL 落到 Run 目录。
2. `WIRE` + `plugin_state` 映射，先打通 `bash` / `read` / `write` / `edit`。
3. 输入栏加「用 DSH」，`planeFieldsFromAgent` 带上 `execution_target=dsh`。
4. 有额度后同一 prompt 跑两轮，对照卡片、正文、原始 log。
