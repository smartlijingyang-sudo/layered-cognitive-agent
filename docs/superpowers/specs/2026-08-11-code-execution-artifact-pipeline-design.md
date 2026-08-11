# Code Execution Artifact Pipeline — 对齐 LobeHub 原生架构

**日期**: 2026-08-11
**状态**: Approved
**触发问题**: 素数+PDF 场景全链路失败——代码不显示、PDF 看不到

## 问题诊断

### 运行链路 (`run_8fb1139afaf5.jsonl`)

```
Step 0: activate_skill("pdf")           → ✅
Step 1: execute_code(reportlab 生成 PDF) → ❌ ModuleNotFoundError: reportlab
Step 2: run_command("pip install")       → ❌ 超时 60s
Step 3: 重试安装                          → 未完成
```

### 五个断裂点

| # | 问题 | 层级 | 根因 |
|---|------|------|------|
| 1 | Onlyboxes 镜像缺 reportlab | 部署 | 镜像未重新构建 |
| 2 | `parse_terminal_response()` 不调用 `strip_artifacts()` | L0 sandbox | terminal 路径与 exec 路径语义不统一 |
| 3 | `build_computer_observation()` 不处理 `generated_files` | L0 tools | computer tool 的 observation 没有 `extra["files"]` |
| 4 | `execute_code` 不注入 artifact scanner bootstrap | L0 computer | 代码执行不扫描 `/mnt/data/` |
| 5 | PDF 不在 `previewable` MIME 列表 | L0 storage | `_is_previewable()` 缺 `application/pdf` |

### 数据流断裂图

```
execute_code()
  → runtime.execute() → adapter.run() → _exec_terminal()
    → parse_terminal_response()
        ❌ 不调用 strip_artifacts()     ← 断裂点 2
        ❌ generated_files 永远为空
  → ComputerOpResult(exec_result=...)
  → build_computer_observation()
      ❌ 不处理 exec_result.generated_files  ← 断裂点 3
      ❌ Observation 没有 extra["files"]
  → tool_files(obs) → ()  ← 空
  → ToolInvoked.files = ()  ← 前端无文件可显示
```

## 设计原则

1. **自动 harvest** — 代码执行自动捕获所有产物，LLM 零额外调用（对齐 OpenAI Code Interpreter 模型）
2. **统一 harvest 语义** — terminal 路径与 exec 路径都调用 `strip_artifacts()`
3. **文件是一等公民** — `ComputerOpResult` 和 `Observation` 都携带文件元数据
4. **最小侵入** — 5 个变更点，每个都是精确修复，不重构不相关的代码

## 变更清单

### 变更 1: `parse_terminal_response()` — 统一 harvest 语义

**文件**: `lca/layer0_infra/sandbox/onlyboxes_bootstrap.py`

**现状**: `parse_exec_response()` 调用 `strip_artifacts()` 解析产物标记；`parse_terminal_response()` 不调用，terminal 路径的 `generated_files` 永远为空。

**修复**: 在 `parse_terminal_response()` 中调用 `strip_artifacts()`，与 `parse_exec_response()` 对齐。

```python
def parse_terminal_response(response, emitter):
    ...
    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")

    # 新增：与 parse_exec_response 对齐，统一 harvest 产物
    cleaned_stdout, generated, diags = strip_artifacts(stdout)
    if diags:
        stderr = stderr + "".join(diags)

    if cleaned_stdout:
        emitter.emit_stdout(cleaned_stdout)
    if stderr:
        emitter.emit_stderr(stderr)
    ...
    return SandboxResult(
        stdout=cleaned_stdout,           # 改：用 cleaned
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        error=error_text,
        generated_files=tuple(generated), # 新增
    )
```

**影响分析**: `run_command` 也走此路径。但 shell 命令不会输出 `__LCA_ONLYBOXES_ARTIFACTS__` 标记，`strip_artifacts()` 对无标记的 stdout 是安全的 no-op（直接返回原文 + 空列表）。

### 变更 2: `execute_code()` — 注入 artifact scanner bootstrap

**文件**: `lca/layer0_infra/computer/runtime_exec.py`

**现状**: `execute_code()` 直接传用户代码到沙箱，不注入文件扫描器。即使代码生成了文件，也不会被 harvest。

**修复**: 在用户代码后追加 artifact scanner，通过 `try/finally` 保证即使代码异常也能 harvest。

```python
_ARTIFACT_SCANNER = '''
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    for _root, _dirs, _files in _os.walk("/mnt/data"):
        for _fname in _files:
            _fpath = _os.path.join(_root, _fname)
            try:
                _dir_name = _os.path.basename(_root)
                _display = _fname if _dir_name == "data" else _os.path.join(_dir_name, _fname)
                with open(_fpath, "rb") as _fh:
                    _raw = _fh.read()
                _scan_files.append({
                    "name": _display,
                    "b64": _b64.b64encode(_raw).decode(),
                    "mime_type": _mt.guess_type(_fname)[0] or "application/octet-stream",
                })
            except Exception:
                pass
    if _scan_files:
        print("__LCA_ONLYBOXES_ARTIFACTS__" + _json.dumps(_scan_files) + "__END_LCA_ARTIFACTS__")
except Exception:
    pass
'''
```

注入方式：用 `try/finally` 包裹用户代码，保证即使异常也能 harvest：

