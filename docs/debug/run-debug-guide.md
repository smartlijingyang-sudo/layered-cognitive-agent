# Agent run debug 排查指南 (SOP)

> **拿到一个 run_id,先读本文。** 这是 coding agent 和工程师自助定位 run 失败的标准操作流程。
> 命令清单与 CLI 实测一致(`uv run python -m lca.infrastructure.cli.cli <cmd> --help`)。

---

## TL;DR — 拿到 run_id 后第一件事

```sh
lca-ops debug-run <run_id>
```

顶层命令 `debug-run` 输出 **8-section 诊断**(ADR-0122):

```
[1/8] manifest        status / broken_hop
[2/8] journal         events + missing_seqs + spine.execution_point → …链
[3/8] kernel.log      per-run kernel 日志 tail —— 仅当文件存在;多数 run 没有
[4/8] phase.cursor    最后完成的 phase
[5/8] error_ref       StopDecision.failure → 类型化 RunDiagnostic
[6/8] stack frames    栈顶 8 帧
[7/8] suggested_action 人读修复建议
[8/8] replay command  lca-ops replay <run_id> --no-llm
```

**关于每一节的实际产出**:

- `[3/8] kernel.log` 节只在 `traces/runs/<run_id>/kernel.log` 存在时打印 tail;该文件由 `KernelLogProjection`(ADR-0122)在 kernel 显式 flush 时才会写入,**多数 run 目录下根本不存在**。如果没看到这一节,不要假定失败信息在别处丢失——直接跳到下面的"补充步骤 A:读 sidecar 拿 traceback"。
- `[5/8] error_ref` 给的是高层的 `node=think.main error_kind=internal attempts=1[1:permanent:ValueError]`,**不含完整 traceback**;这只是分类标签。

加 `--json` 给 agent 用。

> ⚠️ 不要混淆:
> - `lca-ops debug-run <id>`(顶层; ADR-0122 8 段诊断)✅
> - `lca-ops debug run --run-id <id>`(老兼容; 仅 `cat traces/runs/<id>.journal`)
> - `lca-ops debug trace --run-id <id>`(老兼容; 读 diagnostic.jsonl)
>
> 新代码全部用 `debug-run` / `debug-env` 顶层命令。

---

## 完整排查流程

### 第 0 步: 确认 run 真的失败了

```sh
lca-ops status --json   # 先确认 LCA 服务层
```

如果服务层有 missing, 跑 `lca-ops heal` 自愈。如果服务正常但 run 失败, 进入第 1 步。

### 第 1 步: 一键诊断(`lca-ops debug-run`)

```sh
lca-ops debug-run run_<id>
```

8-section 报告就是答案。如果不够, 继续第 2 步。

### 第 2 步: 看 journal 事件流(`lca-ops trace`)

```sh
lca-ops trace <run_id>
lca-ops trace <run_id> --focus llm|tools|delegation
lca-ops trace <run_id> --depth 48 --json
```

读的是默认 journal(自动定位 `traces/runs/<id>/`); `--jsonl <path>` 可显式指定。

### 第 3 步: 解析失败路径(`lca-ops explain`)

```sh
lca-ops explain <run_id>
lca-ops explain <run_id> --json
```

输出失败路径投影 + 因果链。

### 第 4 步: 看 kernel.log(per-run,可选)

```sh
test -f traces/runs/<run_id>/kernel.log && tail -n 200 traces/runs/<run_id>/kernel.log || echo "(no kernel.log — 该 run 没产出此文件,见下一步)"
```

`kernel.log` 是 `KernelLogProjection`(ADR-0122)显式 flush 的输出文件:**不是每个 run 都有**;只有当 kernel 在 process 期间主动 sink 了 structlog / RuntimeObserved / stack trace 时才会出现。这一节只能用作**补充证据**,不能当作必出路径——`debug-run [3/8]` 省略它并不意味着失败信息丢失。

### 补充步骤 A: **读 `<sha256>.json` sidecar 拿完整 traceback** ← 最常被忽略

run 目录下除 `events.jsonl` / `manifest.json` / `profile_snapshot.json` 之外的、文件名是 **64 位十六进制(看起来像 sha256)**的 `.json` 文件,是 **I10 size offload sidecar**(见 `lca/infrastructure/observability/spine/sinks/file_sink.py:_ATOMIC_THRESHOLD = 4096`):当一条 event 序列化后超过 4 KB(PIPE_BUF,Linux 原子写阈值),FileSink 不进主 ledger,而是把完整 payload 写到 `<sha256>.json`,主 ledger 只留 placeholder:`{"execution_point": "...", "offloaded": "<sha256>"}`。

