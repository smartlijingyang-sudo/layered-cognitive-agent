# ADR-0122: Plugin-native debug & 观测体系 — 从legacy清理到 RunDiagnostic 协议

- Status: Accepted (2026-08-31)
- Supersedes: 局部兼容收口 ADR-0119 / ADR-0121
- Decision: 让任何 agent 失败能在 1 条命令 (`lca-ops debug-run <run_id>`) 内自助定位;每种可观测/可调试能力都按 LCA Protocol → Seam → Provider → Adapter → Registry → Plugin 模型落地;清掉双执行路径的 legacy 垃圾;新增 RunDiagnostic / KernelLogProjection 等缺失的诊断插件。

> **2026-09-02 实施脚注:** 本 ADR 描述的命令以最终落地为准:
> - `lca-ops debug run <run_id>` → 顶层 `lca-ops debug-run <run_id>`(合并 dash);`debug env <run_id>` → `debug-env`。
> - `phase-error` diagnose alias **未落地**;4 个真实 alias 是 `model-not-seen` / `loop-stuck` / `memory-poisoned` / `approval-rejected`(连字符)。详见 [run-debug-guide.md §5](../debug/run-debug-guide.md)。
> - `lca-ops replay <run_id> --no-llm` → `lca-ops journal replay <run_id> --step K`(走 `ReplayCursor`,见 ADR-0167 D10)。
>
> ADR 原文保留以体现决策路径,但请勿按字面命令调用。

## Context

### 触发事件

- 2026-08-31 用户发起 `run_f03bd17f77f1`(objective="你能做什么"),失败:固定中文 "Agent 阶段执行失败。可能原因: phase 异常、模型未响应或工具循环失败。"
- 连续 7 个 run 同样失败,模式完全一致。
- 用户多次发问: 为什么不打补丁?为什么不架构优雅解决?为什么这么难 debug?为什么 trace 看不到?为什么日志没有?为什么 debug 环境/运维不能快速定位?为什么清理 legacy?为什么专门一个 debug 排查指导?为什么插件化思维一切插件?

### 用户诉求聚合

| 维度 | 用户要求 |
|---|---|
| 修复策略 | 不打补丁,架构优雅解决,从第一性原理出发 |
| 范围 | 不止此 bug,整体链路都可复现可 debug可理解清晰观察 |
| 工具 | 应该有专门 md 或工具,有专门 debug排查指导, 高级工程师自助定位 |
| 哲学 | 职责清晰边界清晰模块化插件化思维统一 |
| 资产盘点 | traces/runs 下之前不是有 json 日志文件吗,能利用就利用,不好就干掉 |
| 重复清理 | 为什么还有 legacy run 没有迁移,要清理垃圾 |

### 现有可观测资源(已经有的,要利用)

`lca-ops` 子命令(ADR-0065 §六 / PR-9):

```text
trace <run_id>           # 通用轨迹
explain <run_id>         # 失败路径投影
explain control <phase>  # 解析 profile 声明式控制贡献
optimize <run_id>        # 优化候选(延迟/token/重试)
graph-run <run_id>       # Mermaid 插件交互图
minimal-repro <run_id>   # 失败因果链 + evidence refs
diff-context <run_id>    # 同 run step 上下文
diff-runs <a> <b>        # 两次 run 对比
cost <run_id>            # LlmCallCompleted 成本累加
evidence <run_id> <ref>  # 查 state_ref → evidence payload
diagnose <alias>         # 4 个内置 alias: model-not-seen / loop-stuck / memory-poisoned / approval-rejected
```

每条都已经是 Protocol → Adapter 实现(`lca/plugins/tools/diagnostics/`):
- `TraceInspectorToolAdapter` / `FailureExplainer` / `OptimizationFinder` / `PluginGraphRenderer` / `MinimalReproduction` / `DiffContext` / `DiffRuns` / `CostCalculator` / `EvidenceInspector` / `DiagnosePattern`

**已存在的 trace 文件(per-run, plugins 写):**
- `traces/runs/<run_id>/journal.jsonl` —— JsonlJournalProjector
- `traces/runs/<run_id>/journal.jsonl.narrative.md` —— NarrativeSidecar
- `traces/runs/<run_id>/manifest.json` —— ManifestMaterializer
- `traces/runs/<run_id>/profile_snapshot.json` —— profile snapshot plugin

