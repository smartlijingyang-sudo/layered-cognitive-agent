# Sandbox 架构对齐 + SSE 去重 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 sandbox 文件内联导致的 ARG_MAX 崩溃，修复 SSE StepTextDelta 双 channel 文本重复。

**Architecture:** 对齐 LobeHub 原生模式 — 统一 `terminalExec` 执行通道，文件分块写磁盘（或 curl 下载），代码写到 `/tmp/*.py` 再执行。SSE projector 过滤 `decision` channel 的 StepTextDelta。

**Tech Stack:** Python 3.12+, httpx, Onlyboxes console API, LCA 5-layer architecture

**Spec:** `docs/superpowers/specs/2026-08-10-sandbox-file-staging-alignment-design.md`

## Global Constraints

- 五层单向依赖：contracts → layer0 → layer1 → layer2 → layer4，不可反向 import
- `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest` 必须全绿
- 公共函数/类必须有类型标注
- 禁止硬编码 API Key / Token

---

### Task 1: SSE StepTextDelta 去重

**Files:**
- Modify: `lca/layer0_infra/observability/journal/sse_projector.py`
- Test: `tests/test_sse_journal_projector.py`

**Interfaces:**
- Consumes: `StepTextDelta` (from `contracts.models.observability.journal`), `StreamChannel` (from `contracts.atoms.enums`)
- Produces: `SSEJournalProjector.on_event()` 过滤 `channel=decision` 的 StepTextDelta

- [ ] **Step 1: 写失败测试**

在 `tests/test_sse_journal_projector.py` 添加：

```python
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import StepTextDelta


class TestSseProjectorStepTextDeltaFilter(unittest.TestCase):
    def test_decision_channel_filtered(self) -> None:
        """decision channel 的 StepTextDelta 不应出现在 SSE 输出中。"""
        received: list[str | None] = []
        projector = SSEJournalProjector(received.append)
        scope = RunScope(trace_id="t", run_id="r")

        # decision channel — 应被过滤
        projector.on_event(
            StampedEvent(
                seq=1,
                ts=1.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="raw token", seq=0, channel=StreamChannel.DECISION.value
                ),
            )
        )
        # answer channel — 应通过
        projector.on_event(
            StampedEvent(
                seq=2,
                ts=2.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="visible text", seq=1, channel=StreamChannel.ANSWER.value
                ),
            )
        )

        # 只有 answer channel 的帧（+ close 的 None）
        non_none = [f for f in received if f is not None]
        self.assertEqual(len(non_none), 1)
        self.assertIn("visible text", non_none[0])
        self.assertNotIn("raw token", non_none[0])

    def test_answer_channel_passes_through(self) -> None:
        """answer channel 的 StepTextDelta 正常通过。"""
        received: list[str | None] = []
        projector = SSEJournalProjector(received.append)
        scope = RunScope(trace_id="t", run_id="r")
        projector.on_event(
            StampedEvent(
                seq=1,
                ts=1.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="hello", seq=0, channel=StreamChannel.ANSWER.value
                ),
            )
        )
        non_none = [f for f in received if f is not None]
        self.assertEqual(len(non_none), 1)
        self.assertIn("hello", non_none[0])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_sse_journal_projector.py::TestSseProjectorStepTextDeltaFilter -v`
Expected: FAIL — `test_decision_channel_filtered` 断言 `len(non_none) == 1` 但实际为 2

- [ ] **Step 3: 实现过滤逻辑**

修改 `lca/layer0_infra/observability/journal/sse_projector.py`：

```python
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import RunInsight, StampedEvent, StepTextDelta


class SSEJournalProjector(JournalProjector):
    def on_event(self, stamped: StampedEvent) -> None:
        if isinstance(stamped.event, RunInsight):
            with contextlib.suppress(Exception):
                self._emit(stamped_to_sse_frame(stamped))
            return
        # 过滤 decision channel 的 StepTextDelta — 只转发 answer channel
        if (
            isinstance(stamped.event, StepTextDelta)
            and stamped.event.channel == StreamChannel.DECISION.value
        ):
            return
        self._emit(stamped_to_sse_frame(stamped))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_sse_journal_projector.py -v`
Expected: ALL PASS

