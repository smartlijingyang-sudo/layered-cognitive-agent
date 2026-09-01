# lca-ops CLI Reference — ADR-0065 §六 / PR-9

## 顶层子命令

| 命令 | 用途 |
|---|---|
| `status` | 全站状态(kernel_serve / infra / lobehub / daemon / onlyboxes) |
| `heal` / `stop` | 外部服务(`infra/lobehub/daemon`)的生命周期自愈与停止;`restart`/`compose`/`dev` 已删;LCA 进程入口是 `uv run python -m lca_kernel serve`,由 `lca_kernel.lifecycle` 守护 |
| `logs` | journal 事实流(可加 `--replay` 从 materialization 重放) |
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