**死文件(清理):**
- `traces/lca_journal.jsonl` —— v1→v2 migration marker,实际空
- `traces/lca_journal.v1.archive.jsonl` —— v1 归档
- `traces/lca_trace.jsonl` —— 旧 OTel span,未在用
- `traces/e2e_demo_trace.jsonl` —— 旧 demo,未在用
- `traces/generate_report.py` —— 旧脚本

### debug 实际过程的痛点(现场 15 步, 不是事后整理)

| 步骤 | 操作 | 障碍 |
|---|---|---|
| 1 | `git status` | 22 文件未提交,不知哪些相关 |
| 2 | `cat manifest.json` | doctor_report 只给固定字符串 |
| 3 | `cat journal.jsonl` | seq=7/8/9 缺失, 以为 projection 失败 |
| 4 | `tail kernel-serve.log` | stdout 在 pipe, 看不到本次 run |
| 5 | `grep` 日志 | 无痕迹 |
| 6 | `ps aux` | 找到 pid, fd=1 是 pipe |
| 7 | `readlink /proc/...fd/1` | pipe 不可读 |
| 8 | `curl POST /runs` | 同样 failed, 错误固定 |
| 9 | `cat journal | jq` | 缺 seq=7/8/9 |
| 10 | 子进程 `run_inline3.py` | 必须重启 kernel 捕获 stdout |
| 11 | patch `projection_registry` | 发现 `_omit_empty` bug |
| 12 | patch `phase_execution_policy` | 发现 RuntimeError |
| 13 | patch `_resolver` | 定位完整调用链 |
| 14 | grep `run_file_store_scope` | 发现 legacy path 有, 新 path 没 |
| 15 | 对比双路径 scope | 漏项是物理原因 |

**15 步、4 类工具(git/fs/process/patch)**。不是 debug, 是考古。

### 根因(按层次)

#### A. Diagnostic 信号被层层吞没 (不 fail-loud)

| 位置 | 行为 | 后果 |
|---|---|---|
| `ProjectionRegistry.publish` | 异常只 log warning | jsonl 缺事件 |
| `phase_execution_policy.execute_with_policy` | 异常进 `PhaseAttemptFailure.error_type`, **不写 stderr** | 失败类型仅在 journal |
| `system_role_renderer._resolver()` | RuntimeError 抛, 无 traceback 输出 | debug 必须 patch |
| `phase_failure_stop_result` | attempt 信息塞 `final_output` 字符串 | 诊断信息被当输出 |
| `reducer.apply_terminal_outcome` | `state.last_error` 为空时 fallback 写死 | UI 只看到固定中文 |

#### B. stdout/stderr 路径分裂

- `./scripts/lca-ops kernel serve` → `.lca-ops/kernel-serve.log`
- `uv run python -m lca_kernel serve` (grok 直启) → **未知 pipe**
- production vs dev 启动路径不一致

#### C. 双执行路径并存(legacy 垃圾)

`lca/plugins/transport/webserver/handlers/runs/execute/execute.py` 12 个函数:
- `execute_run` (line 265,837) — 两个定义
- `resume_run` (line 407, 865) — 两个定义
- `schedule_run` (line 783) — 调 legacy
- `scheduling.schedule_run` (line 43) — 调新路径
- `_RunLifecycleCoordinator` (line 833) — adapter shim
- `_record_terminal_materialization` (line 807) — shim
- `_freeze_bindings` / `_stage_machine_attachments` 等 legacy helpers

**4 个 schedule/execute 入口**,任何一处少 ambient 都是事故。本次 bug 物理原因。

#### D. scope helpers 散落 8 个文件

```
run_id_scope (run_finalizer.py)
run_attachment_scope (run_attachment_scope.py)
run_workspace_scope (workspace/scope.py)
run_scope (observability/run_context.py)
search_run_scope (search/scope.py)
run_file_store_scope (attachment/run_file_store_scope.py)
run_machine_root_scope (attachment/run_machine_root_scope.py)
adopt_run_scope (observability/run_context.py)
```

**每次新增 ambient 是 shotgun surgery**。

#### E. explain / diagnose 命令不覆盖 phase_error

`DiagnosePattern` enum 现有 4 个 alias:
- `MODEL_NOT_SEEN` / `LOOP_STUCK` / `MEMORY_POISONED` / `APPROVAL_REJECTED`