- [ ] **Step 5: 运行全量检查**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run mypy lca && uv run pytest`
Expected: ALL GREEN

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/observability/journal/sse_projector.py tests/test_sse_journal_projector.py
git commit -m "fix(observability): filter decision-channel StepTextDelta from SSE projector

The journal records both decision (raw LLM tokens) and answer (extracted
user-visible text) channels. SSE consumers were receiving both, causing
text duplication. Only forward answer channel — decision channel remains
in journal/jsonl for debugging."
```

---

### Task 2: Sandbox Protocol — 新增 `write_files`

**Files:**
- Modify: `lca/contracts/protocols/infra.py`
- Modify: `tests/support/inline_sandbox.py`

**Interfaces:**
- Consumes: `SandboxResult`, `SessionConfig`, `SessionInfo` (from `contracts.models.core.sandbox`)
- Produces: `Sandbox.write_files()` 方法签名 — 后续 Task 3/4/5 依赖

- [ ] **Step 1: 修改 Sandbox Protocol**

在 `lca/contracts/protocols/infra.py` 的 `Sandbox` Protocol 中新增 `write_files`：

```python
from lca.contracts.models.core.sandbox import SandboxResult, SessionConfig, SessionInfo


class Sandbox(Protocol):
    async def write_files(
        self,
        files: dict[str, bytes | str],
        # str = presigned URL (curl 下载), bytes = 二进制内容 (分块写入)
        *,
        base_dir: str = "/mnt/data",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        """写文件到沙箱磁盘。str 值走 curl 下载，bytes 值走分块写入。"""
        ...

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult: ...

    # 注意: files 参数已移除

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None: ...
    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult: ...
    async def destroy_session(self, session_id: str) -> None: ...
```

- [ ] **Step 2: 更新 InlineSandbox 测试桩**

修改 `tests/support/inline_sandbox.py`：

```python
class InlineSandbox:
    def __init__(self, *, session_ok: bool = True) -> None:
        self.session_ok = session_ok
        self.run_calls: list[str] = []
        self.session_run_calls: list[tuple[str, str]] = []
        self.created_sessions: list[str] = []
        self.destroyed_sessions: list[str] = []
        self.write_files_calls: list[dict[str, bytes]] = []  # 新增
        self._counter = 0
        self._sessions: dict[str, dict[str, bytes]] = {}

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "/mnt/data",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> SandboxResult:
        self.write_files_calls.append(files)
        # 写入 VFS（只处理 bytes，URL 在测试中不实际下载）
        if session_id and session_id in self._sessions:
            vfs = self._sessions[session_id]
        else:
            vfs = {}
        for name, source in files.items():
            from lca.layer0_infra.sandbox.onlyboxes_bootstrap import safe_rel_name

            if isinstance(source, bytes):
                vfs[f"{base_dir}/{safe_rel_name(name)}"] = source
        if session_id:
            self._sessions.setdefault(session_id, {}).update(vfs)
        return SandboxResult(success=True, exit_code=0)

    async def run(self, code, language="python", timeout_s=60, **kwargs):
        # 移除 files 参数
        del language, timeout_s
        self.run_calls.append(code)
        return self._exec(code, {}, str(kwargs.get("invocation_id", "") or ""))

    async def create_session(self, config=None):
        if not self.session_ok:
            return None
        self._counter += 1
        sid = f"sess_{self._counter}"
        self.created_sessions.append(sid)
        self._sessions[sid] = {}  # 不再从 config 接收 files
        return SessionInfo(session_id=sid, container_id=f"ctr_{sid}")

    async def run_in_session(self, session_id, code, language="python", timeout_s=60, **kwargs):
        del language, timeout_s
        self.session_run_calls.append((session_id, code))
        vfs = self._sessions.setdefault(session_id, {})
        # files 不再通过 kwargs 传入 — 已通过 write_files 预置
        return self._exec(code, vfs, str(kwargs.get("invocation_id", "") or ""))
```

- [ ] **Step 3: 运行测试确认 InlineSandbox 仍可用**

Run: `uv run pytest tests/test_sandbox_runtime.py -v`
Expected: FAIL — `RunBoundSandboxRuntime` 仍传 `files` 给 `run()`/`run_in_session()`，在 Task 5 修复

