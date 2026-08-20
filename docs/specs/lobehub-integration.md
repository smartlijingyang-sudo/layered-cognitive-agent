# LobeHub UI 集成

用 LobeHub 官方 UI（v2.2.13）替换自研 `web/`。聊天走 Run Live；标题等小请求走 OpenAI 兼容面。

协议与渲染链路： [run-live.md](run-live.md)。补丁清单： [CUSTOMIZATIONS.md](../../deploy/lobehub/CUSTOMIZATIONS.md)。

## 架构

```text
Browser → LobeHub v2.2.13 (lobehub-ui/, bun run dev :3010)
              │ executeClientAgent(solo|team|auto)
              │   → runLcaJournal → finishLcaChat
              │ POST /lca-api/runs          →  POST /runs
              │ GET  /lca-api/runs/{id}/live
              ▼
LCA Gateway (:8765)
              │ runs/api.py + runs/execute.py
              ▼
LCA Agent/Team
              │ record() → jsonl + LiveTail
```

模型选择器只暴露 `solo` / `team` / `auto`。真实 LLM 由 gateway 解析。两条路不相交：

- `POST /runs` + `GET /runs/{id}/live`：Agent 干活
- `POST /v1/chat/completions` / embeddings / responses：管家面（标题、话题、小助手）。直连上游，不开 Run。
- `/presence/*` + `/console/*`：本机 host sidecar（在线表 + 人用终端）。
- 本机执行面使用设备上报的真实工作根（`HostRuntimeSettings`：`LCA_HOST_USER` / `LCA_HOST_ROOT`，默认 `/home/<user>`）。
  沙箱执行面使用镜像契约 `SANDBOX_MOUNT_ROOT`（`/mnt/data`）。两套路径不互译。
  离线回落 Onlyboxes。准备环境：`./scripts/lca-ops daemon ensure`。

联网搜索（ADR-0053）：`TAVILY_API_KEY` 已配 → `web_search`；否则 Qwen `enable_search` 兜底。搜索结果同样经 Journal `ToolStarted` / `ToolInvoked` 投影，不另开协议。

## 快速开始

```bash
./scripts/sync_lobehub_ui.sh   # 拉取 v2.2.13 到 lobehub-ui/
./scripts/lca-ops dev          # infra + gateway + LobeHub + daemon
```

环境模板：`deploy/lobehub/.env.lca` → 自动复制为 `lobehub-ui/.env`

## 目录说明

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 官方 v2.2.13 源码（gitignore） |
| `.lobehub-upstream/` | 官方 git 克隆缓存（gitignore） |
| `scripts/sync_lobehub_ui.sh` | 拉取并 rsync 官方 release |
| `lca-ops.yaml` | 栈配置 SSOT：端口、路径、服务 |
| `lca/layer0_infra/ops/` | 编排实现 |
| `scripts/lca-ops` | 唯一入口：status / heal / logs / dev |
| `deploy/lobehub/.env.lca` | LobeHub 本地 env 模板 |
| `gateway/openai_shim.py` | OpenAI 兼容 HTTP 面（标题 / embeddings / responses） |
| `gateway/runs/` | Run Live：开工、Journal SSE、快照、取消、HIL |
| `deploy/lobehub/patches/runtime/lca_run_driver.py` | 前端投影补丁 |

升级：`LOBEHUB_RELEASE=v2.2.14 ./scripts/sync_lobehub_ui.sh`
