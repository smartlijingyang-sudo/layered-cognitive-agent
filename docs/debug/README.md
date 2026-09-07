# Debug & Observability

LCA 的"高级工程师自助定位"基础设施入口。所有 debug / observability / 诊断能力按 Plugin 模型落地(ADR-0122)。

## 入口

- **[run-debug-guide.md](./run-debug-guide.md)** — `lca-ops debug-run <run_id>` 的完整 8 步 SOP + **Step 0b/0c**「后端 5xx 怎么看日志」 + 每步 `WHY / DO / OUTPUT / NEXT / FAIL` + 工具对照表 + 常见失败模式 → 命令映射。命令路径由 [`scripts/check_run_debug_sync.py`](../../scripts/check_run_debug_sync.py) 与 CLI 注册表同步。
- **`.agents/skills/lca-debug-run/SKILL.md`** — Agent 触发入口。口语映射 + 5 步流程概览 + bug-vs-debrief 决策 + 升级到 `lca-code-review` 的证据包交接。人类通常不需要这一份。
- **`AGENTS.md` §6** — 命令矩阵指针 + 服务问题分流(不是 run 问题)。

## 后端 5xx 的快速分流

`lca-ops status` 报 `kernel_serve: healthy`(`/health` 200),但某个 endpoint 返回 5xx。这是最高频的"接口挂了但服务看起来正常"场景,按下面顺序 30 秒定位:

| 症状 | 第一步 | 第二步 | 第三步 |
|---|---|---|---|
| **浏览器抓包:5xx 但 status 健康** | `curl -i -X POST -d '{...}' http://127.0.0.1:8765/<path>` 复现 | `lca-ops logs \| tail -120` 看 `/tmp/lca-kernel.log` | 在该日志里 grep `Traceback` / `Exception` / `<ExceptionName>` |
| **lobehub 网关层就 5xx(看不到 kernel log)** | `lca-ops journal logs lobehub \| tail -80` | 在 `.lca-ops/lobehub.log` 里 grep `<path>` | 多数情况是 lobehub → kernel 路由问题(`LCA_GATEWAY_PUBLIC_URL` 错) |
| **拿到 run_id,要看 run 内部失败** | `LATEST=$(ls -1t traces/runs \| head -1)` | `lca-ops debug-run "$LATEST"` | 走 [run-debug-guide.md](./run-debug-guide.md) Step 1–7 |
| **kernel 进程在但日志路径变了** | `pid=$(pgrep -f 'lca_kernel serve' \| head -1); ls -l /proc/$pid/fd/1` | 读 symlink 指向的实际 log(可能是手动启动留下的) | 若空 → 进程 stdout 被 redirect 到 nohup/launcher,加 `-vv` 重启 |

> **关键提醒:`traces/runs/<id>/kernel.log` ≠ `/tmp/lca-kernel.log`。** 前者是某个 run 的"收尾失败兜底行"(多数 run 没有);后者是 kernel 进程级 stdout/stderr,所有的 Python traceback、`INFO: POST /runs HTTP/1.1 500`、`anomaly_detector:` 都在这里。5xx 排查**永远先看 `/tmp/lca-kernel.log`**(`lca-ops logs` 是 alias)。

### 后端 5xx 案例索引(已知模式)