**缺 `PHASE_ERROR` alias**。本次失败恰好是 phase_error,但只能 `explain` 看到固定字符串 "未在所选事件中发现失败终态"(因为 seq=7/8/9 缺失 + final_output 中文截断)。

#### F. `_omit_empty` UnboundLocalError

Python scoping bug,任何含非空 list 的 envelope 都触发,seq=7/8/9 缺失的物理原因。

#### G. debug 工具散落,不可重放

- `lca-ops diagnose <alias>` —— 4 个 alias
- `lca-ops debug tree|run|scope` —— debug 已散落
- `lca-ops trace|explain|optimize|graph-run|minimal-repro|diff-context|diff-runs|cost|evidence` —— 9 个只读工具

**但没有完整 SOP 文档**,agent 拿到 bug 报告不知道从哪里开始。

## Decision

### 0. 总原则:每种 debug / 观测能力都是 Plugin

按 LCA 哲学 `Protocol → Seam → Provider/Adapter → Registry → Plugin`,所有新增都遵循。每个 diagnostic 工具 = 一个 Protocol + 一个 Adapter + 一个 CLI 命令 wrapper。

### 1. 死文件清理(垃圾干掉)

```
rm traces/lca_journal.jsonl
rm traces/lca_journal.v1.archive.jsonl
rm traces/lca_trace.jsonl
rm traces/e2e_demo_trace.jsonl
rm traces/generate_report.py
```

`traces/lca_journal.jsonl` 的引用 `settings.py:15` 改为 `traces/runs/<run_id>/journal.jsonl`(或"per-run canonical")。

### 2. `RunAmbit` 单聚合(取代 8 个 scope helpers)

新增 `lca/infrastructure/observability/facade/run_ambit.py`:

```python
@dataclass(frozen=True, slots=True)
class RunAmbit:
    scope: RunScope | None = None
    run_id: RunId | None = None
    trace_id: TraceId | None = None
    attachment_ids: tuple[str, ...] = ()
    workspace: Workspace | None = None
    file_store: FileStore | None = None
    machine_root: str | None = None
    search_state: SearchRunState | None = None
    plan_ref: str = ""
    role: str = ""

@contextmanager
def bind_run_ambit(ambit: RunAmbit) -> Iterator[RunAmbit]: ...

def current_run_ambit() -> RunAmbit | None: ...
```

**所有旧 scope helpers 重写读 RunAmbit**, 入口只剩 `bind_run_ambit`。旧 helpers 标记 deprecated, 2026 Q4 删除。

### 3. 单一执行路径 + legacy 清理

**删除 `lca/plugins/transport/webserver/handlers/runs/execute/execute.py`:**
- 整个文件清空或替换为 `<8 lines>` 的 facade(只保留必要 re-export)
- 删除 `execute_run` (line265) / `execute_run` shim (line837) / `schedule_run` (line783) / `resume_run` (line407, 865) / `_freeze_bindings` / `_stage_machine_attachments` / `_RunLifecycleCoordinator` / `_record_terminal_materialization` / `assemble_run_hub` / `create_hub_for_session` / `_emit_plugin_inventory` / `finalize`

**保留唯一:**
- `RunLifecycleCoordinator` (lifecycle/lifecycle.py) —— 入口
- `RunExecutionEnvironment.prepare` (execute/execution_environment.py) —— 用 `bind_run_ambit` 单层
- `scheduling.schedule_run` (scheduling.py) —— 唯一任务调度
- `loop_drivers.py:CognitiveRunDriver` —— 唯一 driver

**新增约束:** 任何代码新增 ambient 资源:加到 `RunAmbit` 字段,不在调用方 with-block 加。

### 4. `RunDiagnostic` 协议(typed 失败不丢)

新增 `lca/runtime/diagnostic.py`:

```python
@dataclass(frozen=True, slots=True)
class StackFrame:
    filename: str
    lineno: int
    name: str
    source_line: str | None = None

@dataclass(frozen=True, slots=True)
class PhaseAttemptSummary:
    attempt: int
    category: PhaseErrorCategory
    error_type: str
    message: str | None = None

@dataclass(frozen=True, slots=True)
class RunDiagnostic:
    run_id: RunId
    trace_id: TraceId
    phase: SemanticPhase
    node_id: str
    error_type: str
    message: str                              # sanitized
    stack: tuple[StackFrame, ...]
    causation: tuple[str, ...]
    attempts: tuple[PhaseAttemptSummary, ...]
    suggested_action: str | None = None
    run_ambit_digest: str | None = None       # ambient 状态 hash
```

