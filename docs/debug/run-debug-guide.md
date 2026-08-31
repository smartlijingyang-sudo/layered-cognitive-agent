# Agent run debug 排查指南 (SOP)

> **拿到一个 run_id,先读本文。** 这是 agent 和工程师自助定位 run 失败的标准操作流程。
> 配合 ADR-0122 — Plugin-native debug & 观测体系。所有命令基于 `lca-ops`(per-run trace 文件在 `traces/runs/<run_id>/`)。

---

## TL;DR — 拿到 run_id 后第一件事

```sh
lca-ops debug run <run_id>
```

这条命令**自动发现** per-run journal 路径, 输出 8-section 诊断(manifest / journal / kernel.log / phase.cursor / error_ref / stack / suggested / replay cmd)。30 秒内能看到真根因。

如果 `lca-ops debug run` 没找到根因(罕见), 按下面顺序逐级深入。

---

## 完整排查流程

### 第 0 步: 确认 run 真的失败了

```sh
curl http://localhost:8765/runs/<run_id> | jq '{status, session_status, error}'
```

`status=failed` 且 `error` 是中文固定字符串("Agent 阶段执行失败。…") → 进入排查。

### 第 1 步: 一键诊断 (`lca-ops debug run`)

```sh
lca-ops debug run run_f03bd17f77f1
```

输出:
```
[1/8] manifest        traces/runs/run_f03bd17f77f1/manifest.json
[2/8] journal         12 events (missing seq 7,8,9 — projection failed)
[3/8] kernel.log      24 lines (last 5 shown below)
[4/8] phase.cursor    think.main
[5/8] error_ref       RuntimeError: render_system_role: no FileStore in ambient scope
[6/8] stack frames    top 8 lines
[7/8] suggested       Bind FileStore via RunAmbit.file_store before thinking
[8/8] replay cmd      lca-ops replay run_f03bd17f77f1 --no-llm
```

**8-section 报告就是答案**。如果不够, 继续。

### 第 2 步: 看 journal 事件流 (`lca-ops trace`)

```sh
lca-ops trace <run_id> --jsonl traces/runs/<run_id>/journal.jsonl
```

输出每条事件的 `seq / time / type / data` 摘要。如果 `event_count` < 真实事件数, **journal 缺事件**, 跳到第 4 步。

### 第 3 步: 解析失败路径 (`lca-ops explain`)

```sh
lca-ops explain <run_id> --jsonl traces/runs/<run_id>/journal.jsonl
```

输出 `events / causal_chain / bottlenecks / plugin_graph`。**`causal_chain` 是从 user prompt 到失败的完整因果链**。

### 第 4 步: 看 kernel.log(per-run)

```sh
tail -50 traces/runs/<run_id>/kernel.log
```

`kernel.log` 包含所有 kernel 内部事件(structlog 输出 / RuntimeObserved / stack trace / projection 失败警告)。**这是定位 RuntimeError / IO 错误最快的路径**。

`LCA_DEBUG=1` 时, 任何 projection 异常 + traceback → stderr,**也会** 写到 `kernel.log`。

### 第 5 步: 失败诊断(`lca-ops diagnose <alias>`)

```sh
# phase 抛了异常时:
lca-ops diagnose phase-error --journal traces/runs/<run_id>/journal.jsonl

# 模型没看到应该看到的 manifest item:
lca-ops diagnose model-not-seen --expected-kind <kind> --journal ...

# 工具循环卡死:
lca-ops diagnose loop-stuck --journal ...

# 记忆被污染:
lca-ops diagnose memory-poisoned --journal ...

# 审批被拒:
lca-ops diagnose approval-rejected --journal ...
```

每个 alias 输出 `DiagnosisReport(findings=[Finding(severity, summary, evidence_refs, detail)])`,`severity=high` 是必看的。

### 第 6 步: 重放失败(`lca-ops replay`)

```sh
# 不消耗 token, 只跑 phase_graph 逻辑:
lca-ops replay <run_id> --no-llm

# 完整重放(消耗 token, 慎用):
lca-ops replay <run_id>
```

`replay` 复用 `traces/runs/<run_id>/profile_snapshot.json` + session + RunAmbit, 重新跑同一 profile。**用于验证修复**。

### 第 7 步: 对比成功 run(`lca-ops diff-runs`)

```sh
lca-ops diff-runs <failing_id> <passing_id> --jsonl traces/runs/<failing_id>/journal.jsonl
```

输出 `events_added / events_removed / fields_changed`。**找出两次 run 的关键差异**(profile / prompt / ambient / model response)。