**包含完整 traceback / 完整 call_frames / 完整 source_location 的 event(任意 channel,>4 KB)都会落到 sidecar**。`debug-run [2/8] journal` 和 `journal trace` / `journal logs` 都只读 `events.jsonl`,所以**这些 traceback 在主 ledger 里看不到**,必须直接读 sidecar。

```sh
# 列出 run 目录下所有 sidecar(events.jsonl / manifest.json / profile_snapshot.json / .swp 之外)
ls traces/runs/<run_id> | grep -vE '^(events\.jsonl|manifest\.json|profile_snapshot\.json|\..*\.swp)$'

# 通常只有一个(或零个):读它
SIDECAR=$(ls traces/runs/<run_id>/<sha256>.json 2>/dev/null | head -1)
[ -n "$SIDECAR" ] && jq -r '
  "exception_class: \(.payload.exception_class // "-")",
  "exception_message: \(.payload.exception_message // "-")",
  "source_location: \(.payload.source_location // "-")",
  "reason: \(.payload.reason // "-")",
  "---traceback---",
  (.payload.traceback_text // "(no traceback_text)")
' "$SIDECAR"
```

快速版(单行 jq):

```sh
SIDECAR=$(ls traces/runs/<run_id>/*.json | grep -vE 'events\.jsonl|manifest\.json|profile_snapshot\.json' | head -1)
jq -r '.payload.exception_class + ": " + (.payload.exception_message // "(no message)")' "$SIDECAR"
```

> ⚠️ 注意:**这些 sidecar 不是"被隔离的错误事件"**——FD-2 是 detector/sink 内部异常的 containment(见 `anomaly.py:91 / 216 / 327` 和 `emit_pipeline.py:204 / 242`),它**不**决定是否写文件。文件是否 offload 只看大小 4 KB。这条规则容易让人误以为"error-channel event 都被隔离出去了",记住:**事件仍然是 spine event,只是体积大就 sidecar。**

### 第 5 步: 失败诊断(`lca-ops diagnose <alias>`)

### 第 5 步: 失败诊断(`lca-ops diagnose <alias>`)

> **注意:** 4 个内置 alias(**不包含 `phase-error`**, 虽然部分文档历史地写过) — `phase-error` 在 CLI 里返回 `Unknown pattern`。

```sh
# 模型没看到应该看到的 manifest item:
lca-ops diagnose-model-not-seen --expected-kind <kind>

# 工具循环卡死:
lca-ops diagnose-loop-stuck

# 记忆被污染:
lca-ops diagnose-memory-poisoned

# 审批被拒:
lca-ops diagnose-approval-rejected
```

或一行 `lca-ops diagnose <alias>`(同上 4 个)。每个 alias 输出 `DiagnosisReport(findings=[Finding(severity, summary, evidence_refs, detail)])`,`severity=high` 必看。

### 第 6 步: 离线重放失败

```sh
# 推荐: 不消耗 token, 只跑 phase_graph 逻辑:
lca-ops journal replay <run_id> --no-llm

# 打印 model-visible + actions(debug 验证用):
lca-ops journal replay <run_id> --tool <tool_name>
```

> ⚠️ `lca-ops replay` **不是顶层命令**(老文档里写的)。当前 replay 在 `journal replay` 子命令下。

### 第 7 步: 对比成功 run(`lca-ops diff-runs`)

```sh
lca-ops diff-runs <failing_id> <passing_id>
```

输出 `events_added / events_removed / fields_changed` + `prompt_hash_a/b` + `delta`。

### 第 8 步: 看 plugin 交互图(`lca-ops graph-run`)

```sh
lca-ops graph-run <run_id>   # Mermaid, stdout
```

### 第 9 步: 找 RunAmbit 状态(`lca-ops debug-env`)

```sh
lca-ops debug-env <run_id>
lca-ops debug-env <run_id> --json
```

dump `RunAmbit` + diagnostic 摘要(scope / run_id / attachment_ids / workspace / file_store / phase_cursor / failure_node_id / error_message / error_type / attempts / suggested_action)。**某字段 None 而 phase 抛 RuntimeError → 直接定位 ambient 缺失**。

### 第 10 步: 看 cost / evidence / minimal-repro

```sh
lca-ops cost <run_id> --pricing-ref <ref>
lca-ops evidence <run_id> sha256:<digest>     # 查 arguments_ref/output_ref → payload
lca-ops minimal-repro <run_id>                 # 失败因果链 + evidence refs
lca-ops optimize <run_id> --limit 5            # 优化候选(延迟/token/重试)
```

