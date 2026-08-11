# Sandbox 文件传输架构对齐设计

**日期**: 2026-08-10
**状态**: Draft
**触发**: `run_skill_script` 对 xlsx skill 报 `docker create failed: argument list too long`

---

## 1. 根因

LCA 的 `build_wrapped_code()` 和 `build_session_wrapped_code()` 把所有挂载文件
（附件 + skill 资源）base64 编码后**内联到 Python 源码字符串**里：

```python
_LCA_MOUNTS = [("schemas/ISO-IEC29500-4_2016/sml.xsd", "base64data..."), ...]
```

这个巨大字符串（xlsx skill = 1.41 MB）作为 `code` 字段经 HTTP POST 发给 Onlyboxes
console，console 内部传给 docker 时超过 `ARG_MAX`。

**本质问题**: 文件传输和代码执行耦合在一个字符串里。

## 2. LobeHub 原生做法（参照系）

LobeHub 的 `OnlyboxesSandboxProvider`（902 行）+ `SandboxMiddlewareService` 用完全不同的架构：

### 2.1 执行通道

| 操作 | 端点 | 机制 |
|------|------|------|
| 一切操作 | `POST /api/v1/commands/terminal` | 带 `session_id` + `create_if_missing: true` |
| 写文件 | 同上 | 分块 base64 → `appendWriteFileChunkScript`（48KB/chunk） |
| 执行代码 | 同上 | 先 `writeTextFile` 到 `/tmp/*.py`，再 `python3 /tmp/*.py` |
| Shell 命令 | 同上 | 直接传 command |
| Skill 资源 | 同上 | `curl <zipUrl> -o skill.zip && unzip -q` |

### 2.2 文件暂存（关键发现）

LobeHub 用 **presigned URL + curl** 把用户文件下载到沙箱，不用 base64 传输：

```bash
# buildSandboxFilesInitCommand() 生成的 bootstrap 命令
mkdir -p '/mnt/data'; if [ ! -f '/mnt/data/.lobe-files-initialized' ]; then
  curl -fsSL '<presigned_url_1>' -o '/mnt/data/file1.csv' || true;
  curl -fsSL '<presigned_url_2>' -o '/mnt/data/file2.xlsx' || true;
  touch '/mnt/data/.lobe-files-initialized';
fi
```

- 触发时机：第一次 `callTool()` 时 lazy init（`ensureFilesInitialized()`）
- 幂等性：沙箱内 marker 文件 `/mnt/data/.lobe-files-initialized` 控制
- Session 回收后 marker 消失 → 下次自动重新同步

### 2.3 Skill 资源（关键发现）

Skill 资源用 **presigned ZIP URL + curl + unzip**，也不内联：

```bash
# buildSkillSetupCommand() 生成
if [ ! -f .prepared ]; then
  rm -rf dir && mkdir -p dir &&
  curl -fsSL <zipUrl> -o skill.zip &&
  unzip -q skill.zip -d dir &&
  printf prepared > .prepared;
fi
```

- 工作目录：`/tmp/lobe-skills/{sha256(skill_set)}/` — 内容寻址
- 幂等性：每个 skill 目录下的 `.prepared` marker

### 2.4 设计原则

1. **唯一执行通道 = `terminalExec`** — 不用 `pythonExec`，无 ARG_MAX 风险
2. **文件先写后执行** — 代码和文件分别传输
3. **代码写到文件再执行** — 不经过 `-c` 参数
4. **Session 持久化** — 同一 session 内文件系统跨调用存活
5. **幂等 marker 文件** — 沙箱内 marker 是唯一真相源，不依赖外部缓存
6. **URL 优先于 chunk** — 能 curl 下载就不 base64 分块

## 3. 设计方案

### 3.1 核心原则

**代码是代码，文件是文件，两个通道分开传。**

```
当前（错误）:  code + files → build_wrapped_code() → 巨大字符串 → 一次 POST
正确（对齐）:  files → writeFilesToDisk() → 分块写到沙箱磁盘
               code → executeCode() → 只传代码逻辑（无文件数据）
```

### 3.2 Sandbox Protocol 变更