| 模式 | 关键字(grep `/tmp/lca-kernel.log`) | 根因 | 修复 |
|---|---|---|---|
| JWT 私钥缺失 → `500` | `InvalidTokenError: LCA_JWT_SECRET not set` / `JwtSecretUnconfiguredError` | webserver handler 直接读 `os.environ["LCA_JWT_SECRET"]` 而未走 Profile `from_env` 注入 | 见下文 [POST /lca-api/runs 500 → jwt_secret_unconfigured](#post-lca-api-runs-500--jwt_secret_unconfigured) |
| Capability 越权 → `403` / `CapabilityGrantExceededError` | `capability grant exceeded` | 命令超出 Profile 授权范围 | 检查 Profile `auth.grants` 与 command `envelope.requires` |
| C2 / C10 违例(认知直写世界) | `Reducer.single_writer` / `body_only_execution_path` | 新代码绕过 Reducer / 绕过 Body | 看 traceback 顶部 frame → 退回到现有 seam |
| lobehub → kernel ECONNREFUSED | `connect ECONNREFUSED 10.36.6.252:8765`(出现在 `.lca-ops/lobehub.log` 而非 kernel log) | lobehub 的 `LCA_GATEWAY_PUBLIC_URL` 指向了 kernel 不监听的接口 | `cat /proc/<lobehub_pid>/environ \| tr '\0' '\n' \| grep LCA_GATEWAY`;重启 lobehub 或修正环境 |

完整新增案例请在本节追加;新案例的最小要求:`关键字 + grep 命令 + 修复路径`。**禁止**仅描述症状而不写 grep 关键字。

## POST /lca-api/runs 500 → jwt_secret_unconfigured

`lca-ops status` 可能显示 `kernel_serve: healthy`(`/health` 200),但 UI 一发
对话立即 500,日志里只有一段 traceback,看起来"服务正常,接口挂了"。原因
100% 是 kernel 没拿到 JWT 签名私钥——见下文。

### 复现

```bash
# 直接打 kernel(不走 lobehub)
curl -sS -X POST -H 'Content-Type: application/json' \
     -d '{"messages":[{"role":"user","content":"hello"}]}' \
     -i http://127.0.0.1:8765/runs
# 期望修复后:HTTP/1.1 202 Accepted
# 修复前:HTTP/1.1 500 Internal Server Error + body "Internal Server Error"
```

### 关键字

| 来源 | 关键字 |
|---|---|
| Kernel 日志(`/tmp/lca-kernel.log` 或 `.lca-ops/kernel-serve.log`) | `InvalidTokenError: LCA_JWT_SECRET not set` / `JwtSecretUnconfiguredError` |
| `lca-ops debug-run <run_id>` section 7(异常解释) | "JWT secret missing — see docs/debug/README.md#post-runs-500" |
| HTTP 响应 | 修复前 500 / 修复后 dev-mode=202 或生产 from_env=202;缺 PEM 返回 503 + `{"error":{"code":"jwt_secret_unconfigured",...}}` |

### 修复路径

- **生产**:Profile 加 `jwt.private_pem: {from_env: LCA_JWT_SECRET}`(以及 `jwt.public_pem: {from_env: LCA_JWT_PUBLIC_KEY}` 给 WS verify 用),并把 PEM 写到宿主机环境。
- **开发**:Profile 设 `jwt.dev_mode: true`,启动期自动生成 keypair;每次 kernel 重启 keypair 会变,跨重启的 WS 会话需重连。**禁止**多副本部署用 dev_mode。
- `lca-ops kernel-restart` 在 dev_mode 启动前会打印 `[WARN] JWT key auto-generation (dev_mode=true)`;若 Profile 既无 `jwt.private_pem` 也未开 dev_mode,会**直接拒绝** spawn 进程并 exit,避免再次出现 500。

详见 [notes/jwt-secret-injection-via-profile.md](../notes/implemented/seam/2026-09-07-jwt-secret-injection-via-profile.md)。

## 前端 SPA / Vite / patch injection

**症状**: `lca-ops status` 全部 healthy, kernel 日志显示 `POST /runs 202 + ws_token`,但浏览器里的 chat **完全不走 LCA gateway**,而走 lobehub 原生 `/webapi/chat/openai` 路径——前端根本看不到 LCA 模型 + agent loop。日志里搜索 LCA 关键字**永远 0 命中**。

**根因** (至少三种之一):

| 根因 | 关键字 |
|---|---|
| **Vite 默认只 expose `VITE_*` env**;`process.env.NEXT_PUBLIC_*` 在浏览器 bundle 是 `undefined` —— `isLcaGatewayMode()` 永远返回 `false`。 | Vite dev server logs, `getLcaGatewayUrl()` throws "lcaGatewayUrl not configured" |
| **`lca-ops lobehub restart` 跑完 SPA bundle 没被重新 inject 真 URL**(lobehub-spa Vite 仍加载旧的占位符字符串 `ws://lca-gateway-unset:0000`) | `grep 'LCA_GATEWAY_WS_URL' lobehub-ui/src/store/chat/agents/transports/lcaGateway/client.ts` 看到占位符 |
| lobehub-spa 进程**根本没在跑** —— Vite dev server (:9876) listener 没了,前端 SPA bundle 取不到 | `ss -ltn \| grep 9876` 没输出;`curl http://127.0.0.1:9876/` 返回 `connection refused` |

### 复现 / 验证命令

```bash
# 1. 浏览器请求真的走到 LCA gateway 了吗?
grep -E "lca-api|runs|ws-token" .lca-ops/lobehub.log | tail -20
# Next.js rewrite 把 /lca-api/* 改写到 /runs/*,所以 access log 显示的是
# rewrite 后的路径 (/runs),而不是原始 /lca-api/runs —— 这是正常的。

# 2. Vite 服务端有没有把 NEXT_PUBLIC_LCA_GATEWAY_URL 注入 SPA bundle?
curl -sS "http://127.0.0.1:9876/src/store/chat/agents/transports/lcaGateway/client.ts" | grep LCA_GATEWAY_WS_URL
# 期望: const LCA_GATEWAY_WS_URL = "ws://<host>:<port>";
# 如果看到 "ws://lca-gateway-unset:0000" → patch engine 没 inject 真值,跑
# ./scripts/lca-ops lobehub restart,会看到 "[lca] patch applied: lca_runtime_agent_gateway"

# 3. isLcaGatewayMode() 在前端是不是 true?
# 在浏览器 DevTools Console 跑:
#   __BUILD_TIME_LCA_GATEWAY_URL  (console 里 __vite_something 或 grep 上面 url)
# 或 grep agentDispatcher.ts bundle:
curl -sS "http://127.0.0.1:9876/src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts" \
    | grep -A2 isLcaGatewayMode
```

### 修复路径

- **Vite 默认不 expose `NEXT_PUBLIC_*`**: LCA 的 `lca_runtime_agent_gateway` patch engine 在 apply 阶段读 `LCA_GATEWAY_PUBLIC_URL` env,把真 URL **字符串字面量**写进 `lcaGateway/client.ts`(Vite 看到字符串字面量直接 inline 到 bundle)。重启 lobehub 必须重新 inject —— `./scripts/lca-ops lobehub restart` 会自动跑(commit `c4303f50`)。
- **SPA bundle 没拿到真值**: 跑 `LCA_GATEWAY_PUBLIC_URL=http://<host>:<port> python3 deploy/lobehub/patch_lobehub.py apply lca_runtime_agent_gateway` 手动重 inject,然后 `lca-ops lobehub restart`。
- **lobehub-spa 死了**: `ss -ltn | grep 9876` 没有 LISTEN。`./scripts/lca-ops lobehub restart` 重启。**别用 `pkill -f vite`** —— 自身 argv 匹配容易 self-kill;从 `kill <pid>` 或 `pid=$(ss -ltnp | grep 9876 | grep -oP 'pid=\K[0-9]+')` 拿 PID 再 kill。

### Debug 中几个常见的陷阱

1. **`.lca-ops/kernel-serve.log` 是旧 kernel PID 的 log**,不是当前 kernel 的。当前 kernel 的 stdout 在 `/tmp/lca-kernel.log`(由 `lca-ops kernel_serve` spawn 时打开)。两者文件指针完全不同。看到一个没新内容别下结论"kernel 没工作" —— `ls -la --time-style=full-iso /tmp/lca-kernel.log .lca-ops/kernel-serve.log` 看哪个最近更新。
2. **lobehub log 里的 `ECONNREFUSED 10.36.6.252:8765` 可能不是当前问题** —— 这是 lobehub 的 `/api/device/devices` proxy 在 kernel 短暂重启时打印的,跟前端 chat 路径没关系。`grep -B2 ECONNREFUSED` 看时间点。
3. **`lca-ops lobehub restart` 输出"dev server ready"** 但 SPA bundle 仍是旧的 —— 见上"修复路径"第二项。
4. **Vite 在 dev mode 不 restart**,只是 HMR 文件改动。如果磁盘改了 client.ts 但浏览器还是看到老值,确认 `lca-ops lobehub restart` **真的**杀了 Vite 进程(否则 Vite 用 cache 返回旧文件)。

## 一次性命令速查

## 一次性命令速查

按"我要做什么"选命令;每个命令的完整语义、副作用、边界见 `run-debug-guide.md` 和 `lca-ops <cmd> --help`。

### 诊断一次 run

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
| `lca-ops journal logs lobehub` | Next.js :3010 进程日志(`.lca-ops/lobehub.log`) |
| `lca-ops journal logs lobehub-spa` | Vite :9876 进程日志(`.lca-ops/lobehub-spa.log`) |
| `lca-ops logs` | alias → `journal logs`(同 `journal logs`) |
| `lca-ops logs kernel` | tail `/tmp/lca-kernel.log`(kernel 进程 stdout/stderr) — 后端 5xx 的第一站 |

### Patch engine(LCA ↔ lobehub-ui)

lobehub-ui 是 vendor 目录(`deploy/lobehub/patches/runtime/<name>.py` + `<name>.ts`)。`./scripts/lca-ops lobehub restart` 会自动跑 `apply_patches()` 并打印 `[lca] patch applied/skipped: <name>`。

```bash
# 手动跑 patch(改了 deploy/lobehub/patches/ 后)
LCA_GATEWAY_PUBLIC_URL=http://<host>:<port> python3 deploy/lobehub/patch_lobehub.py

# 看 manifest(JSON;哪个 patch 的哪次 apply 的 SHA 在用)
python3 deploy/lobehub/patch_lobehub.py manifest

# 检查某个 patch 是否还健康
python3 deploy/lobehub/patch_lobehub.py verify

# 列出已 discover 的 patch
python3 deploy/lobehub/patch_lobehub.py list

# 抓 drift(直接改 lobehub-ui 源码没 register)
python3 deploy/lobehub/patch_lobehub.py drift
```

### LobeHub 前端（非 run）

Agent 页闪错 / 无限刷新 / `504 Outdated Optimize Dep` → [lobehub-frontend-debug.md](./lobehub-frontend-debug.md)

## fail-loud

fail-loud 是 `lca_kernel` lifecycle 的 K6 内置钩子(`lca_kernel/lifecycle.py`,ADR-0115):
未捕获异常、SIGTERM/SIGINT、环境加载违例直接以非零退出或 stderr 暴露,不被静默吞掉。
**常开,没有开关**;`LCA_DEBUG` 环境变量不存在(ADR-0122 §12 的设计未落地)。
异常与 traceback 的持久化走 spine 事件 + I10 sidecar(`<sha256>.json`),不写 `kernel.log`。

## per-run 资产

`traces/runs/<run_id>/`:

- `events.jsonl` — spine SSOT(ADR-2026-09-02-i17-stream-align;canonical journal events)
- `journal.json` — `lca.journal/3` step 投影(pretty-printed, codemap 用)
- `journal.raw.jsonl` — legacy v2 envelope stream(CLI 已不直接读,仅迁移源)
- `manifest.json` — terminal manifest
- `profile_snapshot.json` — profile 快照
- `kernel.log` — 失败兜底单行记录,唯一写者是 `record_run_failure()`(`lca/plugins/transport/webserver/handlers/runs/terminal/failure.py`):仅当 run 的收尾路径本身失败时追加一行 `run_failure_observed ...`。**多数 run 没有此文件,缺失不代表失败丢失**(ADR-0122 §5 的 `KernelLogProjection` 未落地)。进程级内核日志在 `/tmp/lca-kernel.log`(`lca-ops heal` 的 spawn 输出),两者不要混淆。
- `diagnostic.json` — typed RunDiagnostic(ADR-0122)

## 相关 ADR

- ADR-0065 §六 / PR-9: coding-agent tools (9 个 trace/explain/... 命令)
- ADR-0121: attachment FileRef SSOT
- ADR-0122: Plugin-native debug & 观测体系

## 缓存何时清: 改完代码后必做的命令

下面每行都是**修代码后必须跑**的命令。漏一个,前端就用旧 bundle,你以为修了但 UI 没变化,debug 半小时也找不到原因。这张表是这次 debug 出的真金白银——之前几个修复看起来"没生效"全是缓存没清。

| 改了谁 | 必跑命令 | 原因 |
|---|---|---|
| `lca/plugins/transport/webserver/...`(kernel handler / JWT seam / profile yaml) | `./scripts/lca-ops kernel-restart` | `/tmp/lca-kernel.log` 是 kernel 进程 stdout,只有新进程才写 |
| `deploy/lobehub/patches/...` LCA patch 源(任何 .py / .ts) | `lca-ops lobehub restart` | `_ensure_patches` 会自动跑 `apply_patches()` 并 inject 真实 URL;你如果只手动 `python3 deploy/lobehub/patch_lobehub.py apply ...` 不会重启 SPA,前端 bundle 还是旧占位符 |
| `lca/infrastructure/cli/services/lobehub/lobehub.py`(start/ensure_patches) | `lca-ops lobehub restart` | `_ensure_patches` 改了之后必须重新 init bootstrap |
| `lobehub-ui/.env*`(NEXT_PUBLIC_LCA_GATEWAY_URL 等) | `lca-ops lobehub restart` | `_ensure_env` 在 ensure_ready 阶段重写 `.env`,但 SPA spawn 拿 env 走的是 `_child_env()`,不重启拿不到 |
| 任何上面之后 **前端看不到变化** | `rm -rf lobehub-ui/node_modules/.vite lobehub-ui/.next && lca-ops lobehub restart` | Vite + Next dev (turbopack) 都缓存 module 编译产物;bundle 正确但 dev server 仍用旧 module 时**vite serve 输出旧文件**;只有 SPA restart 不能彻底清,需要先 rm |
| `lobehub-ui/src/.../*.ts`(经 LCA patch 注入的) | `rm -rf lobehub-ui/node_modules/.vite && lca-ops lobehub restart` | 上面那条的特化 |
| `lca_kernel/...` runtime lifecycle | `lca-ops kernel-restart` | K6 LIFO dispose 由 `lca_kernel.lifecycle` 守护,kernel PID 替换后才生效 |
| `profiles/...` web-assistant / web-standard | `lca-ops kernel-restart`(dev_mode 试)+ 看 dev-mode warn | 旧 kernel PID 用旧 profile snapshot,新 profile 加载得重启 |
| 浏览器 / React UI 仍 0 反应 | **用户在浏览器硬刷新**:macOS **Cmd+Shift+R** / Win/Linux **Ctrl+Shift+R**;DevTools → Network → Disable cache → 重启 DevTools | lobehub-spa 把 `.lca-ops/lobehub-spa.log` 的 stdout buffer 住,你能看到 bundle 文件已更新但浏览器还在用 ETag 命中的旧 module |

### lobehub-spa log 静止 / 看不到新内容

`lobehub-spa.log` mtime 几小时不变是 **正常** 的(Next dev 走 turbopack,bun 进程 stdout 经常 buffer;`open("ab", buffering=0)` 只是 process-level flush)。**判断"前端真的没拿到新 bundle"** 的可靠信号:

```sh
# 1. 看 vite 实际 serve 的内容
curl -sS http://127.0.0.1:9876/src/path/to/file.ts | grep 你刚改的字符串

# 2. 看 kernel 端 access log 是否有新 run 创建 + WS handshake
grep "POST /v1/runs.*ws-token" /tmp/lca-kernel.log | tail -5
```

如果 (1) 是新字符串,说明 server 端有;浏览器看不到就是 browser 端缓存(硬刷新)。如果 (1) 仍是旧字符串,server 端缓存,要 `rm -rf lobehub-ui/node_modules/.vite` 再 restart。

### 几个反复踩的坑

1. **`pkill -f vite` 会 self-kill**——bash wrapper 的 argv 含 `vite`,被 pkill 匹配后连 shell 一起死。用 `kill $(ss -ltnp | grep 9876 | grep -oP 'pid=\K[0-9]+')` 或者 `pid=$(pgrep -f 'node.*vite' | grep -v $$); kill $pid`(`grep -v $$` 排除自己)。
2. **`rm -rf lobehub-ui/node_modules/.vite` 不删 bun dev:spa 进程**,只删 Vite 的 dep cache。Vite 仍会跑,只是重新扫描。bun 进程死了 Vite 才彻底重启。
3. **`lca-ops` spawn 用 `subprocess.Popen` 不传 `cwd`**,lca-ops 自己 `os.chdir` 到 `Path.cwd()`。所以 `lca-ops` 命令在子目录跑会跑到意外目录——保持 `cwd` 在 repo 根。
4. **WS handshake 在 uvicorn access log 里不出现**(`101 Switching Protocols` 不写 access log)。`grep "/ws " /tmp/lca-kernel.log` 找不到是正常的。要确认 WS 通了用 `POST /v1/runs/{id}/ws-token` 看 200。

## 调试相关 run-debug-guide / debug README 的同步规则

**何时把发现写进 `docs/debug/`**:

- 一种新的后端 5xx 模式 → `docs/debug/README.md` 案例索引 + 关键字。
- 一种新的"前端 UI 看着健康但 0 反应"模式 → `docs/debug/README.md` 新一节 + `run-debug-guide.md` 一个新 Step 0x。
- 一种新的"我以为我修了但没生效"反模式 → 上面的缓存表加一行(优先)或单独写一段。
- 一种新的"这命令真的帮我找到问题" / "这命令误导过我" → 同一节里加进 trap 段。

**何时不用**:

- 已有同节覆盖的现象(避免重复);改进去已有的 case。
- 用户一次性很特殊的错误(进 journal/log,不进文档)。
- 仅命令名(进 `lca-ops --help` 输出,不进文档)。

**写 note (`docs/notes/...`) 还是 README**:

- 新 seam/原语/契约 → `docs/notes/...`(seam / contract / profile / primitive 之一)。
- 流程 / 排查顺序 / 命令速查 → `docs/debug/...`(不入 notes,notes 关心契约不关心命令)。