### 第 8 步: 看 plugin 交互图(`lca-ops graph-run`)

```sh
lca-ops graph-run <run_id> --jsonl traces/runs/<run_id>/journal.jsonl
```

输出 Mermaid 图。**直观看到哪些 plugin 参与了这次 run**。

### 第 9 步: 找 RunAmbit 状态(`lca-ops debug env`)

```sh
lca-ops debug env <run_id>
```

dump `RunAmbit` 全部字段(scope / run_id / attachment_ids / workspace / file_store / machine_root / search_state / plan_ref / role)。**如果某字段 None 而 think.main 抛 RuntimeError, 直接定位 ambient 缺失**。

### 第 10 步: 看 cost / evidence

```sh
lca-ops cost <run_id> --jsonl traces/runs/<run_id>/journal.jsonl
lca-ops evidence <run_id> <ref> --jsonl traces/runs/<run_id>/journal.jsonl
lca-ops minimal-repro <run_id> --jsonl traces/runs/<run_id>/journal.jsonl
```

---

## 工具对照表

| 用途 | 命令 |
|---|---|
| 主诊断 | `lca-ops debug run <run_id>` |
| RunAmbit 状态 | `lca-ops debug env <run_id>` |
| 看轨迹 | `lca-ops trace <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| 失败路径 | `lca-ops explain <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| 优化候选 | `lca-ops optimize <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| 插件图 (Mermaid) | `lca-ops graph-run <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| 失败因果 | `lca-ops minimal-repro <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| step 上下文 | `lca-ops diff-context <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| 两次 run 对比 | `lca-ops diff-runs <a> <b> --jsonl traces/runs/<id>/journal.jsonl` |
| LLM 成本 | `lca-ops cost <run_id> --jsonl traces/runs/<id>/journal.jsonl` |
| evidence payload | `lca-ops evidence <run_id> <ref> --jsonl traces/runs/<id>/journal.jsonl` |
| phase_error 诊断 | `lca-ops diagnose phase-error --journal traces/runs/<id>/journal.jsonl` |
| 重放 | `lca-ops replay <run_id> [--no-llm]` |

---

## per-run 资产

`traces/runs/<run_id>/` 下, **全部由 Projection Plugin 产出**:

| 文件 | 写入 Plugin |
|---|---|
| `journal.jsonl` | `JsonlJournalProjector` |
| `journal.jsonl.narrative.md` | `NarrativeSidecar` |
| `manifest.json` | `ManifestMaterializer` |
| `profile_snapshot.json` | profile snapshot plugin |
| `kernel.log` | `KernelLogProjection` (ADR-0122) |
| `diagnostic.json` | `RunDiagnosticRecorder` (ADR-0122) |

**任何新增 per-run 资源都加一个 Projection Plugin**。

跨 run 全局文件:

| 文件 | 用途 |
|---|---|
| `traces/latest.json` | 最新 run 原子指针 |
| `traces/last` | 上次 run 的诊断摘要 |
| `traces/projection_failures.jsonl` | Projection 失败 backstop (ADR-0122) |

---

## fail-loud 开关

```sh
LCA_DEBUG=1 lca_kernel serve --profile ...
```

开启后:
- 所有 projection 异常 + traceback → stderr
- 所有 `PhaseAttemptFailure` 详情 → stderr
- `PhaseExecutionFailure` 完整 stack → stderr
- `RunDiagnostic.message` → stderr
- Projection 失败除 backstop 外还 stderr

**dev 推荐开, prod 默认关(避免日志爆炸)**。

---

## 常见失败模式 → 命令对照

| 症状 | 第一反应 |
|---|---|
| `status=failed` + 中文固定 error | `lca-ops debug run <run_id>` |
| journal 缺事件 (seq=7/8/9 等) | `tail kernel.log` + `LCA_DEBUG=1` 重跑 |
| model 没看到 expected manifest item | `lca-ops diagnose model-not-seen --expected-kind <kind>` |
| 工具循环 30s 超时 | `lca-ops diagnose loop-stuck --window 10` |
| 审批被拒 | `lca-ops diagnose approval-rejected` |
| phase 抛 RuntimeError | `lca-ops diagnose phase-error` + `lca-ops debug env <run_id>` |
| Memory 污染 | `lca-ops diagnose memory-poisoned` |
| 想离线重放 | `lca-ops replay <run_id> --no-llm` |
| 对比两次 run | `lca-ops diff-runs <a> <b>` |
| 想要 mermaid 图 | `lca-ops graph-run <run_id>` |

