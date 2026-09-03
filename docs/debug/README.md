# Debug & Observability

LCA 的"高级工程师自助定位"基础设施入口。所有 debug / observability / 诊断能力按 Plugin 模型落地(ADR-0122)。

## 入口文档

- **[run-debug-guide.md](./run-debug-guide.md)** — Agent 第一读物。`lca-ops debug-run <run_id>` 的完整 SOP + 工具对照表 + 常见失败模式 → 命令映射。

## "最新一次 run 全面分析"流程(最常用触发)

用户表达"**最新一次 run** / **刚才那个 run** / **最近一次** / **上一个 run** / **看看刚才发生了什么** / **分析一下这次**" → **直接按这个流程走,不要先去翻代码、问 run_id、或 ls traces/runs**。

```sh
# 1. 取最新 run_id(pointer 文件,不是 ls -t)
LATEST=$(jq -r .run_id traces/latest.json)

# 2. 一键 8 段诊断(首选;所有症状入口)
./scripts/lca-ops debug-run "$LATEST"
#    注:[3/8] kernel.log 多数 run 没有,[5/8] 不含完整 traceback。

# 3. 看完整 spine 事件流(理解过程;模型所见即日志)
#    表格视图(控制点 + channel + outcome):
./scripts/lca-ops journal logs -r "$LATEST" -v
#    树视图(人读;不带 run_id 默认最新一个;--human:缩进 + payload 原文 + Δms + 自动折叠 reducer.apply/token 噪声):
./scripts/lca-ops journal trace            # 最新 run
./scripts/lca-ops journal trace "$LATEST"  # 显式 run_id

# 3.5 读 traceback:从专用索引或 sidecar 拿(ADR-2026-09-03)
#    首选:`./scripts/lca-ops journal exceptions "$LATEST"`(人读+grep+--json)
#    它读 <run_id>.exceptions.jsonl —— 每个 exception.caught EP 必落盘的专用索引,
#    不论 payload 大小,绝不丢(底层 TracingFileSink 三道防线 + 必落盘保证)。
#    Sidecar(旧路径,> 4 KiB offload)文件名现在是 <sha8>-<SafeClass>.json
#    (e.g. 1a2b3c4d-AttributeError.json),可读不靠 hash 猜。
./scripts/lca-ops journal exceptions "$LATEST"
./scripts/lca-ops journal exceptions "$LATEST" --grep AttributeError
./scripts/lca-ops journal exceptions "$LATEST" --json | jq '.records[0].payload'
# Last-resort:FALLBACK.log 只在主 ledger + exceptions index 都写不进去时出现,
# 是 TracingFileSink 的兜底(进程级最后一道)。
[ -f traces/runs/"$LATEST"/FALLBACK.log ] && cat traces/runs/"$LATEST"/FALLBACK.log

# 4. 失败原因投影(仅 run 失败时有意义)
./scripts/lca-ops explain "$LATEST"

# 5. step 树 / 因果链 / narrative(早期失败的 run 可能 journal.json 不存在,正常)
./scripts/lca-ops journal steps "$LATEST" 2>/dev/null
./scripts/lca-ops journal narrative "$LATEST" 2>/dev/null
```

**口语映射**(agent 看到这些词就直接走流程,不要先分析语义):

| 用户说 | 走的流程 |
|---|---|
| "最新一次 run" / "刚才那个" / "上次" / "最近" | 上面 5 步全套**含 3.5 exceptions** |
| "分析一下这次" / "看看发生了什么" | 上面 1-3 + **3.5 exceptions** |
| "为啥这次失败" / "这次出错了" / "traceback 呢" | 上面 1-2 + **3.5 exceptions**(`lca-ops journal exceptions` 拿 traceback) + 4 |
| "理解一下过程" / "走了一遍啥逻辑" | 上面 1 + 3 + 5 |
| "DSH 风格轨迹" / "给我个 HTML" | 加 `./scripts/lca-ops journal trajectory "$LATEST"` |
| "模型都做了啥" / "调了啥工具" | `./scripts/lca-ops trace "$LATEST" --focus llm\|tools\|delegation`(`--focus` 是 trace 的选项;`journal logs` 不支持) |
| "给我个像 journal 那样的树视图" / "人读 trace" | `./scripts/lca-ops journal trace`(**默认 --human**:树缩进 + Δms + payload 原文,默认最新 run) |
| "所有 traceback 一刀命中" / "grep 异常类" | `./scripts/lca-ops journal exceptions "$LATEST" --grep AttributeError` |

**取 run_id 的硬规则**:永远 `jq -r .run_id traces/latest.json`,**不要** ls、find、按 mtime 排序 —— pointer 文件是 SSOT。

**traceback 必落盘**(ADR-2026-09-03):`exception.caught` EP 必写 `<run_id>.exceptions.jsonl`(专用索引,TracingFileSink 三道防线,IOError 不抛)。失败兜底走 `<run_id>.FALLBACK.log` + structlog。grep 一行: `jq -r 'select(.payload.exception_class=="X")' traces/runs/<id>/<id>.exceptions.jsonl`。

## 现有可观测/调试能力

### 一次性诊断

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
