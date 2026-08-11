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
        stdout=cleaned_stdout,  # 改：用 cleaned
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        error=error_text,
        generated_files=tuple(generated),  # 新增
    )
```

**影响分析**: `run_command` 也走此路径。但 shell 命令不会输出 `__LCA_ONLYBOXES_ARTIFACTS__` 标记，`strip_artifacts()` 对无标记的 stdout 是安全的 no-op（直接返回原文 + 空列表）。

**补充发现**: `OnlyboxesSandboxAdapter` 的 `run()`、`run_in_session()`、`run_terminal()` 已全部收敛到 `_exec_terminal()` → `parse_terminal_response()`。`parse_exec_response()` 虽然定义在 `onlyboxes_bootstrap.py` 中，但**全代码库无任何调用方**——它是死代码。这意味着变更 1 修复的是唯一的单点故障：一次修复同时救回 `execute_code`、`run_command`、`sandbox_execute` 三个入口。后续可清理 `parse_exec_response()` 死代码（不在本次范围内）。

### 变更 2: `execute_code()` — 注入 artifact scanner bootstrap

**文件**: `lca/layer0_infra/computer/runtime_exec.py`

**现状**: `execute_code()` 直接传用户代码到沙箱，不注入文件扫描器。即使代码生成了文件，也不会被 harvest。

**修复**: 在用户代码后追加 artifact scanner，通过 `try/finally` 保证即使代码异常也能 harvest。

```python
_ARTIFACT_SCANNER = """
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    _output_dir = "/mnt/data/outputs"
    if _os.path.isdir(_output_dir):
        for _fname in _os.listdir(_output_dir):
            _fpath = _os.path.join(_output_dir, _fname)
            if _os.path.isfile(_fpath):
                try:
                    with open(_fpath, "rb") as _fh:
                        _raw = _fh.read()
                    _scan_files.append({
                        "name": _fname,
                        "b64": _b64.b64encode(_raw).decode(),
                        "mime_type": _mt.guess_type(_fname)[0] or "application/octet-stream",
                    })
                except Exception:
                    pass
    if _scan_files:
        print("__LCA_ONLYBOXES_ARTIFACTS__" + _json.dumps(_scan_files) + "__END_LCA_ARTIFACTS__")
except Exception:
    pass
"""
```

**ADR-0046 合规**: 仅扫描 `/mnt/data/outputs/`（`SANDBOX_OUTPUT_SUBDIR`），与 Mock / E2B / Local 三个后端行为一致。不扫描 `/mnt/data/` 根目录，避免：
- 把用户上传的输入文件当"新产物"重复收集
- 把技能挂载文件（`/mnt/data/_skills/`）当产物 harvest
- `entry_basename()` 在 `try_append_generated_file()` 中会剥离子目录路径，导致同名输入/输出文件冲突

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

`build_computer_observation()` 新增文件处理逻辑。**复用已有共享函数** `_stored_part()`（来自 `sandbox_observation.py`），与 `build_exec_observation()` 保持同构：

```python
from lca.layer0_infra.tools.sandbox_observation import _stored_part
from lca.layer0_infra.workspace.scope import get_run_workspace


def build_computer_observation(result, *, tool_name, start, store):
    ...
    extra: dict[str, Any] = {}
    if not result.success:
        extra[FAILURE_KIND] = FAILURE_KIND_EXECUTION

    # 新增：复用 _stored_part() 存储文件，与 sandbox_exec_observation 同构
    file_parts: list[dict[str, Any]] = []
    for gen in result.generated_files:
        file_parts.append(_stored_part(store, gen.data, gen.name, gen.mime_type))

    if file_parts:
        extra["files"] = file_parts

    # 新增：记录到 workspace artifact ledger（与 build_exec_observation 对齐）
    if result.success and file_parts:
        workspace = get_run_workspace()
        if workspace is not None:
            workspace.artifacts.record_from_tool_files(
                file_parts, tool_name=tool_name, agent_role=""
            )
    ...
```

**`previewable` 取值策略**: `_stored_part()` 默认 `previewable=True`（所有文件标记为可预览）。这与 `build_exec_observation()` 对生成文件的处理一致——只有超长 stdout/stderr 落盘为 `.log` 时才传 `previewable=False`。实际的预览能力由前端按 MIME 类型判断，`previewable` 只是 hint。

**需要给 `build_computer_observation` 注入 `FileStore` 引用**。当前签名不接收 `store`，需要从 `tool_set.py` 传入：

```python
# tool_set.py — 传入 store
async def execute(_self, args):
    result = await spec.handler(runtime, args)
    return build_computer_observation(result, tool_name=spec.name, start=start, store=store)