```python
class Sandbox(Protocol):
    # ── 文件传输（新增） ──
    async def write_files(
        self,
        files: dict[str, bytes],
        *,
        base_dir: str = "/mnt/data",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        """分块写文件到沙箱磁盘。返回成功/失败。"""
        ...

    # ── 代码执行（简化） ──
    async def run(
        self,
        code: str,
        language: str = "python",
        # 删除: files: dict[str, bytes] | None = None,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult: ...

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        # 删除: files 参数（文件已通过 write_files 预置）
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult: ...

    # ── Session 管理（不变） ──
    async def create_session(...) -> SessionInfo | None: ...
    async def destroy_session(...) -> None: ...
```

**Breaking change**: `run()` 和 `run_in_session()` 移除 `files` 参数。
调用方（`RunBoundSandboxRuntime`）改为先 `write_files()` 再 `run()`。

### 3.3 OnlyboxesSandboxAdapter 改造

#### 3.3.1 统一执行通道：`_exec_terminal()`

所有操作（文件写入、代码执行、shell 命令）统一走 `terminalExec`：

```python
async def _exec_terminal(
    self,
    command: str,
    *,
    session_id: str = "",
    timeout_s: int = 60,
    invocation_id: str = "",
) -> TerminalResult:
    """统一终端执行通道 — 对齐 LobeHub execTerminal。"""
    body = {
        "command": command,
        "create_if_missing": True,
        "lease_ttl_sec": self._lease_ttl_sec,
        "session_id": session_id or self._default_session_id,
        "timeout_ms": timeout_ms(timeout_s),
    }
    resp = await self._client.post(
        f"{self._base_url}/api/v1/commands/terminal",
        headers=self._auth_headers(),
        json=body,
    )
    return TerminalResult.from_response(resp, invocation_id)
```

#### 3.3.2 文件暂存：`write_files()` — 两种策略

对齐 LobeHub 的 "URL 优先、chunk 兜底" 策略：

**策略 A — presigned URL + curl（用户附件，优先）**

LCA 的 `FileStore` 生成临时下载 URL，沙箱内 curl 下载。
对齐 LobeHub `buildSandboxFilesInitCommand()` 模式：

```python
async def write_files(self, files, *, base_dir, session_id, timeout_s):
    """files 可以是 dict[str, bytes] 或 dict[str, str]（URL）。"""
    curl_cmds = []
    chunk_files = []

    for name, source in files.items():
        path = f"{base_dir}/{safe_rel_name(name)}"
        if isinstance(source, str) and source.startswith(("http://", "https://")):
            # 策略 A: URL → curl 下载（零数据传输经过 LCA）
            curl_cmds.append(f"curl -fsSL '{source}' -o '{path}'")
        else:
            chunk_files.append((name, source, path))

    # 批量 curl 命令（一个 terminal 调用下载所有 URL 文件）
    if curl_cmds:
        marker = f"{base_dir}/.lca-files-initialized"
        cmd = (
            f"mkdir -p '{base_dir}'; "
            f"if [ ! -f '{marker}' ]; then " + " && ".join(curl_cmds) + f" && touch '{marker}'; fi"
        )
        await self._exec_terminal(cmd, session_id=session_id, timeout_s=timeout_s)

    # 策略 B: 分块 base64 写入（skill 资源等无 URL 的文件）
    for name, data, path in chunk_files:
        await self._write_file_chunked(data, path, session_id)

    return SandboxResult(success=True, exit_code=0)
```

**策略 B — 48KB 分块 base64（skill 资源，兜底）**

对齐 LobeHub `writeTextFile()` — 用于没有 URL 的文件（skill 包资源）：

```python
WRITE_CHUNK_BYTES = 48 * 1024  # 对齐 LobeHub WRITE_FILE_CHUNK_BYTES


async def _write_file_chunked(self, data: bytes, path: str, session_id: str):
    await self._exec_terminal(
        f"mkdir -p $(dirname '{path}') && : > '{path}'",
        session_id=session_id,
    )
    for offset in range(0, len(data), WRITE_CHUNK_BYTES):
        chunk = base64.b64encode(data[offset : offset + WRITE_CHUNK_BYTES]).decode("ascii")
        await self._exec_terminal(
            f"printf '%s' '{chunk}' | base64 -d >> '{path}'",
            session_id=session_id,
        )
```

**为什么两种策略**：
- 用户附件（50类型.xlsx 等）存在 `FileStore` 里，可以生成 presigned URL → curl 最快
- Skill 资源（52 个 ISO schema 文件）在本地磁盘，没有 URL → 分块写入
- 对齐 LobeHub：用户文件用 presigned URL，skill 用 ZIP URL，都是 "URL 优先"

