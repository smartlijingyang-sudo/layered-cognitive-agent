# DSH (DeepSeek Harness) — sandbox-user 侧运行时

DSH 是 DeepSeek 的 Agent 运行时。LCA 把 DSH 执行委托给 sandbox-user 侧的 daemon，
和 CLI 工具走同一条 transport 路径。SDK 装在共享 venv（`/opt/lca/venv`）里。

## 架构

```
gateway (MachineDshRuntime)
  │ write_files → runner.py + config.json
  │ runCommand  → python3 runner.py config.json
  │               └─ DSH SDK (sandbox-user venv)
  │                  ├─ events → .lca/dsh/events.jsonl
  │                  └─ result → stdout
  │ readFile    ← events.jsonl
  ▼
DshTurnDriver → Journal → LobeHub
```

| 路径 | 作用 |
|---|---|
| `deploy/dsh/install-dsh-sdk.sh` | 安装 SDK 到 sandbox-user venv |
| `deploy/dsh/requirements-dsh.txt` | Python 依赖（pin 到 rc6） |
| `lca/layer0_infra/dsh/machine_runtime.py` | Gateway 侧：生成 runner、驱动 transport |

## 安装

```bash
# 首次 / 升级 SDK
./deploy/dsh/install-dsh-sdk.sh

# 或通过 ops
./scripts/lca-ops dsh ensure
```

SDK 装在 `/opt/lca/venv`，daemon 的 `buildExecEnv()` 会自动把 venv/bin 加到 PATH。

## Ops 集成

```bash
./scripts/lca-ops status    # 检查 SDK 是否安装
./scripts/lca-ops heal      # 自动安装缺失的 SDK
./scripts/lca-ops dsh ensure  # 单独 ensure DSH
```

## 升级 SDK

1. 更新 `requirements-dsh.txt` 中的版本号
2. 重新安装：`./deploy/dsh/install-dsh-sdk.sh`

## 为什么不在 gateway 侧装 SDK

DSH 执行的是 sandbox-user 的工作空间，和 CLI 工具同一信任边界。
SDK 跑在 sandbox-user venv 里，gateway 只负责编排（写 runner → 执行 → 读结果），
不 import 任何 DSH 代码。