**Lifecycle 收口:**
- PhaseTransaction 在 phase_error 时构造 `RunDiagnostic`(抓 stack via `traceback.extract_tb`)
- `StopDecision.failure: RunDiagnostic | None` 取代 `final_output` 误用
- reducer 据此设 `state.last_error = diagnostic.message`
- `TerminalOutcome.error_ref: RunDiagnostic` 一路传到 UI/doctor
- `doctor_report.H6.error_ref` 直接链向 typed 异常

### 5. `KernelLogProjection` Plugin(per-run kernel.log)

新增 `lca/plugins/observability/projections/kernel_log.py`:

```python
class KernelLogProjection(JournalProjector):
    """Write per-run kernel internals to traces/runs/<id>/kernel.log.

    Independent file handle, separate from primary journal — even when the
    main journal.jsonl is broken, kernel.log survives. Failures go to backstop.
    """
    def __init__(self, run_id: str, trace_id: str):
        self._path = Path(f"traces/runs/{run_id}/kernel.log")
        self._fh = self._path.open("a", encoding="utf-8")

    def on_event(self, stamped): ...

    def close(self): self._fh.close()
```

**LCA_DEBUG=1 时启用**,默认也启用, 只是没 stacktrace。

### 6. `phase-error` diagnose alias(扩展现有 DiagnosePattern)

新增 `lca/plugins/tools/diagnostics/phase_error.py`:

```python
class PhaseErrorDiagnose:
    """诊断 phase_error: 解析 StopDecision.failure 中的 RunDiagnostic。"""
    pattern = DiagnosePattern.PHASE_ERROR

    def diagnose(self, store: RunStore, *, trace_id: str | None = None) -> DiagnosisReport:
        findings = []
        for event in store.events:
            if isinstance(event.event, AgentRunFinished) and event.event.status == "failed":
                err = event.event.error or ""
                findings.append(Finding(
                    pattern=self.pattern,
                    severity="high",
                    summary=f"phase_error: {err}",
                    evidence_refs=(event.seq,),
                    detail="建议: 跑 lca-ops debug run <run_id> 拿 typed stack trace",
                ))
        return DiagnosisReport(self.pattern, tuple(findings))
```

加进 `DiagnosePattern` enum, `diagnose` 命令支持。`lca-ops diagnose phase-error --jsonl traces/runs/<id>/journal.jsonl` 直接用。

### 7. `RunDiagnosticInspector` 新增 Tool Adapter

新增 `lca/plugins/tools/diagnostics/run_diagnostic.py`:

```python
class RunDiagnosticInspector(ToolAdapter):
    """One-shot RunDiagnostic export. Reads journal + kernel.log + manifest.

    输出 8-section 报告:
    [1] manifest summary
    [2] journal event timeline (with missing seq)
    [3] kernel.log tail (last 50 lines, with grep on stack frames)
    [4] phase.cursor + causation chain
    [5] AgentRunFinished.error_ref → typed RunDiagnostic
    [6] Stack frames (top 8)
    [7] Suggested action
    [8] Replay command
    """
```

CLI wrapper `lca-ops debug run <run_id>` 注册。

### 8. `_omit_empty` 重写

```python
def _omit_empty(value):
    if isinstance(value, Mapping):
        return {
            k: v
            for k, v in (
                (str(k), _omit_empty(v)) for k, v in value.items()
            )
            if not _is_empty_default(v)
        }
    if isinstance(value, list):
        return [
            p for p in (_omit_empty(item) for item in value)
            if not _is_empty_default(p)
        ]
    return value
```

**纯 generator + comprehension,无作用域歧义**。

### 9. `ProjectionBackstop` Plugin

新增 `lca/plugins/observability/projections/backstop.py`:

```python
class ProjectionBackstop(JournalProjector):
    """独立 IO 写 projection_failures.jsonl,保留 traceback。

    主 journal.jsonl 写盘失败时,backstop 仍记录,debug 有信号。
    """
```

`ProjectionRegistry.publish` 失败时调 `_backstop.record(...)`。backstop 自己的 IO 失败时 fallback `structlog.warning` + **不 raise**(避免递归)。

### 10. `lca-ops debug run <run_id>` 主入口

合并 7 个 tools 在一个命令下:

