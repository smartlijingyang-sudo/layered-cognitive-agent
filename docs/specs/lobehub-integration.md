# LobeHub UI 集成

用 LobeHub 官方 UI（v2.2.13）替换自研 `web/`。聊天走 Agent 命令 `POST /runs` + 观察 `GET /runs/{id}/live`；标题等小请求走 OpenAI 兼容管家面，不开 loop。

协议与渲染链路： [run-live.md](run-live.md)。补丁清单： [CUSTOMIZATIONS.md](../../deploy/lobehub/CUSTOMIZATIONS.md)。命令面：[ADR-0100](../adr/0100-chat-command-is-agent-run.md)。**Tool 字段契约： [ADR-0102](../adr/0102-tool-render-contract.md) —— 每个 Tool 在 Python 端声明 `RenderContract`，codegen 出 TS，前端 `projectToolCall()` 是唯一投影函数**。

## 架构

```text
Browser → LobeHub v2.2.13 (lobehub-ui/, bun run dev :3010)
              │ runLcaJournal / finishLcaChat
              │（注入自 lca_run_driver 补丁）
              │ POST /runs              202 {run_id, live_url}
              │ GET  /runs/{id}/live    四事件
              ▼
LCA Gateway (:8765)
              │ create_and_dispatch
              │ UI 编码器 → reasoning | text | tool | done
              ▼
LCA Agent/Team
              │ record() → jsonl
```

选择器只暴露 mode：`solo` / `team` / `auto` / `cordis-creator`。真实 LLM 由 profile 解析。

- `POST /runs`：开工。一次回车 = 一次 Run。
- `GET /runs/{id}/live`：画布。四种 UI 事件，不是 Journal，不是三通道。
- `/v1/chat/completions` / embeddings / responses：管家面。直连上游，不开 Agent Loop。
- cancel / answer / profile / doctor：命令与诊断。
- `/presence/*` + `/console/*`：本机 host sidecar（在线表 + 人用终端）。
- 本机执行面使用设备上报的真实工作根（`HostRuntimeSettings`：`LCA_HOST_USER` / `LCA_HOST_ROOT`，默认 `/home/<user>`）。
  沙箱执行面使用镜像契约 `SANDBOX_MOUNT_ROOT`（`/mnt/data`）。两套路径不互译。
  离线回落 Onlyboxes。准备环境：`./scripts/lca-ops daemon ensure`。

联网搜索（ADR-0053）：`TAVILY_API_KEY` 已配 → `web_search`；否则 Qwen `enable_search` 兜底。搜索结果经 Journal `ToolStarted` / `ToolInvoked` 记账，聊天流走 `event: tool`，不另开协议。

## 快速开始

```bash
./scripts/sync_lobehub_ui.sh   # 拉取 v2.2.13 到 lobehub-ui/
./scripts/lca-ops lobehub ensure   # 同步源码 / 打补丁 / 写 .env / bun install
./scripts/lca-ops heal             # 拉起 infra / lobehub / daemon / kernel_serve
```

环境模板：`deploy/lobehub/.env.lca` → 自动复制为 `lobehub-ui/.env`

## 目录说明

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 官方 v2.2.13 源码（gitignore） |
| `.lobehub-upstream/` | 官方 git 克隆缓存（gitignore） |
| `scripts/sync_lobehub_ui.sh` | 拉取并 rsync 官方 release |
| `lca-ops.yaml` | 栈配置 SSOT：端口、路径、服务 |
| `lca/infrastructure/cli/` | 编排实现(services + commands + steps) |
| `scripts/lca-ops` | 唯一入口：status / heal / stop / logs / inspect-tree / dump-profile / debug / diagnose / provision |
| `deploy/lobehub/.env.lca` | LobeHub 本地 env 模板 |
| `lca/plugins/transport/webserver/handlers/runs/` | LCA API:`POST /runs`、`GET /runs/{id}`、`GET /runs/{id}/live`、`/v1/chat/completions` |
| `deploy/lobehub/patches/runtime/LcaRunDriver.ts` | LobeHub 侧补丁:`POST /lca-api/runs` → SSE live loop(注入 LcaRunDriver 到 transports) |

升级：`LOBEHUB_RELEASE=v2.2.14 ./scripts/sync_lobehub_ui.sh`