#### 3.3.3 代码执行：`run()` / `run_in_session()`

代码写到临时文件再执行，不经过 `-c` 参数：

```python
async def run(self, code, language="python", timeout_s=60, **kwargs):
    invocation_id = str(kwargs.get("invocation_id", "") or "")
    ext = {"python": "py", "javascript": "js", "typescript": "ts"}[language]
    runner = {"python": "python3", "javascript": "node", "typescript": "npx --yes tsx"}[language]

    code_path = f"/tmp/lca-{new_id('code')}.{ext}"

    # 1. 写代码到文件
    await self._write_text_file(code, code_path, session_id="")
    # 2. 执行文件
    result = await self._exec_terminal(
        f"{runner} '{code_path}'",
        timeout_s=timeout_s,
        invocation_id=invocation_id,
    )
    return result.to_sandbox_result()
```

#### 3.3.4 Session 创建：轻量

Session 创建不再传文件 — 只创建容器：

```python
async def create_session(self, config=None):
    # 只发一个 no-op 命令触发容器创建（对齐 LobeHub ensureSession）
    result = await self._exec_terminal(":", timeout_s=30)
    return SessionInfo(session_id=result.session_id)
```

### 3.4 Bootstrap 简化

**删除** `build_wrapped_code()` 和 `build_session_wrapped_code()` 中的文件内联逻辑。

新的 bootstrap 只做三件事：
1. 设置环境变量
2. 执行用户代码
3. 收集产出物

```python
def build_minimal_bootstrap(code: str) -> str:
    """极简 bootstrap — 无文件挂载（文件已在磁盘上）。"""
    env_preamble = build_sandbox_env_preamble()
    code_literal = json.dumps(code)
    return f"""
import os, json, sys
{env_preamble}
_ns = {{"__name__": "__main__"}}
try:
    exec(compile({code_literal}, "<lca-user>", "exec"), _ns)
except SystemExit as _se:
    if _se.code not in (0, None):
        raise
"""
```

对比当前 80+ 行的 `build_wrapped_code()`（含文件挂载 + numpy patch + harvest），
新 bootstrap 只有 ~15 行。产出物收集移到执行后的独立步骤。

### 3.5 RunBoundSandboxRuntime 适配

`_execute_raw()` 改为两阶段：

```python
async def _execute_raw(self, code, *, language, timeout_s, invocation_id, extra_files):
    # Phase 1: 文件暂存（如果有新文件）
    all_files = {**self._mount_files, **(extra_files or {})}
    if all_files and not self._files_staged:
        await self._sandbox.write_files(
            all_files,
            base_dir="/mnt/data",
            session_id=self._session.session_id if self._session else "",
        )
        self._files_staged = True

    # Phase 2: 代码执行（无文件参数）
    if self._session:
        return await self._sandbox.run_in_session(
            self._session.session_id,
            code,
            language,
            timeout_s,
            invocation_id=invocation_id,
        )
    return await self._sandbox.run(
        code,
        language,
        timeout_s,
        invocation_id=invocation_id,
    )
```

`_files_staged` 标记确保文件只写一次（session 内幂等）。

### 3.6 Skill 资源处理

**当前**: `skill_mount_files()` 把所有资源文件作为 `extra_files` 传给 runtime，
runtime 内联到代码里。

**新方案**: 对齐 LobeHub 的 skill 暂存模式 — 内容寻址 + 幂等 marker：

```
/mnt/data/_skills/{skill_id}/        ← skill 工作目录
/mnt/data/_skills/{skill_id}/.prepared  ← 幂等 marker
```

- `SkillExecTool` 调用 `write_files()` 暂存资源到 `/mnt/data/_skills/{skill_id}/`
- `build_skill_exec_code()` 生成的命令 `cd` 到该目录后执行
- 幂等性：`.prepared` marker 确保同一 session 内不重复写入
- 对 `SkillExecTool` 接口不变 — 仍传 `extra_files=mounts`

xlsx skill 的 52 个文件（1069 KB）首次分块写入约 23 个 chunk 请求，
后续执行跳过（`.prepared` marker 存在）。

**未来演进**: 如果 skill 包可以打包为 ZIP 并托管到可下载 URL，
可以进一步对齐 LobeHub 的 `curl + unzip` 模式，零 chunk 开销。

### 3.7 向后兼容