```

**闭环验证**: `extra["files"]` → `tool_files(obs)` 提取 → `ToolInvoked.files` → SSE → 前端文件卡片。

**Workspace artifact ledger 对齐决策**: `build_exec_observation()` 在成功路径调用 `_record_workspace_artifacts()` 将产物记入 workspace 级账本，用于 run 结束时的 `closure_text()`（"任务已完成，已生成以下文件：…"）和 pipeline 成员间的 `handoff_block()`。Computer tool 路径必须对齐——否则通过 `execute_code` 生成的文件不会出现在 run 结束摘要中。

### 变更 4: PDF 可预览

**文件**: `lca/layer0_infra/file_store.py`

在 `_is_previewable()` 的 MIME 集合中加入 `application/pdf`：

```python
if mime in {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/pdf",  # 新增
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
  → 注入 _ARTIFACT_SCANNER（仅扫描 /mnt/data/outputs/，ADR-0046 合规）
  → try/finally 包裹用户代码
  → runtime.execute() → adapter → parse_terminal_response()
      → strip_artifacts() ✅ 解析标记（变更 1）
      → SandboxResult.generated_files ✅
  → SandboxExecResult.generated_files ✅ (sandbox_exec_result_from 已传递)
  → ComputerOpResult.generated_files ✅ (变更 5)
  → build_computer_observation(store=...)
      → _stored_part() 存储文件到 FileStore ✅ (变更 3，复用共享函数)
      → extra["files"] = [{name, url, mimeType, ...}] ✅
      → workspace.artifacts.record_from_tool_files() ✅ (变更 3，ledger 对齐)
      → state["code"] = source_code ✅ (变更 2)
  → tool_files(obs) → files ✅
  → ToolInvoked.files ✅ → SSE → 前端文件卡片 ✅
  → Run 结束 → closure_text() 包含生成文件摘要 ✅
```

## 测试策略

### 单元测试

1. **`parse_terminal_response` harvest**: 构造带 `__LCA_ONLYBOXES_ARTIFACTS__` 标记的 JSON 响应 → 验证 `SandboxResult.generated_files` 非空
2. **`parse_terminal_response` no-op**: 构造普通 stdout（无标记）→ 验证 `generated_files` 为空、stdout 不变
3. **`build_computer_observation` 文件传递**: 构造带 `generated_files` 的 `ComputerOpResult` → 验证 `Observation.extra["files"]` 非空
4. **`build_computer_observation` 无文件**: 空 `generated_files` → 验证 `extra` 无 `files` 键

### 集成测试

5. **`execute_code` 生成文件**: 代码写文件到 `/mnt/data/outputs/` → 验证 observation 包含文件元数据
6. **ADR-0046 合规**: 代码同时在 `/mnt/data/`（根目录）和 `/mnt/data/outputs/` 写文件 → 验证只有 `outputs/` 下的文件被 harvest，根目录文件被忽略
7. **技能挂载不污染**: `activate_skill("pdf")` 后执行代码 → 验证 `/mnt/data/_skills/` 下的文件不出现在 `generated_files`
8. **`run_command` 不受影响**: 执行普通 shell 命令 → 验证行为不变

### 端到端验证

9. **素数 + PDF 场景复测**: 重新构建镜像后，执行素数程序 + PDF 生成 → 验证文件出现在 ToolInvoked.files

## 不在范围内

- Onlyboxes 镜像重建（运维操作，不在代码变更范围）
- `parse_exec_response()` 死代码清理（已确认无调用方，可后续安全删除）
- LobeHub Work 注册系统对齐（独立特性，需要 gateway + 前端联动）
- `pip install` 自动重试机制（独立优化，需要网络策略设计）
- 前端 PDF 内嵌渲染（依赖 LobeHub FileViewer 组件）

## 修订记录

- **v1** (2026-08-11): 初版设计
- **v2** (2026-08-11): 代码核实修正
  - 变更 2 扫描器路径从 `/mnt/data` 改为 `/mnt/data/outputs`（ADR-0046 合规）
  - 变更 3 改为复用 `_stored_part()` 共享函数，消除重复
  - 变更 3 补齐 workspace artifact ledger 记录（与 `build_exec_observation` 对齐）
  - 补充 `parse_exec_response()` 死代码发现
  - 测试策略增加 ADR-0046 合规测试和技能挂载不污染测试
