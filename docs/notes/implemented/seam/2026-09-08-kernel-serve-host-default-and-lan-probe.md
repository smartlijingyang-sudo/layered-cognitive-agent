# Agent Note: kernel_serve host default unification + post-spawn LAN probe

Status: implemented

## Problem

`cli/commands/kernel/kernel.py` 的 typer Option default 与 `cli/config/config.py:KernelServeConfig.host` 的 SSOT 默认值长期不一致(`127.0.0.1` vs `0.0.0.0`)。`KernelServeService._spawn` 只对 loopback `/health` 探活,Next.js proxy 走 LAN 不可达时仍报 healthy,前端 `/lca-api/*` 全部 500。

## Decision

1. typer Option default 引用模块级 `_LAN_BIND_DEFAULT = "0.0.0.0"` 常量,与 `KernelServeConfig.host` 字面值合并为一处。`cli/services/kernel/serve.py` 同样把 `{"0.0.0.0", "::"}` 抽到 `_BIND_ALL_HOSTS` 常量。
2. `_spawn` 在 loopback `/health` 通后,如果 `host ∈ _BIND_ALL_HOSTS`,额外 GET `LCA_GATEWAY_PUBLIC_URL` / `OPENAI_PROXY_URL` 解析出的 `<host>:<port>/health`。不可达返 `False` 让 state 报"host 不匹配",不静默放过。
3. `tests/infrastructure/cli/test_kernel_serve_probe_lan.py` 覆盖 unset / healthy / unreachable / loopback-equal / legacy-env 五条路径。

## Alternatives considered

**只改 typer default,不加 LAN 探活**。表面上看够了,但 spawn 后只验证 loopback 的现状没变,Next.js proxy 改 LAN URL 时仍静默踩坑。loopback-OK 不是 end-to-end OK。
**改 KernelServeConfig.host → 127.0.0.1**。让命令/配置一致,代价是 Next.js proxy 默认要配 loopback,而生产部署多 LAN,改向会让现有部署全坏。不选。
**只在 spawn 命令里写 `bash -c '... && curl LAN/health'`**。把 LAN 探活塞进 shell 包裹里。代价是测试不可 mock(curl 是外部进程)、CLI 调用栈里看不到诊断信息。不选,保持 Python 内探活。

## Consequences

- Spawn 后 30s 内如果 LAN 路由不通(防火墙 / 容器网络),`lca-ops heal` 会显式打印 `[FAIL] ... Set LCA_KERNEL_HOST=0.0.0.0 or fix the LAN route.` 而不是回退 loopback-OK 假象。
- Operator 不再需要记住 `--host 0.0.0.0` vs `--host 127.0.0.1` 差异;typer 提示文本现在写明两者用途。
- S104 ruff 警告(S104: `0.0.0.0` 字面量)出现于两个新文件,均以 `# noqa: S104 — see KernelServeConfig` 注释说明 bind-all 是有意为之,留给后人不误删。

## Verification

- `ruff check` PR-A 改动的 2 个文件:0 error
- `uv run pytest tests/infrastructure/cli/test_kernel_serve_probe_lan.py`:5 passed
- `uv run pytest tests/infrastructure/cli/test_lobehub_child_env_lca.py`:4 passed(未触及)
- 端到端:`./scripts/lca-ops status --json` kernel_serve running on `0.0.0.0:8765`,loopback + `10.36.6.252:8765` 双可达
- 浏览器:UI sendMessage → `run_id` 真实创建 → kernel `phase_started`

## Also observed (out of scope of this PR)

- **journal.json H3 duplicate step_id**:real run `run_20951da435a6` 的 `journal.json` 含 `step_index=[1,2,3,4,5]` 但 `step_id=[step-001,step-001,step-002,step-003,step-004]`,触发 doctor `duplicate step_id: ['step-001']`。直接跑 `fold_step_tree` over spine.jsonl 只产 4 step,JournalDocumentWriter 写盘后是 5 step。怀疑 Session snapshot + spine ledger 双流在 `StepTreeFoldDeriver._iter_events` 合并顺序与 fold 假设不一致。**未修**,留 follow-up。
- **`RuntimeError: spine_port_append: no Session hook bound for execution_point='exception.caught'`** — kernel 启动后某路径抛的 unhandled exception。**未修**,留 follow-up。

## Files touched

- `lca/infrastructure/cli/commands/kernel/kernel.py` — typer default,`_LAN_BIND_DEFAULT` 常量
- `lca/infrastructure/cli/services/kernel/serve.py` — `_probe_proxy_lan`,`_BIND_ALL_HOSTS` 常量,模块 docstring
- `tests/infrastructure/cli/test_kernel_serve_probe_lan.py` — 新建,5 个 case

## Commit

`556bc3d8 fix(cli): kernel_serve host default → 0.0.0.0 + post-spawn LAN probe`