```python
wrapped = (
    "try:\n"
    + textwrap.indent(code, "    ")
    + "\nfinally:\n"
    + textwrap.indent(_ARTIFACT_SCANNER, "    ")
)
```

由于变更 1 已让 `parse_terminal_response` 调用 `strip_artifacts()`，bootstrap 输出的标记在 adapter 层被自动解析，文件进入 `SandboxResult.generated_files` → `SandboxExecResult.generated_files`。

同时，在 `state` 中加入 `code` 字段（源码始终可见）：

```python
state["code"] = code  # 前端代码显示，无论成功/失败
```

### 变更 3: `ComputerOpResult` + `build_computer_observation()` — 文件传递闭环

**文件 1**: `lca/layer0_infra/computer/runtime.py`

`ComputerOpResult` 新增 `generated_files` 字段：

```python
@dataclass(frozen=True)
class ComputerOpResult:
    success: bool
    content: str
    state: dict[str, Any]
    error: str = ""
    exec_result: SandboxExecResult | None = None
    generated_files: tuple[SandboxFile, ...] = ()  # 新增
```

**文件 2**: `lca/layer0_infra/tools/computer/observations.py`

`build_computer_observation()` 新增文件处理逻辑：

```python
def build_computer_observation(result, *, tool_name, start):
    ...
    extra: dict[str, Any] = {}
    if not result.success:
        extra[FAILURE_KIND] = FAILURE_KIND_EXECUTION

    # 新增：存储生成文件到 FileStore，加入 extra["files"]
    if result.generated_files:
        file_parts = []
        for gen in result.generated_files:
            stored = _store.put(data=gen.data, name=gen.name, mime_type=gen.mime_type)
            file_parts.append({
                "name": stored.name,
                "mimeType": stored.mime_type,
                "sizeBytes": stored.size_bytes,
                "url": stored.url,
                "previewable": stored.previewable,
                "attachmentId": stored.attachment_id,
            })
        extra["files"] = file_parts
    ...
```

需要给 `build_computer_observation` 注入 `FileStore` 引用。当前签名不接收 `store`，需要从 `tool_set.py` 传入：

```python
# tool_set.py — 传入 store
async def execute(_self, args):
    result = await spec.handler(runtime, args)
    return build_computer_observation(result, tool_name=spec.name, start=start, store=store)
```

**闭环验证**: `extra["files"]` → `tool_files(obs)` 提取 → `ToolInvoked.files` → SSE → 前端文件卡片。

### 变更 4: PDF 可预览

**文件**: `lca/layer0_infra/file_store.py`

在 `_is_previewable()` 的 MIME 集合中加入 `application/pdf`：

```python
if mime in {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/pdf",        # 新增
}:
    return True
```

### 变更 5: `execute_code()` 传递 generated_files 到 ComputerOpResult

**文件**: `lca/layer0_infra/computer/runtime_exec.py`

在 `execute_code()` 构建 `ComputerOpResult` 时，从 `exec_result.generated_files` 传递到 `ComputerOpResult.generated_files`：

```python
return ComputerOpResult(
    success=ok,
    content=str(content),
    state=state,
    error=str(state.get("error") or ""),
    exec_result=exec_result,
    generated_files=exec_result.generated_files,  # 新增
)
```

## 修复后数据流

```
execute_code(code)
  → 注入 _ARTIFACT_SCANNER
  → runtime.execute() → adapter → parse_terminal_response()
      → strip_artifacts() ✅ 解析标记
      → SandboxResult.generated_files ✅
  → SandboxExecResult.generated_files ✅ (sandbox_exec_result_from 已传递)
  → ComputerOpResult.generated_files ✅ (变更 5)
  → build_computer_observation()
      → FileStore.put() 存储每个文件 ✅ (变更 3)
      → extra["files"] = [{name, url, mimeType, ...}] ✅
      → state["code"] = source_code ✅ (变更 2)
  → tool_files(obs) → files ✅
  → ToolInvoked.files ✅ → SSE → 前端文件卡片 ✅
```

## 测试策略

### 单元测试

1. **`parse_terminal_response` harvest**: 构造带 `__LCA_ONLYBOXES_ARTIFACTS__` 标记的 JSON 响应 → 验证 `SandboxResult.generated_files` 非空
2. **`parse_terminal_response` no-op**: 构造普通 stdout（无标记）→ 验证 `generated_files` 为空、stdout 不变
3. **`build_computer_observation` 文件传递**: 构造带 `generated_files` 的 `ComputerOpResult` → 验证 `Observation.extra["files"]` 非空
4. **`build_computer_observation` 无文件**: 空 `generated_files` → 验证 `extra` 无 `files` 键

### 集成测试

5. **`execute_code` 生成文件**: 代码写文件到 `/mnt/data/` → 验证 observation 包含文件元数据
6. **`run_command` 不受影响**: 执行普通 shell 命令 → 验证行为不变

### 端到端验证

7. **素数 + PDF 场景复测**: 重新构建镜像后，执行素数程序 + PDF 生成 → 验证文件出现在 ToolInvoked.files

## 不在范围内

- Onlyboxes 镜像重建（运维操作，不在代码变更范围）
- LobeHub Work 注册系统对齐（独立特性，需要 gateway + 前端联动）
- `pip install` 自动重试机制（独立优化，需要网络策略设计）
- 前端 PDF 内嵌渲染（依赖 LobeHub FileViewer 组件）