---

## 不要做的事

- ❌ 不要 cat 全局 `traces/lca_journal.jsonl`(已 dead,迁移到 per-run 后是占位符)
- ❌ 不要 grep `.lca-ops/lobehub.log` 找 kernel 异常(那是 Next.js 进程日志)
- ❌ 不要 grep `.lca-ops/kernel-serve.log` 找本次 run(可能被 pipe 截走, stdout 不可靠)
- ❌ 不要 patch 源码 + 重启才能定位(任何 bug 都该 1 条命令定位,否则就是 ADR-0122 没收口)
- ❌ 不要 ps + /proc/fd/1 找 kernel stdout(直接 `cat traces/runs/<id>/kernel.log` 更快)
- ❌ 不要靠 TypeScript 搜索 `phase.cursor` 在 journal 里硬找 cursor(`lca-ops explain` 已经给出)

---

## 进阶: agent 编程时

### 给 run 写测试

```python
def test_my_phase_fails_cleanly():
    # 用 lca-ops replay 验证
    subprocess.run(["lca-ops", "replay", "<run_id>", "--no-llm"])
    # 期望 RunDiagnostic 出现在 diagnostic.json
    diag = json.loads(Path("traces/runs/<id>/diagnostic.json").read_text())
    assert diag["phase"] == "think.main"
```

### 监控 live runs

```sh
lca-ops logs -v
lca-ops logs -d        # + delta events
```

### 检查诊断 alias 是否覆盖

```sh
grep -A 30 "class DiagnosePattern" lca/infrastructure/observability/diagnostics/diagnostics.py
```

新失败模式 → 加 enum value + diagnose_* 函数 + 测试 + 给本指南加 row。

---

## 完整资源地图

```text
lca/
  infrastructure/
    observability/
      diagnostics/
        diagnostics.py               # DiagnosePattern enum + 4 个诊断函数
        ...
      journal/
        jsonl/projector.py           # JsonlJournalProjector (per-run journal)
        console/projector.py         # ConsoleJournalProjector
        otel/projector.py            # OtelProjector
        engine/
          engine.py                  # RunStore / RunScope
          journal_io.py              # _omit_empty, dumps_journal_record
        stream/
          narrative_sidecar.py       # NarrativeSidecar
      facade/
        projection_registry.py       # ProjectionRegistry
        run_context.py               # run_scope
        settings.py                  # _DEFAULT_JSONL_PATH (per-run template)
      journal_io.py                  # StampedEvent / JournalEvent 模型
    cli/
      commands/
        tools.py                     # 9 个 trace/explain/optimize/... 命令
        diagnostics.py               # diagnose alias
  plugins/
    tools/diagnostics/
      trace_inspector_tool.py        # trace
      failure_explainer.py           # explain
      optimization_finder.py         # optimize
      plugin_graph_renderer.py       # graph-run
      minimal_reproduction.py        # minimal-repro
      diff_context.py                # diff-context
      diff_runs.py                   # diff-runs
      cost_calculator.py             # cost
      evidence_inspector.py          # evidence
      # + phase_error.py (ADR-0122 新增)
      # + run_diagnostic.py (ADR-0122 新增)
      # + debug_run.py (ADR-0122 新增)
    observability/
      projections/
        # + kernel_log.py (ADR-0122 新增)
        # + backstop.py (ADR-0122 新增)

traces/
  runs/<run_id>/
    journal.jsonl                    # canonical per-run journal
    journal.jsonl.narrative.md
    manifest.json
    profile_snapshot.json
    # + kernel.log (ADR-0122 新增)
    # + diagnostic.json (ADR-0122 新增)
  latest.json
  last
  # + projection_failures.jsonl (ADR-0122 新增)
```

---

## 相关 ADR

- ADR-0065: §六 / PR-9 coding-agent tools (trace/explain/optimize/... 9 个)
- ADR-0119: gateway-as-plugin, webserver routes
- ADR-0121: attachment FileRef SSOT
- **ADR-0122 (本 ADR):** Plugin-native debug & 观测体系

---

## 维护

- 任何新增 trace 写入 → 加 Projection Plugin + CLI wrapper + 测试 + 本文档 row
- 任何新增诊断模式 → 加 `DiagnosePattern` enum + `diagnose_*` 函数 + 测试 + 本文档 row
- 任何 per-run 文件 schema 变更 → 更新本文档的"per-run 资产"章节
- 任何新增 `--jsonl` 路径 → 默认指向 `traces/runs/<run_id>/journal.jsonl`(per-run canonical)