```sh
$ lca-ops debug run run_f03bd17f77f1
[1/8] manifest        traces/runs/run_f03bd17f77f1/manifest.json
[2/8] journal         12 events (missing seq 7,8,9 — projection failed)
[3/8] kernel.log      24 lines (last 5 shown below)
[4/8] phase.cursor    think.main
[5/8] error_ref       RuntimeError: render_system_role: no FileStore...
[6/8] stack frames    top 8 lines
[7/8] suggested       Bind FileStore via RunAmbit.file_store before thinking
[8/8] replay cmd      lca-ops replay run_f03bd17f77f1 [--no-llm]
```

实现: 新增 `lca/plugins/tools/diagnostics/debug_run.py` (DebugRunAdapter),`lca/infrastructure/cli/commands/tools.py` 加 `debug` 子命令组。

### 11. `lca-ops replay <run_id>` 重放

新增 `lca/infrastructure/cli/commands/replay.py`:

```python
def replay(run_id, *, no_llm=False):
    """重放一个 run。复用 profile_snapshot.json + journal + RunAmbit。

    --no-llm 时 mock LLM,只跑 phase_graph 逻辑(不消耗 token)。
    """
```

### 12. `LCA_DEBUG=1` fail-loud 开关

新增 `lca/infrastructure/observability/debug_mode.py`:

```python
@lru_cache
def debug_mode() -> bool:
    return os.environ.get("LCA_DEBUG", "").lower() in ("1", "true", "yes")
```

开启时:
- 所有 Projection 异常 + traceback → stderr
- 所有 PhaseAttemptFailure 详情 → stderr
- PhaseExecutionFailure 完整 stack → stderr
- `ProjectionRegistry.publish` 失败时,除 backstop 外还 stderr

非 debug 模式:仍保留 typed diagnostic,只不写 stderr。

### 13. `docs/debug/run-debug-guide.md` —— Agent SOP

新增 `docs/debug/run-debug-guide.md`:

```markdown
# Agent run debug 排查指南(SOP)

## 拿到一个 run_id 后,按顺序执行:

### 第 1 步: 一键诊断
\`\`\`sh
lca-ops debug run <run_id>
\`\`\`
输出 8-section 报告(manifest / journal / kernel.log / phase.cursor /
error_ref / stack / suggested / replay cmd)。

### 第 2 步: 如果 stack 看不全
\`\`\`sh
lca-ops trace <run_id> --jsonl traces/runs/<id>/journal.jsonl
lca-ops explain <run_id> --jsonl traces/runs/<id>/journal.jsonl
\`\`\`

### 第 3 步: 如果怀疑 phase 抛了异常
\`\`\`sh
lca-ops diagnose phase-error --jsonl traces/runs/<id>/journal.jsonl
\`\`\`

### 第 4 步: 重放
\`\`\`sh
lca-ops replay <run_id> --no-llm
\`\`\`
不消耗 token,只跑 phase_graph。

### 第 5 步: 对比成功 run
\`\`\`sh
lca-ops diff-runs <failing_id> <passing_id> --jsonl ...
\`\`\`

### 第 6 步: 找 ambient 状态
\`\`\`sh
lca-ops debug env <run_id>
\`\`\`
dump RunAmbit 全部字段。

## 工具对照表

| 用途 | 命令 |
|---|---|
| 主诊断 | `lca-ops debug run <run_id>` |
| 看轨迹 | `lca-ops trace <run_id>` |
| 失败路径 | `lca-ops explain <run_id>` |
| 优化候选 | `lca-ops optimize <run_id>` |
| 插件图 | `lca-ops graph-run <run_id>` |
| 失败因果 | `lca-ops minimal-repro <run_id>` |
| step 上下文 | `lca-ops diff-context <run_id>` |
| 两次 run 对比 | `lca-ops diff-runs <a> <b>` |
| 成本 | `lca-ops cost <run_id>` |
| evidence payload | `lca-ops evidence <run_id> <ref>` |
| phase_error 诊断 | `lca-ops diagnose phase-error` |
| 重放 | `lca-ops replay <run_id>` |

## per-run 资产

`traces/runs/<run_id>/` 下:
- `journal.jsonl` —— canonical journal (JsonlJournalProjector)
- `journal.jsonl.narrative.md` —— narrative sidecar (NarrativeSidecar)
- `manifest.json` —— terminal manifest (ManifestMaterializer)
- `profile_snapshot.json` —— profile 快照
- `kernel.log` —— kernel 内部日志 (KernelLogProjection, ADR-0122)

## fail-loud

`LCA_DEBUG=1` 时,所有 projection / phase / projection 异常 + traceback → stderr。

## 不要做的事

- 不要 cat 全局 `traces/lca_journal.jsonl`(已 dead)
- 不要 grep `.lca-ops/lobehub.log` 找 kernel 异常(那是 Next.js 进程日志)
- 不要 patch 源码 + 重启才能定位(任何 bug 都该 1 条命令定位)
```