- [ ] **Step 4: Commit**

```bash
git add lca/contracts/protocols/infra.py tests/support/inline_sandbox.py
git commit -m "feat(sandbox): add write_files to Sandbox Protocol, remove files from run/run_in_session"
```

---

### Task 3: OnlyboxesSandboxAdapter — 统一 terminalExec 通道 + write_files

**Files:**
- Modify: `lca/layer0_infra/sandbox/onlyboxes_adapter.py`
- Test: `tests/test_onlyboxes_sandbox.py`

**Interfaces:**
- Consumes: `Sandbox.write_files()` Protocol (Task 2)
- Produces: `OnlyboxesSandboxAdapter` 实现 `write_files()` + `_exec_terminal()` + 简化 `run()`/`run_in_session()`

- [ ] **Step 1: 写 `_exec_terminal` 和 `write_files` 的测试**

在 `tests/test_onlyboxes_sandbox.py` 添加（HTTP mock 模式）：

```python
class WriteFilesTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_files_chunks_large_file(self) -> None:
        """大于 48KB 的文件应分块写入。"""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")
        calls: list[dict] = []

        async def mock_post(url, **kwargs):
            calls.append({"url": url, "body": kwargs.get("json", {})})
            resp = MagicMock()
            resp.status_code = 200
            resp.text = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""})
            resp.ok = True
            return resp

        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(side_effect=mock_post)

        data = b"x" * (48 * 1024 + 1000)  # 略大于一个 chunk
        result = await adapter.write_files({"big.bin": data}, base_dir="/mnt/data")

        self.assertTrue(result.success)
        # 至少 2 次 terminal 调用（mkdir + 至少 2 chunk）
        self.assertGreaterEqual(len(calls), 2)
        # 所有请求都走 /api/v1/commands/terminal
        for call in calls:
            self.assertIn("/api/v1/commands/terminal", call["url"])

    async def test_write_files_url_uses_curl(self) -> None:
        """URL 类型的文件应生成 curl 命令。"""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")
        calls: list[dict] = []

        async def mock_post(url, **kwargs):
            calls.append({"url": url, "body": kwargs.get("json", {})})
            resp = MagicMock()
            resp.status_code = 200
            resp.text = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""})
            resp.ok = True
            return resp

        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(side_effect=mock_post)

        result = await adapter.write_files(
            {"data.csv": "https://example.com/data.csv"},
            base_dir="/mnt/data",
        )

        self.assertTrue(result.success)
        # 应有一个 curl 命令
        curl_calls = [c for c in calls if "curl" in c["body"].get("command", "")]
        self.assertEqual(len(curl_calls), 1)
        self.assertIn("https://example.com/data.csv", curl_calls[0]["body"]["command"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py::WriteFilesTests -v`
Expected: FAIL — `write_files` 方法不存在

- [ ] **Step 3: 实现 `_exec_terminal` + `write_files` + 简化 `run`/`run_in_session`**

重写 `lca/layer0_infra/sandbox/onlyboxes_adapter.py`。核心变更：

