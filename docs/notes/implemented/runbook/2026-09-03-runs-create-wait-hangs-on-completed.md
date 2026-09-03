# Agent Note: `runs create --wait` 把 "completed" run 当成永不终止

Status: implemented

> **Superseded by**: [观测面 SSOT 全量收口与约束保证](../seam/2026-09-03-observation-ssot-registry.md)(root note, implemented 2026-09-03)。本 note 作为 BUG 现场诊断证据保留;修法已并入根 note PR-1~7。

## Problem

`lca-ops runs create --wait` 在 run 实际已完成时仍持续 polling 到 300s 超时,污染 `traces/runs/<id>/run_<id>.spine.jsonl` 尾部塞满 `transport.route.enter/exit` 噪音(本次观察:run 7 秒关闭,CLI 仍写 351 个 transport.route 事件),且 debug agent 在 `await wait` 时拿不到终端 verdict 就要降级到直接读 manifest,违反 `AGENTS.md §6` "唯一入口 runs create"的协议契约。

证据:

- `traces/runs/run_365ad8d3c2c0/manifest.json`:`status="completed"`、`outcome="completed"`、`closed_at=1788409105.787`(12:18:25 创建后 7 秒关闭)。
- `curl http://127.0.0.1:8765/runs/run_365ad8d3c2c0/doctor` 返回 `{"status":"unknown","outcome":"completed",...}`。
- `lca/infrastructure/cli/commands/runs.py:152` 把 terminal 集硬编码为 `{"success", "failed", "cancelled", "paused"}`,**不包含 `"completed"` / `"unknown"`**。
- 同 run 的 `run_<id>.spine.jsonl` 371 行,其中 `transport.route.exit` × 114 是 CLI polling 反复触发的副作用,会污染后续 `journal trace --human` 的可读性。

根因:

- `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` `GET /runs/{id}/doctor` 把 manifest 的 `status="completed"` 映射成 `status="unknown"`(可能因 doctor 内部有 `summary` / `outcome` 二选一,某些代码路径默认 unknown)。
- CLI `--wait` 不知道 `unknown` 是 terminal,继续 polling。

## Proposal

1. 在 CLI `--wait` 的 terminal 集中加入 `"completed"` 与 `"unknown"`(后者视为 `failed` 兜底,理由:`status=unknown` + `outcome=completed` 是当前事实;`status=unknown` + `outcome≠completed` 应被记 `failed`)。
2. 在 doctor 端点统一 `status` ↔ `outcome` 语义:写一个 `terminal_status_from_manifest(manifest) -> str` 助手,返回 `"success" | "failed" | "cancelled" | "paused" | "completed"`,并把 `manifest.status` 当 truth source,doctor `status` 字段直接转发。`unknown` 只在 manifest 缺失时返回。
3. 加 lint / 测试守护:`scripts/check_run_debug_sync.py` 加一条 "doctor status 集 = CLI `--wait` 终端集 + manifest status 集",两边不齐就 fail。

## Wire contract

- `GET /runs/{id}/doctor`:`status` 字段值集合新增 `"completed"`,保留 `"unknown"` 仅作为 manifest 缺失时的兜底。
- `lca.infrastructure.cli.commands.runs` `--wait` 终端集:`{"success", "failed", "cancelled", "paused", "completed"}`;`unknown` 计为 `failed`。

## Alternatives considered

### Why not 在 kernel 关闭 run 时强制写 `status="success"`?

否决:kernel 不知道 run 是否真"成功"。run outcome 由 doctor 判定,manifest 是 SSOT;kernel 不应承担 outcome 判断。

### Why not 把 --wait 的 polling 改为订阅 SSE?

否决:CLI 是无状态请求端,SSE 需要持久连接管理、断线重连、多 client 协调 —— 与 `urllib.request.urlopen` 的 10s 超时简单模型不兼容,改动面铺到整个 journal live 通道。增量修改 scope 内只动 polling 终态判定,scope 守恒。

### Why not 让 CLI 直接读 `traces/latest.json` 拿 status?

否决:CLI 必须 verify status from kernel(避免本地 traces 已被 roll 走的 stale 状态);HTTP 端点是契约。

## Acceptance criteria

- 给定 `traces/runs/run_365ad8d3c2c0/`,`curl /runs/<id>/doctor | jq .status` 返回 `"completed"`(不是 `"unknown"`)。
- 同一 run `lca-ops runs create --wait --user-text ...` 在 < 30 秒内退出(无须等到 300s)。
- 终端集测试:`tests/cli/test_runs_create_wait.py` 覆盖 `completed` / `success` / `failed` / `cancelled` / `paused` 五个 terminal 值。

## Risks

- 把 `"unknown"` 终端化为 `failed` 可能把当前 silent run 也算 failed — 但 `unknown` 在新 doctor 实现里只在 manifest 缺失时出现,而 manifest 缺失代表 run 早已 GC,合理。
- 某些下游 consumer 可能依赖 `status="unknown"` 的特殊含义(比如 batch 监控脚本看到 unknown 就报警),需要先 grep 一下:
  ```bash
  rg '"unknown"' lca/ scripts/ docs/ tests/ --type py --type md
  ```
  若有,同 PR 改。

## Related

- `lca/infrastructure/cli/commands/runs.py:152` — CLI 终态集硬编码。
- `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` — doctor status 映射。
- `lca/plugins/transport/webserver/handlers/runs/doctor/doctor.py` — doctor 实现,需统一 manifest 是 status 唯一源。
- `scripts/check_run_debug_sync.py` — 现成的同步门禁,可扩展。
- `docs/debug/run-debug-guide.md` Step 1 — "如果 status=passed → done" 的语义在当前实现下永远不命中,文档与实现漂移。