### 14. `RunAmbit` debug dump 命令

新增 `lca-ops debug env <run_id>` 输出:
```
RunAmbit:
  scope: RunScope(run_id=..., trace_id=...)
  run_id: ...
  trace_id: ...
  attachment_ids: ()
  workspace: <workspace at /mnt/data/...>
  file_store: <FileStore at traces/files/...>
  machine_root: None
  search_state: SearchRunState(...)
  plan_ref: 8638ea0484ac7f7f
  role: 助手
```

如果某字段 None 而 think.main 抛 RuntimeError,**直接定位**。这是本次 bug 的最快诊断。

### 15. LCA_DEBUG 文档化

`AGENTS.md` 加一段:LCA_DEBUG 用法 + 何时开启。

## 不变量保持

- C1 闭集: `RunDiagnostic` / `StackFrame` / `PhaseAttemptSummary` 是新增**观察协议**,不增加 phase / event vocabulary;`RunAmbit` 聚合已存在的 ambient,不改语义;`DiagnosePattern.PHASE_ERROR` 是新 enum 值,非新 phase。
- C4 Reducer: reducer 仍是 state 唯一写入者,RunDiagnostic 是 sealed value。
- C7 控制/观察分离: RunDiagnostic 是诊断观察,StopDecision 仍是 control plane;不进入 prompt。
- AGENTS.md §5 "不要用兼容别名":legacy `execute_run` 整文件清空。
- ADR-0119 / ADR-0121: gateway/runs plugin 边界保留;kernel boot / 事件流不变。

## 验证

- `scripts/check_kernel_boundary.py` + importlinter 边界
- `uv run mypy lca` —— RunDiagnostic / RunAmbit / StopDecision.failure typed 完整
- 全量 pytest, ruff, lint-imports, vulture
- `tests/test_run_ambit.py` —— bind_run_ambit 单层替代 6 层 with
- `tests/test_run_diagnostic.py` —— RuntimeError 一路传至 TerminalOutcome.error_ref
- `tests/test_kernel_log_projection.py` —— per-run kernel.log 写入,主 journal 坏时仍有
- `tests/test_projection_backstop.py` —— projection 抛 IOError, backstop 记录
- `tests/test_omit_empty.py` —— 非空 list 不再 UnboundLocalError
- `tests/test_legacy_cleanup.py` —— 旧 `execute_run` / `schedule_run` (execute.py) 不再 import 成功
- `tests/test_diagnose_phase_error.py` —— phase-error alias 输出 RunDiagnostic 摘要
- `tests/test_lca_ops_debug_run.py` —— `lca-ops debug run` 输出 8-section 报告
- `tests/test_lca_ops_replay.py` —— `lca-ops replay <run_id>` 重跑, `--no-llm` 不消耗 token

## 改动文件