```python
WRITE_CHUNK_BYTES = 48 * 1024


class OnlyboxesSandboxAdapter(Sandbox):
    # ... __init__ 不变 ...

    async def _exec_terminal(
        self,
        command: str,
        *,
        session_id: str = "",
        timeout_s: int = 60,
        invocation_id: str = "",
    ) -> SandboxResult:
        """统一终端执行通道 — 对齐 LobeHub execTerminal。"""
        emitter = SandboxStreamEmitter(invocation_id)
        t_ms = timeout_ms(timeout_s)
        body = {
            "command": command,
            "create_if_missing": True,
            "lease_ttl_sec": self._lease_ttl_sec,
            "session_id": session_id,
            "timeout_ms": t_ms,
        }
        # HTTP POST /api/v1/commands/terminal
        ...
        return parsed_result

    async def write_files(self, files, *, base_dir="/mnt/data", session_id="", timeout_s=60):
        curl_cmds = []
        chunk_files = []
        for name, source in files.items():
            path = f"{base_dir}/{safe_rel_name(name)}"
            if isinstance(source, str) and source.startswith(("http://", "https://")):
                curl_cmds.append(f"curl -fsSL '{source}' -o '{path}'")
            else:
                chunk_files.append(
                    (name, source if isinstance(source, bytes) else source.encode(), path)
                )

        if curl_cmds:
            marker = f"{base_dir}/.lca-files-initialized"
            cmd = (
                f"mkdir -p '{base_dir}'; if [ ! -f '{marker}' ]; then "
                + " && ".join(curl_cmds)
                + f" && touch '{marker}'; fi"
            )
            await self._exec_terminal(cmd, session_id=session_id, timeout_s=timeout_s)

        for _name, data, path in chunk_files:
            await self._write_file_chunked(data, path, session_id)

        return SandboxResult(success=True, exit_code=0)

    async def _write_file_chunked(self, data: bytes, path: str, session_id: str):
        await self._exec_terminal(
            f"mkdir -p \"$(dirname '{path}')\" && : > '{path}'", session_id=session_id
        )
        for offset in range(0, len(data), WRITE_CHUNK_BYTES):
            chunk = base64.b64encode(data[offset : offset + WRITE_CHUNK_BYTES]).decode("ascii")
            await self._exec_terminal(
                f"printf '%s' '{chunk}' | base64 -d >> '{path}'", session_id=session_id
            )

    async def run(self, code, language="python", timeout_s=60, **kwargs):
        # 写代码到临时文件再执行
        ext = {"python": "py", "javascript": "js", "typescript": "ts"}.get(language, "py")
        runner = {"python": "python3", "javascript": "node", "typescript": "npx --yes tsx"}.get(
            language, "python3"
        )
        code_path = f"/tmp/lca-code-{new_id('code')}.{ext}"
        await self._write_text_file(code, code_path, session_id="")
        return await self._exec_terminal(
            f"{runner} '{code_path}'",
            timeout_s=timeout_s,
            invocation_id=str(kwargs.get("invocation_id", "") or ""),
        )

    async def run_in_session(self, session_id, code, language="python", timeout_s=60, **kwargs):
        ext = {"python": "py", "javascript": "js", "typescript": "ts"}.get(language, "py")
        runner = {"python": "python3", "javascript": "node", "typescript": "npx --yes tsx"}.get(
            language, "python3"
        )
        code_path = f"/tmp/lca-code-{new_id('code')}.{ext}"
        await self._write_text_file(code, code_path, session_id=session_id)
        return await self._exec_terminal(
            f"{runner} '{code_path}'",
            session_id=session_id,
            timeout_s=timeout_s,
            invocation_id=str(kwargs.get("invocation_id", "") or ""),
        )

    async def create_session(self, config=None):
        # 轻量: no-op 命令触发容器创建（对齐 LobeHub ensureSession）
        result = await self._exec_terminal(":", timeout_s=30)
        if result.success:
            return SessionInfo(session_id="terminal-session", container_id="")
        return None

    # run_terminal 保留，内部改走 _exec_terminal
    # destroy_session 保留
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_onlyboxes_sandbox.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add lca/layer0_infra/sandbox/onlyboxes_adapter.py tests/test_onlyboxes_sandbox.py
git commit -m "feat(sandbox): rewrite OnlyboxesAdapter with terminalExec unified channel

- All operations go through POST /api/v1/commands/terminal
- write_files: URL files via curl, binary files via 48KB base64 chunks
- run/run_in_session: write code to /tmp/*.py then execute (no -c arg)
- create_session: lightweight no-op command (LobeHub ensureSession pattern)
- Eliminates ARG_MAX crash from inline base64 file embedding"
```

---

### Task 4: Bootstrap 简化 — 删除文件内联

**Files:**
- Modify: `lca/layer0_infra/sandbox/onlyboxes_bootstrap.py`
- Delete: `lca/layer0_infra/sandbox/onlyboxes_session_bootstrap.py`
- Modify: `lca/layer0_infra/sandbox/onlyboxes_session.py`
- Test: `tests/test_onlyboxes_sandbox.py`

**Interfaces:**
- Consumes: Nothing from previous tasks (independent cleanup)
- Produces: 简化的 bootstrap 函数，无文件内联

- [ ] **Step 1: 简化 `onlyboxes_bootstrap.py`**