---

## 工具对照表(全部顶层命令,经 `./scripts/lca-ops --help` 核对)

| 用途 | 命令 |
|---|---|
| **主诊断 (8 段)** | `lca-ops debug-run <run_id>` |
| RunAmbit + 摘要 | `lca-ops debug-env <run_id>` |
| 看轨迹 | `lca-ops trace <run_id> [--focus llm\|tools\|delegation] [--depth 24]` |
| 失败路径投影 | `lca-ops explain <run_id>` |
| 失败因果链 | `lca-ops minimal-repro <run_id>` |
| step 上下文差异 | `lca-ops diff-context <run_id> --step N` |
| 两次 run 对比 | `lca-ops diff-runs <a> <b>` |
| 优化候选 | `lca-ops optimize <run_id>` |
| 插件图(Mermaid) | `lca-ops graph-run <run_id>` |
| LLM 成本累加 | `lca-ops cost <run_id>` |
| evidence payload | `lca-ops evidence <run_id> <ref>` |
| 预设症状诊断 | `lca-ops diagnose-{model-not-seen,loop-stuck,memory-poisoned,approval-rejected}` |
| **Live tail spine** | `lca-ops journal logs` (默认 follow 最新 run) |
| **离线回放 spine** | `lca-ops journal logs -r <run_id>` |
| step 树 / 因果链 | `lca-ops journal steps` |
| narrative.md | `lca-ops journal narrative` |
| 模型可见性校验 | `lca-ops journal verify-model-visible` |
| DSH Trajectory HTML | `lca-ops journal trajectory` |
| step 复盘(不调 LLM) | `lca-ops journal replay <run_id> --no-llm` |
| 老兼容入口 | `lca-ops debug tree\|run\|scope\|trace` |

---

## per-run 资产(`traces/runs/<run_id>/`)

| 文件 | 来源 | 是否一定存在 |
|---|---|---|
| `events.jsonl` | **spine SSOT**(ADR-0167;append-only) | ✅ 每个 run |
| `manifest.json` | `ManifestMaterializer` | ✅ 每个 run |
| `profile_snapshot.json` | profile snapshot | ✅ 每个 run |
| `journal.json` | step 投影(`lca.journal/3.1`) | ⚠️ 仅 run 进入 step 树后才写;**early-fail 的 run 没有**,`journal steps` 会报 `journal.json not found` |
| `journal.narrative.md` | `StepNarrativeWriter` | ⚠️ 同上 |
| `<sha256>.json` sidecar | **I10 size offload**(4 KB 以上的 event 自动 offload) | ⚠️ 仅当有 event > 4 KB,**包含完整 traceback / call_frames / source_location 的 event 必定在这里**,不是"错误隔离" |
| `kernel.log` | `KernelLogProjection` (ADR-0122) | ❌ **多数 run 不存在**——只有 kernel 显式 flush 才会写;`debug-run [3/8]` 缺这一节不代表丢东西 |
| `journal.raw.jsonl` | legacy v2 envelope stream(仅迁移源,CLI 不读) | ❌ 仅迁移期间的 run |
| `diagnostic.json` | `RunDiagnosticRecorder` (ADR-0122) | ❌ 已不再写 |
| `.<file>.swp` | 编辑器临时文件(vim 等) | ❌ 不参与诊断 |

跨 run 全局:

| 文件 | 用途 |
|---|---|
| `traces/latest.json` | 最新 run 原子指针 |
| `traces/last` | 上次 run 诊断摘要 |
| `traces/projection_failures.jsonl` | Projection 失败 backstop (ADR-0122) |

---

## 不要做的事

- ❌ 不要 cat `traces/lca_journal.jsonl`(已 dead, 默认 `--jsonl` 仍指向它,见下)
- ❌ 不要 cat `traces/runs/<id>/journal.jsonl`(旧 schema; 走 `journal.json` 或 `events.jsonl`)
- ❌ 不要 `lca-ops replay <run_id>`(命令不存在; 用 `journal replay <run_id>`)
- ❌ 不要 `lca-ops diagnose phase-error`(已删; 看上面 4 个 alias)
- ❌ 不要 `LCA_DEBUG=1`(环境变量不存在,被 fail-loud 替代)
- ❌ 不要 grep `.lca-ops/lobehub.log` 找 kernel 异常(那是 Next.js 进程日志)
- ❌ 不要 grep `.lca-ops/kernel-serve.log` 找本次 run(stdout 可能被 pipe 截走,不可靠)
- ❌ 不要 `ps` + /proc/.../fd/1 找 kernel stdout
- ❌ 不要假定 `traces/runs/<id>/kernel.log` 存在 —— 它**多数 run 不写**,遇到 [3/8] 不打印直接读 sidecar(见"补充步骤 A")
- ❌ 不要 `cat traces/runs/<id>/events.jsonl` 然后以为 traceback 不在那里就完了 —— 大体积 event 在 sidecar,见"补充步骤 A"
- ❌ 不要 patch 源码 + 重启才能定位(任何 bug 都该 1 条命令定位,否则就是 ADR-0122 没收口)