| 文件 | 改动 |
|---|---|
| `lca/infrastructure/observability/facade/run_ambit.py` (新) | `RunAmbit` + `bind_run_ambit` + `current_run_ambit` + 窄 accessor |
| `lca/runtime/diagnostic.py` (新) | `RunDiagnostic` + `StackFrame` + `PhaseAttemptSummary` |
| `lca/contracts/models/core/stop.py` | `StopDecision.failure: RunDiagnostic | None` 取代 final_output 误用 |
| `lca/contracts/models/core/terminal_outcome.py` | `error_ref` 携带 RunDiagnostic |
| `lca/plugins/transport/webserver/handlers/runs/execute/execute.py` | **整个删除**(12 个函数清零) |
| `lca/plugins/transport/webserver/handlers/runs/execute/execution_environment.py` | `prepare()` 用 `bind_run_ambit` 单层; 接入 KernelLogProjection |
| `lca/infrastructure/cli/commands/tools.py` | 加 `debug run` / `debug env` 子命令 |
| `lca/infrastructure/cli/commands/replay.py` (新) | `replay<run_id>` 子命令 |
| `lca/plugins/tools/diagnostics/phase_error.py` (新) | `PhaseErrorDiagnose` (新 alias) |
| `lca/plugins/tools/diagnostics/run_diagnostic.py` (新) | `RunDiagnosticInspector` (DebugRunAdapter) |
| `lca/plugins/tools/diagnostics/debug_run.py` (新) | DebugRun 主命令 wrapper |
| `lca/plugins/observability/projections/kernel_log.py` (新) | `KernelLogProjection` |
| `lca/plugins/observability/projections/backstop.py` (新) | `ProjectionBackstop` |
| `lca/plugins/phase_graph/failure_stop.py` | 把 attempts 填到 RunDiagnostic, 不再写 final_output 字符串 |
| `lca/runtime/reducer.py` | `apply_stop` 读 StopDecision.failure 设 state.last_error |
| `lca/infrastructure/observability/facade/projection_registry.py` | publish 失败 → backstop + stderr(if LCA_DEBUG) |
| `lca/infrastructure/observability/debug_mode.py` (新) | `debug_mode()` lru_cache |
| `lca/infrastructure/observability/journal/engine/journal_io.py` | `_omit_empty` 重写 |
| `lca/infrastructure/attachment/system_role_renderer.py` | `_resolver` 接受 `RunAmbit.file_store is None` degrade |
| 全部 scope helpers | 重写读 RunAmbit |
| `traces/lca_journal.jsonl` / `traces/lca_journal.v1.archive.jsonl` / `traces/lca_trace.jsonl` / `traces/e2e_demo_trace.jsonl` / `traces/generate_report.py` | **删除** |
| `lca/infrastructure/observability/facade/settings.py` | `_DEFAULT_JSONL_PATH` 改为指向 `traces/runs/<run_id>/journal.jsonl` 模板 |
| `docs/debug/run-debug-guide.md` (新) | Agent SOP |
| `AGENTS.md` | 加 LCA_DEBUG 段落 |
| `tests/test_run_ambit.py` / `test_run_diagnostic.py` / `test_kernel_log_projection.py` / `test_projection_backstop.py` / `test_omit_empty.py` / `test_legacy_cleanup.py` / `test_diagnose_phase_error.py` / `test_lca_ops_debug_run.py` / `test_lca_ops_replay.py` (新) | 覆盖 |

## 验收标准

ADR-0122 完成后:

1. `traces/runs/<run_id>/kernel.log` 一定有完整 traceback (LCA_DEBUG=1)
2. `traces/runs/<run_id>/manifest.json` 一定有 typed `error_ref: RunDiagnostic`
3. `lca-ops debug run <run_id>` 在 30 秒内输出 8-section 报告
4. `lca-ops replay <run_id> --no-llm` 重跑不消耗 token
5. `lca-ops diagnose phase-error` 覆盖本次失败模式
6. 任何新加 ambient 资源必须经 RunAmbit,不在 with-block 重复
7. 任何新加 exception 路径必须经 RunDiagnostic, 不被吞
8. legacy `execute_run` / `schedule_run` (execute.py) 全删除,只有一个入口
9. traces 下死文件全清
10. docs/debug/run-debug-guide.md 是 agent 拿到 bug 报告时的**第一份读物**

## 替代方案(以及为什么不用)

- **A. 仅 patch `_resolver` 加 traceback**:修症状,下次类似问题还是 ad-hoc debug,违反"统一解决"
- **B. 不清理 legacy**:违反 AGENTS.md §5 + 用户明确要求清理
- **C. 不实现 RunAmbit**:scope helpers 散落问题没解决,下次扩展 ambient 又会有人忘
- **D. 不实现 replay**:违反 "可复现" 原则
- **E. 不写 debug guide**:agent 拿到 bug 仍不知道从哪开始, 违反"高级工程师自助"

## 实施 PR 分批

PR-1 (基础): `_omit_empty` 重写 + dead files 清理 + KernelLogProjection + ProjectionBackstop
PR-2 (协议): RunDiagnostic + RunAmbit + StopDecision.failure + reducer 改造
PR-3 (执行): legacy execute.py 清理 + 单执行路径
PR-4 (debug): DebugRunAdapter + phase-error alias + replay + debug env
PR-5 (文档): docs/debug/run-debug-guide.md + AGENTS.md LCA_DEBUG 段