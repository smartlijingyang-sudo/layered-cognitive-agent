# lca-ops CLI Reference — ADR-0065 §六 / PR-9

## 顶层子命令

| 命令 | 用途 |
|---|---|
| `status` | 全站状态(kernel_serve / infra / lobehub / daemon / onlyboxes) |
| `heal` / `stop` | 生命周期(`restart` 已删;kernel 进程由 `kernel_serve` 自管,`heal` 会自愈) |
| `logs` | **(已重命名)** → `journal logs`(默认 tail 最新 run 的 spine SSOT `events.jsonl`;`-r <run_id>` 离线回放;`-v` 展开 payload + error 通道 traceback) |
| `inspect-tree <profile.yaml>` | 解析后的插件树 + capability 图 |
| `dump-profile <profile.yaml>` | 展开 bundle + patch 的 entries |
| `diagnose <alias>` | 内置诊断:`model_not_seen` / `loop_stuck` / `memory_poisoned` / `approval_rejected` |

## observability 子集

| 命令 | 用途 |
|---|---|
| `cost <run_id> [--by model\|phase\|tool]` | 按 pricing_ref 重算 cost |
| `trace <run_id> [--format mermaid]` | trace 报告 |
| `explain <run_id>` | 失败因果链 |
| `graph <run_id>` | 插件交互图 |
| `minimal-repro <run_id>` | 最小复现包 |
| `diff-runs <a> <b> --step N` | 两次 run 同 step 差异 |

## diagnose alias 输出格式

```json
{
  "alias": "loop_stuck",
  "error_codes": ["loop_stuck", "loop_oscillating", "loop_max_steps"],
  "hint": "检查 step 数与 oscillation 模式;增大 max_steps 或调整 reasoner prompt。"
}
```

## logs --replay

从 `materializations/<generator-id>/<generator-version>/` 重放历史
materialization;不重新生成,而是验证现有视图与 ledger 一致。

> **2026-09-02 修正(ADR-2026-09-02-i17-stream-align §A)**:顶层 `logs` 子命令已删,
> 改为 `lca-ops journal logs` (按 spine SSOT 直读,无 envelope v2 渲染层)。
> `materializations/` 重放由 `lca-ops journal trace <run_id>` 子命令接管(PR-9 I17)。

## journal logs(取代顶层 `logs`)

```sh
# 默认: tail 最新 run 的 spine SSOT(traces/runs/<id>/events.jsonl)
lca-ops journal logs

# 离线回放指定 run
lca-ops journal logs -r run_a4248231a677

# 展开 payload + error 通道 traceback(exc_type/exception_message/traceback_text/cause_chain)
lca-ops journal logs -v -r run_a4248231a677
```

按 `channel` 分桶打印:`control`(节点生命周期)/ `fact`(reducer 写入) /
`error`(失败 + traceback)。`channel=error` 事件在 verbose 模式下额外展开
`exc_type` / `exception_message` / `traceback_text` / `cause_chain`,由
`wrap_instrument._exception_payload` 注入(ADR-2026-09-02-i17-stream-align §B)。

## Run 路径查找顺序（`_resolve_journal_artifact`, ADR-0167.1 D6）

CLI 在不显式 `--journal` / `--jsonl` 时按下列顺序查找 run artifact：

```text
1. --journal <path> (显式参数, 任意 caller-provided path)
2. traces/runs/<id>/journal.json         # lca.journal/3.1 step-tree 主存储 (ADR-0164 + ADR-0167 D3)
3. traces/runs/<id>/events.jsonl          # EventSpine SSOT (ADR-0165.1, ADR-0167 D1)
4. traces/runs/<id>/journal.raw.jsonl     # legacy replay stream (回放兜底)
5. traces/runs/<id>.journal               # legacy per-trace_id layout
6. traces/lca_journal.jsonl                # 全局 legacy stream
```

`lca-ops trace <run_id>` / `lca-ops explain <run_id>` / `lca-ops minimal-repro <run_id>` /
`lca-ops journal steps <run_id>` 全部走这条 lookup。`journal.json` 缺失但 `events.jsonl`
存在时，CLI 会基于 `events.jsonl` re-derive step tree（Re- 协议见 ADR-0167 D10）。

doctor 的 `_doctor_journal_path` 同样优先 `journal.json` → `events.jsonl` →
否则 H2 broken。

## 例子

```sh
# 标准 trace (自动找到 journal.json / events.jsonl)
lca-ops trace run_abc123

# 显式指 events.jsonl (off  /  partial profile 下)
lca-ops trace run_abc123 --jsonl traces/runs/run_abc123/events.jsonl

# debug-run: 看一次 8-section 诊断, spine.events + journal 双源都能识别
lca-ops debug-run run_abc123
```
