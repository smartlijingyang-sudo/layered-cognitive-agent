# LobeHub UI（LCA 内置，独立副本）

本目录 **与 `/home/lichao/lobehub` 无任何关系**，是 LCA 项目自维护的 LobeHub 副本。

## 目录（均在 LCA 仓库根下）

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 可运行的 LobeHub 源码（gitignore，由脚本生成） |
| `.lobehub-upstream/` | 官方 git 浅克隆缓存（gitignore） |
| `.lobehub-stack/` | gateway 进程 pid / 日志（gitignore） |
| `deploy/lobehub/.env.lca` | 本地 env 模板（**提交进 git**） |

## 首次拉取 v2.2.13

```bash
./scripts/sync_lobehub_ui.sh
```

从 `https://github.com/lobehub/lobehub.git` 拉取 tag `v2.2.13`，写入 `lobehub-ui/`。

## 启动

```bash
./scripts/start_lobehub_stack.sh dev
```

`dev` / `sync` 会自动：

1. 从官方 tag 同步 `lobehub-ui/`（若需要）
2. **自动打 LCA 补丁**（`deploy/lobehub/patch-lca-qwen-defaults.sh` + `patch-lca-integration.py`）
3. 启动 gateway（**Python 代码比进程新时自动重启**）
4. 启动 LobeHub dev

若只改了 gateway Python，可：

```bash
./scripts/start_lobehub_stack.sh restart-gateway
```

若只改了 LCA 补丁脚本、未 sync 官方 UI：

```bash
python3 deploy/lobehub/patch-lca-integration.py   # 或 patch-lca-qwen-defaults.sh
# LobeHub dev 需手动刷新 / 重启 dev 进程
```

`dev` 启动前会自动停止占用 `:3010` 的旧 LobeHub/Next 进程（含 `.next/dev/lock`）。
若本机已有 `lobe-postgres(:25432)` / `lobe-minio(:19000)` 等容器，脚本会自动跳过 docker compose。
若需保留已有 dev 实例：`LOBE_REUSE_DEV=1 ./scripts/start_lobehub_stack.sh dev`

停止全部：`./scripts/start_lobehub_stack.sh stop`

## 版本锁定

同步后在 `lobehub-ui/.lca-origin.json` 可查看来源 tag 与同步时间。