删除 `build_wrapped_code()` 中的文件挂载逻辑。保留：
- `build_minimal_bootstrap(code)` — 只做 env patching + exec
- `parse_exec_response()` — 不变
- `safe_rel_name()` — 不变（write_files 仍用）
- 常量（`PYTHON_LANGUAGES`, `CAPABILITY_*` 等）— 不变

```python
def build_minimal_bootstrap(code: str) -> str:
    """极简 bootstrap — 无文件挂载（文件已通过 write_files 预置到磁盘）。"""
    env_preamble = build_sandbox_env_preamble()
    code_literal = json.dumps(_strip_surrogates(code))
    return f"""# --- LCA minimal bootstrap ---
import os as _lca_os, sys as _lca_sys, json as _lca_json
{env_preamble}
# numpy/pandas JSON patch
_lca_original_dumps = _lca_json.dumps
def _lca_numpy_dumps(obj, *args, **kwargs):
    def _numpy_default(o):
        if hasattr(o, "item"): return o.item()
        raise TypeError(f"Object of type {{type(o).__name__}} is not JSON serializable")
    kwargs.setdefault("default", _numpy_default)
    return _lca_original_dumps(obj, *args, **kwargs)
_lca_json.dumps = _lca_numpy_dumps

import warnings as _lca_warnings
_lca_warnings.filterwarnings("ignore", module="matplotlib.font_manager")

try:
    exec(compile({code_literal}, "<lca-user>", "exec"), {{"__name__": "__main__"}})
except SystemExit as _lca_se:
    if _lca_se.code not in (0, None):
        raise
"""
```

- [ ] **Step 2: 删除 `onlyboxes_session_bootstrap.py`**

```bash
rm lca/layer0_infra/sandbox/onlyboxes_session_bootstrap.py
```

- [ ] **Step 3: 简化 `onlyboxes_session.py`**

Session 操作合并到 adapter。`onlyboxes_session.py` 只保留 `http_destroy_session`（DELETE 请求），删除 `http_create_session` 和 `http_run_in_session`（不再需要独立的 session HTTP 端点）。

- [ ] **Step 4: 更新测试**

删除/更新 `test_wrapped_code_embeds_mounts` 等依赖旧 `build_wrapped_code` 的测试。新测试验证 `build_minimal_bootstrap` 不包含文件数据。

- [ ] **Step 5: 运行全量检查**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest`
Expected: ALL GREEN（Task 5 修复 runtime 后）

- [ ] **Step 6: Commit**

```bash
git add -A lca/layer0_infra/sandbox/ tests/test_onlyboxes_sandbox.py
git commit -m "refactor(sandbox): delete file-inlining bootstrap, simplify session module

- build_wrapped_code → build_minimal_bootstrap (no file embedding)
- Delete onlyboxes_session_bootstrap.py (merged into adapter)
- Simplify onlyboxes_session.py (only destroy_session remains)"
```

---

### Task 5: RunBoundSandboxRuntime — 两阶段执行

**Files:**
- Modify: `lca/layer0_infra/sandbox/runtime.py`
- Modify: `lca/layer0_infra/skills/exec_bootstrap.py`
- Test: `tests/test_sandbox_runtime.py`

**Interfaces:**
- Consumes: `Sandbox.write_files()` (Task 2), simplified adapter (Task 3/4)
- Produces: 两阶段执行：先 `write_files` 再 `run`/`run_in_session`

- [ ] **Step 1: 修改 `_execute_raw` 为两阶段**

```python
class RunBoundSandboxRuntime(SandboxRuntime):
    def __init__(self, ...):
        ...
        self._staged_file_keys: set[str] = set()  # 替代 _files_staged bool

    async def _execute_raw(self, code, *, language, timeout_s, invocation_id, extra_files):
        # Phase 1: 文件暂存（增量 — 只写新文件）
        all_files = {**self._mount_files, **(extra_files or {})}
        new_files = {k: v for k, v in all_files.items() if k not in self._staged_file_keys}
        if new_files:
            session_id = self._session.session_id if self._session else ""
            await self._sandbox.write_files(
                new_files, base_dir="/mnt/data", session_id=session_id)
            self._staged_file_keys.update(new_files.keys())

        # Phase 2: 代码执行（无文件参数）
        if self._session is not None and not self._stateless:
            return await self._sandbox.run_in_session(
                self._session.session_id, code, language, timeout_s,
                invocation_id=invocation_id)
        return await self._sandbox.run(
            code, language, timeout_s, invocation_id=invocation_id)
