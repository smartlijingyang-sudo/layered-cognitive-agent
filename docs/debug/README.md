# Debug & Observability

LCA 的"高级工程师自助定位"基础设施入口。所有 debug / observability / 诊断能力按 Plugin 模型落地(ADR-0122)。

## 入口文档

- **[run-debug-guide.md](./run-debug-guide.md)** — Agent 第一读物。`lca-ops debug run <run_id>` 的完整 SOP + 工具对照表 + 常见失败模式 → 命令映射。

## 现有可观测/调试能力

### 一次性诊断

| 命令 | 用途 |
|---|---|
| `lca-ops debug run <run_id>` | 主入口,8-section 报告 |
| `lca-ops debug env <run_id>` | dump RunAmbit |
| `lca-ops trace <run_id>` | journal 轨迹 |
| `lca-ops explain <run_id>` | 失败路径投影 |
| `lca-ops diagnose <alias>` | 模式诊断(model-not-seen / loop-stuck / memory-poisoned / approval-rejected / phase-error) |

### 离线分析

| 命令 | 用途 |
|---|---|
| `lca-ops replay <run_id> --no-llm` | 重放失败,不消耗 token |
| `lca-ops optimize <run_id>` | 优化候选(延迟/token/重试) |
| `lca-ops graph-run <run_id>` | Mermaid 插件交互图 |
| `lca-ops minimal-repro <run_id>` | 失败因果链 + evidence refs |
| `lca-ops diff-context <run_id>` | 同 run step 上下文 |
| `lca-ops diff-runs <a> <b>` | 两次 run 对比 |
| `lca-ops cost <run_id>` | LLM 成本累加 |
| `lca-ops evidence <run_id> <ref>` | evidence payload 查询 |

### Live

| 命令 | 用途 |
|---|---|
| `lca-ops journal logs` | 默认 tail 最新 run 的 spine SSOT(`traces/runs/<id>/events.jsonl`) |
| `lca-ops journal logs -r <run_id>` | 离线回放指定 run(优先 events.jsonl,否则兜底 journal.raw.jsonl) |
| `lca-ops journal logs -v` | 展开 payload + error 通道 traceback |

## fail-loud 开关

```sh
LCA_DEBUG=1 lca_kernel serve --profile ...
```

开启后,所有 projection / phase / 异常 + traceback → stderr + `traces/runs/<id>/kernel.log`。

## per-run 资产

`traces/runs/<run_id>/`:

- `events.jsonl` — spine SSOT(ADR-2026-09-02-i17-stream-align;canonical journal events)
- `journal.json` — `lca.journal/3` step 投影(pretty-printed, codemap 用)
- `journal.raw.jsonl` — legacy v2 envelope stream(CLI 已不直接读,仅迁移源)
- `manifest.json` — terminal manifest
- `profile_snapshot.json` — profile 快照
- `kernel.log` — kernel 内部日志(ADR-0122)
- `diagnostic.json` — typed RunDiagnostic(ADR-0122)

## 相关 ADR

- ADR-0065 §六 / PR-9: coding-agent tools (9 个 trace/explain/... 命令)
- ADR-0121: attachment FileRef SSOT
- ADR-0122: Plugin-native debug & 观测体系