| 组件 | 影响 | 迁移 |
|------|------|------|
| `Sandbox` Protocol | `files` 参数移除 | 调用方改为先 `write_files` |
| `SandboxRuntime` Protocol | 不变 | 内部实现改 |
| `OnlyboxesSandboxAdapter` | 重写执行通道 | `pythonExec` → `terminalExec` |
| `build_wrapped_code()` | 删除 | 替换为 `build_minimal_bootstrap()` |
| `build_session_wrapped_code()` | 删除 | 同上 |
| `onlyboxes_session.py` | 重写 | 不再需要独立的 session HTTP 模块 |
| `SkillExecTool` | 不变 | 传 `extra_files` 不变 |
| `SandboxCodeTool` | 不变 | 传 `files` via runtime |

## 4. 性能对比

| 场景 | 当前 | 新方案 |
|------|------|--------|
| xlsx skill (52 files, 1069 KB) | ❌ ARG_MAX 崩溃 | ✅ 首次 ~23 chunk，后续 0（marker 跳过） |
| 用户附件 (11 KB xlsx) | ❌ 内联到 1.41 MB 代码 | ✅ 1 次 curl 下载（presigned URL） |
| 简单代码 (无文件) | 1 POST pythonExec | 1 write + 1 exec terminal |
| Session 内多次执行 | 每次都内联文件 | 文件写一次，后续执行零文件开销 |
| 大附件 (10 MB CSV) | ❌ 内联后 ~14 MB 代码 | ✅ 1 次 curl（URL）或 ~210 chunk（兜底） |

## 5. 端点选择

LobeHub 用 `POST /api/v1/commands/terminal`（带 `session_id`），LCA 当前用
`POST /api/v1/tasks` + `capability: terminalExec`（无 session）。

**决策**: 优先使用 LobeHub 同款端点 `/api/v1/commands/terminal`（已验证支持 session 持久化）。
如果 Onlyboxes console 版本不支持此端点，回退到 `POST /api/v1/tasks` + `terminalExec` +
`session_id` 扩展字段（需 console 侧配合）。

实施前验证：`curl POST /api/v1/commands/terminal` 确认可用。

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Onlyboxes console 不支持 `/api/v1/commands/terminal` | 回退到 `POST /api/v1/tasks` + `terminalExec` + `session_id` 扩展 |
| 分块写入增加 HTTP 往返次数 | Session 内复用持久连接；48KB chunk 对齐 LobeHub 生产验证值 |
| `terminalExec` 输出格式与 `pythonExec` 不同 | 统一 `TerminalResult` 解析层，输出格式归一化 |
| 现有测试依赖 `build_wrapped_code` | 测试改为验证 `write_files` + `run` 的两阶段行为 |
| Shell 注入（路径含特殊字符） | `safe_rel_name()` 已净化为 basename；shell 命令中路径用单引号包裹 + 转义 |
| `_files_staged` 标记粒度 | 改为 set 跟踪已暂存的 file key，支持增量暂存 |

## 7. 不在范围内

- Onlyboxes console 内部实现（假设已支持 `terminalExec` 端点）
- LobeHub 前端 patch（已对齐，不需要改）
- SSE 事件格式（已对齐，不需要改）
- StepTextDelta 双 channel 问题（独立问题，不在此设计范围）

## 8. 受影响文件清单

| 文件 | 操作 |
|------|------|
| `lca/contracts/protocols/infra.py` | 修改 Sandbox Protocol |
| `lca/layer0_infra/sandbox/onlyboxes_adapter.py` | 重写（terminalExec 统一通道） |
| `lca/layer0_infra/sandbox/onlyboxes_bootstrap.py` | 简化（删除文件内联） |
| `lca/layer0_infra/sandbox/onlyboxes_session.py` | 删除或大幅简化 |
| `lca/layer0_infra/sandbox/onlyboxes_session_bootstrap.py` | 删除（合并到 bootstrap） |
| `lca/layer0_infra/sandbox/runtime.py` | 修改 `_execute_raw` 两阶段 |
| `lca/layer0_infra/sandbox/runtime_mount.py` | 不变 |
| `lca/layer0_infra/tools/skills/exec_tool.py` | 不变 |
| `lca/layer0_infra/skills/exec_bootstrap.py` | 简化（`build_skill_exec_code` 不再需要 mount 逻辑） |
| `tests/` | 更新测试 |
