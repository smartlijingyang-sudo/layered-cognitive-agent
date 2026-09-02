# lca-ops CLI Reference — ADR-0065 §六 / PR-9

## 顶层子命令

| 命令 | 用途 |
|---|---|
| `status` | 全站状态(kernel_serve / infra / lobehub / daemon / onlyboxes) |
| `heal` / `stop` | 生命周期(`restart` 已删;kernel 进程由 `kernel_serve` 自管,`heal` 会自愈) |
| `journal logs` | **canonical** — tail 最新 run 的 spine SSOT `events.jsonl`;`-r <run_id>` 离线回放;`-v` 展开 payload + offloaded sidecar traceback |
| `logs` | (alias for `journal logs`;保留避免外部脚本/ CI 拿到 `No such command`) |
| `inspect-tree <profile.yaml>` | 解析后的插件树 + capability 图 |
| `dump-profile <profile.yaml>` | 展开 bundle + patch 的 entries |
| `diagnose <problem>` | 内置诊断(连字符):`model-not-seen` / `loop-stuck` / `memory-poisoned` / `approval-rejected` |

## observability 子集

| 命令 | 用途 |
|---|---|
| `cost <run_id> [--json] [--jsonl PATH]` | 按 pricing_ref 重算 cost |
| `trace <run_id> [--focus all\|llm\|tools\|delegation] [--depth N]` | trace 报告; mermaid 视图走 `graph-run <run_id>` |
| `explain <run_id>` | 失败因果链 |
| `graph-run <run_id>` | Mermaid 插件交互图(原 `trace --format mermaid` 已删) |
| `minimal-repro <run_id> [--json] [--jsonl PATH]` | 最小复现包 |
| `diff-runs <a> <b> --step N` | 两次 run 同 step 差异 |

## diagnose alias 输出格式

```json
{
  "problem": "loop-stuck",
  "error_codes": ["loop-stuck", "loop-oscillating", "loop-max-steps"],
  "hint": "检查 step 数与 oscillation 模式;增大 max_steps 或调整 reasoner prompt。"
}
```

> **2026-09-02 修正(ADR-2026-09-02-i17-stream-align §A)**:
> 顶层 `logs` 子命令曾被删除,改为 `lca-ops journal logs`(按 spine SSOT 直读,无 envelope v2 渲染层)。
> 现已重新提供顶层 `logs` 作为 `journal logs` 的 alias —— 外部 CI / 仪表盘 / 老脚本可以无缝使用,
> 标志、副作用、查找顺序均与 `journal logs` 一致。

## journal logs(取代顶层 `logs`,但顶层 alias 仍在)

```sh
# 默认: tail 最新 run 的 spine SSOT(traces/runs/<id>/events.jsonl)
lca-ops journal logs

# 离线回放指定 run
lca-ops journal logs -r run_a4248231a677

# 展开 payload + error 通道 traceback(exc_type/exception_message/traceback_text/cause_chain)
lca-ops journal logs -v -r run_a4248231a677

# 等价的顶层调用
lca-ops logs -v -r run_a4248231a677
```

按 `channel` 分桶打印:`control`(节点生命周期)/ `fact`(reducer 写入) /
`error`(失败 + traceback)。`channel=error` 事件在 verbose 模式下额外展开
`exc_type` / `exception_message` / `traceback_text` / `cause_chain`,由
`wrap_instrument._exception_payload` 注入(ADR-2026-09-02-i17-stream-align §B)。

> **offloaded sidecar**(>=4 KB 的 error 事件):`events.jsonl` 会写入一行
`{"execution_point": ..., "offloaded": "<sha256>"}`, 真正的 payload 在 `<sha256>.json`。
`-v` 模式会自动读 sidecar 并展示 traceback,无需 `cat` 单独文件。

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