> **关于 `lca-ops trace` / `explain` / `diff-runs` / `diff-context` / `minimal-repro` / `optimize` / `graph-run` / `cost` / `evidence` 的 `--jsonl <path>` 默认值**:全部默认指向 `traces/lca_journal.jsonl`(dead path)。实际上当前实现会回退去读 per-run 的 `events.jsonl`(`-_shared._resolve_journal_path` 的 fallback),所以 `lca-ops trace <run_id>` 不带 `--jsonl` 仍能工作,但**只能用每个 run 自己的 ledger**,跨 run 的文件名手填。改默认值这事属于 P-1 修复,跑命令时记得默认参数是不可信的。

---

## 常见失败模式 → 命令对照

| 症状 | 第一反应 |
|---|---|
| `status=failed` + 中文固定 error | `lca-ops debug-run <run_id>`,然后**直接读 `<sha256>.json` sidecar** 拿完整 traceback(见"补充步骤 A") |
| spine 缺事件 (seq 不连续) | `debug-run` [2/8] 报 missing_seqs;**多数情况下不是事件被隔离**,而是 ≥ 4 KB 的 event offload 到 sidecar,主 ledger 只留 placeholder `{"offloaded": "<sha256>"}` → `cat traces/runs/<id>/<sha256>.json` |
| `debug-run [3/8] kernel.log` 没打印 | **预期行为**;该文件多数 run 不存在。直接读 `<sha256>.json` sidecar 找 traceback |
| `debug-run [5/8] error_ref` 只给分类标签 | 同上,**不含完整 traceback**;读 sidecar |
| model 没看到 expected manifest item | `lca-ops diagnose-model-not-seen --expected-kind <kind>` |
| 工具循环卡死 / 超时 | `lca-ops diagnose-loop-stuck` |
| 审批被拒 | `lca-ops diagnose-approval-rejected` |
| phase 抛 RuntimeError | `lca-ops debug-env <run_id>` 找 RunAmbit 缺字段 |
| Memory 污染 | `lca-ops diagnose-memory-poisoned` |
| 想离线重放 | `lca-ops journal replay <run_id> --no-llm` |
| 对比两次 run | `lca-ops diff-runs <a> <b>` |
| 想要 mermaid 图 | `lca-ops graph-run <run_id>` |
| 看 DSH 风格 HTML | `lca-ops journal trajectory` |
| audit 写权限 / hook 残留 | `lca-ops audit-{control-surface,state-writers,direct-commands,hook-attach}` |
| 想知道某能力归属 | `lca-ops why <capability>` / `why-plugin <id>` |

---

## 自检闭环(报告"已定位"前)

- [ ] 引用了**具体 trace 文件**(路径 + seq/行号),不是"看 journal"
- [ ] 给了**修复方向**(哪个 ADR / 哪个 seam / 哪个 reducer),不是"应该没问题"
- [ ] 用 `--json` 验证过结构化输出
- [ ] 没让用户 `grep` / `ps` / `readlink /proc/...fd/1`(ADR-0122 现场记录过 15 步考古 = 失败)
- [ ] 没改 source code(debug 是 read-only)

---

## 相关 ADR

- ADR-0065 §六 / PR-9: coding-agent tools(9 个 trace/explain/... 命令)
- ADR-0119: gateway-as-plugin, webserver routes
- ADR-0121: attachment FileRef SSOT
- **ADR-0122: Plugin-native debug & 观测体系** —— 8 段诊断的来源
- ADR-0164 / 0165 / 0166 / **0167**: spine SSOT + step 物化视图 + model-visible

---

## 维护约定

- **改命令调用语法时**:跑 `lca-ops <cmd> --help` 实测,改完本表后再提交
- **删 alias / 加 alias**:同时改本表 + `lca-ops diagnose --help`
- **加 per-run 资源**:加 Projection Plugin + CLI wrapper + 本表 row
- **改 spine / journal 路径**:同时核对 ADR-0167 + AGENTS.md §6
- **不要复活已删 alias / 命令**(如 `phase-error`、`lca-ops replay`、`LCA_DEBUG`)