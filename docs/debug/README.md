# Debug & Observability

LCA 的"高级工程师自助定位"基础设施入口。所有 debug / observability / 诊断能力按 Plugin 模型落地(ADR-0122)。

## 入口

- **[run-debug-guide.md](./run-debug-guide.md)** — `lca-ops debug-run <run_id>` 的完整 8 步 SOP + 每步 `WHY / DO / OUTPUT / NEXT / FAIL` + 工具对照表 + 常见失败模式 → 命令映射。命令路径由 [`scripts/check_run_debug_sync.py`](../../scripts/check_run_debug_sync.py) 与 CLI 注册表同步。
- **`.agents/skills/lca-debug-run/SKILL.md`** — Agent 触发入口。口语映射 + 5 步流程概览 + bug-vs-debrief 决策 + 升级到 `lca-code-review` 的证据包交接。人类通常不需要这一份。
- **`AGENTS.md` §6** — 命令矩阵指针 + 服务问题分流(不是 run 问题)。

## 一次性命令速查

按"我要做什么"选命令;每个命令的完整语义、副作用、边界见 `run-debug-guide.md` 和 `lca-ops <cmd> --help`。

### 诊断一次 run

| 命令 | 用途 |
|---|---|
| `lca-ops debug-run <run_id>` | 主入口,8-section 报告 |
| `lca-ops debug-env <run_id>` | dump RunAmbit |
| `lca-ops trace <run_id>` | journal 轨迹 |
| `lca-ops explain <run_id>` | 失败路径投影 |
| `lca-ops diagnose <problem>` | 模式诊断(连字符):`model-not-seen` / `loop-stuck` / `memory-poisoned` / `approval-rejected`(`phase-error` 不存在) |

### 离线分析

| 命令 | 用途 |
|---|---|
| `lca-ops journal replay <run_id> --step K` | 重放失败:重读 `traces/runs/<id>/model_visible/`,**不调 LLM、不消耗 token**。`--no-llm` 不是 flag,因为默认就是只读不调。 |
| `lca-ops runs create --user-text "..."` | 触发一个新 run(走 `POST /runs` carrier,**唯一**创建 run 的入口) |
| `lca-ops optimize <run_id>` | 优化候选(延迟/token/重试) |
| `lca-ops graph-run <run_id>` | Mermaid 插件交互图 |
| `lca-ops minimal-repro <run_id>` | 失败因果链 + evidence refs |
| `lca-ops diff-context <run_id>` | 同 run step 上下文 |
| `lca-ops diff-runs <a> <b>` | 两次 run 对比 |
| `lca-ops cost <run_id>` | LLM 成本累加 |
| `lca-ops evidence <run_id> <ref>` | evidence payload 查询 |

> **历史命令修正**:`lca-ops replay <run_id> --no-llm` **不存在**。`lca-ops replay`
> 不是顶层命令。真实命令是 `lca-ops journal replay <run_id> --step K`,且
> 默认就**不消耗 token**(只 dump messages + actions)。如果你在文档里看到
> `lca-ops replay`,请按上面这条改正。

### Live

| 命令 | 用途 |
|---|---|
| `lca-ops journal logs` | 默认 tail 最新 run 的 spine SSOT(`traces/runs/<id>/events.jsonl`) |
| `lca-ops journal logs -r <run_id>` | 离线回放指定 run(优先 events.jsonl,否则兜底 journal.raw.jsonl) |
| `lca-ops journal logs -v` | 展开 payload + error 通道 traceback |

## fail-loud

fail-loud 是 `lca_kernel` lifecycle 的 K6 内置钩子(`lca_kernel/lifecycle.py`,ADR-0115):
未捕获异常、SIGTERM/SIGINT、环境加载违例直接以非零退出或 stderr 暴露,不被静默吞掉。
**常开,没有开关**;`LCA_DEBUG` 环境变量不存在(ADR-0122 §12 的设计未落地)。
异常与 traceback 的持久化走 spine 事件 + I10 sidecar(`<sha256>.json`),不写 `kernel.log`。

## per-run 资产

`traces/runs/<run_id>/`:

- `events.jsonl` — spine SSOT(ADR-2026-09-02-i17-stream-align;canonical journal events)
- `journal.json` — `lca.journal/3` step 投影(pretty-printed, codemap 用)
- `journal.raw.jsonl` — legacy v2 envelope stream(CLI 已不直接读,仅迁移源)
- `manifest.json` — terminal manifest
- `profile_snapshot.json` — profile 快照
- `kernel.log` — 失败兜底单行记录,唯一写者是 `record_run_failure()`(`lca/plugins/transport/webserver/handlers/runs/terminal/failure.py`):仅当 run 的收尾路径本身失败时追加一行 `run_failure_observed ...`。**多数 run 没有此文件,缺失不代表失败丢失**(ADR-0122 §5 的 `KernelLogProjection` 未落地)。进程级内核日志在 `/tmp/lca-kernel.log`(`lca-ops heal` 的 spawn 输出),两者不要混淆。
- `diagnostic.json` — typed RunDiagnostic(ADR-0122)

## 相关 ADR

- ADR-0065 §六 / PR-9: coding-agent tools (9 个 trace/explain/... 命令)
- ADR-0121: attachment FileRef SSOT
- ADR-0122: Plugin-native debug & 观测体系