```

- [ ] **Step 2: 简化 `exec_bootstrap.py`**

`build_skill_exec_code()` 不再需要处理文件挂载（文件已在磁盘上）。只保留：
- env preamble
- `os.chdir` 到 skill 目录
- 可选 `pip install -r requirements.txt`
- `subprocess.run(command, shell=True)`

删除 `skill_mount_files()` 函数（不再需要 — 文件由 runtime 的 `write_files` 处理）。

- [ ] **Step 3: 更新 `ensure_ready` — session 创建不再传 files**

```python
async def ensure_ready(self, explicit_ids=None):
    self._mount_files = load_mount_files(self._store, explicit_ids)
    self._manifest = build_mount_manifest(self._store, self._mount_files)

    if self._session is None and not self._stateless:
        try:
            self._session = await self._sandbox.create_session()  # 无 config 参数
        except Exception:
            self._session = None
        if self._session is None:
            self._stateless = True
    ...
```

- [ ] **Step 4: 更新 InlineSandbox 和测试**

确保 `InlineSandbox` 的 `create_session` 不再接收 files。`test_sandbox_runtime.py` 的测试应适配新的两阶段流程。

- [ ] **Step 5: 运行全量检查**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest`
Expected: ALL GREEN

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/sandbox/runtime.py lca/layer0_infra/skills/exec_bootstrap.py tests/
git commit -m "feat(sandbox): two-phase execution — write_files then run

- RunBoundSandboxRuntime stages files via write_files() before execution
- Incremental staging: only new files are written (tracked by _staged_file_keys)
- Simplify build_skill_exec_code: no mount logic, files already on disk
- Session creation no longer passes files"
```

---

### Task 6: 端到端验证 + LobeHub 前端集成确认 + 清理

- [ ] **Step 1: 确认 LobeHub 前端 lca.events 链路生效**

Patch 源码已打（9 个文件），构建产物也包含 `lca_tool_event`。但需确认运行时链路通畅：

```bash
# 1. 重启 LobeHub dev server（确保 patch 后的源码被加载）
cd lobehub-ui && pnpm dev  # 或对应的启动命令

# 2. 发一个会触发工具调用的请求（如 "搜索天气"），观察浏览器 DevTools Network
#    在 SSE 流中查找包含 "lca" 字段的 chunk：
#    data: {"choices":[{"delta":{},"lca":{"v":1,"events":[{"type":"tool_started",...}]}}]}
#
# 3. 确认前端渲染了工具卡片（搜索图标 + 折叠面板）
```

如果 SSE 流中有 `lca.events` 但前端不显示卡片：
- 检查浏览器 Console 是否有 `handleLcaToolEvent` 相关报错
- 检查 `StreamingHandler.ts` 的 `handleLcaToolEvent` 是否被调用（加 console.log 调试）
- 确认 `ClientLLMTransport` 是实际使用的 transport（而非 server-side transport 绕过了 patch）

如果 SSE 流中没有 `lca.events`：
- 检查 `JournalOpenAiProjector._project_tool_started` 是否被调用
- 检查 `merge_lca_extension` 输出是否包含在 SSE chunk 中
- 用 `curl` 直接请求 `/v1/chat/completions` 验证后端输出

- [ ] **Step 2: 验证 Onlyboxes console `/api/v1/commands/terminal` 端点**

```bash
curl -s -X POST http://127.0.0.1:8089/api/v1/commands/terminal \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello", "session_id": "test", "create_if_missing": true, "timeout_ms": 5000}'
```

如果返回 404，回退到 `POST /api/v1/tasks` + `capability: terminalExec` + `session_id` 字段。

- [ ] **Step 2: 运行完整 E2E 测试（如有）**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 3: 运行完整 lint 链**

Run: `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest && uv run vulture lca --min-confidence 80`
Expected: ALL GREEN

- [ ] **Step 4: 最终 commit（如有清理）**

```bash
git add -A
git commit -m "chore(sandbox): cleanup after terminalExec migration"
```
