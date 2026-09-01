# ADR-0163：可执行性 readiness 在 boot 期决定，不在 request 期重复判断

## 状态

**Accepted — 2026-09-01**

由用户对 `/runs`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses`、`/journal/live` 五条 route 在缺 `LLM_API_KEY` 或缺 process-journal 绑定时，**请求路径返 503 服务不可用**的现象提出的处理原则：readiness 是启动期判断，请求路径只在「输入不合法」（4xx）层面回报。

Refines: ADR-0115（K1–K8：service 与 transport 接缝）、ADR-0119（webserver-as-plugin）、ADR-0119-followup（webserver route Registry）

## 背景

### 1. 当前 6 处 readiness 重复判断

| Route | 文件 | 判断内容 | 当前响应 |
|---|---|---|---|
| `POST /runs` | `handlers/runs/api/command_endpoints.py:55-71` | `ctx is None` + `llm_status(ctx)["llm_available"]` | 503 `lca_plugin_ctx_missing` / `lca_llm_unavailable` |
| `POST /runs`（legacy） | `handlers/runs/api/routes.py:133-148` | 同上 | 同上 |
| `POST /v1/chat/completions` | `handlers/openai_endpoints.py:50-65` | 同上 | 同上 |
| `POST /v1/embeddings` | `handlers/openai_endpoints.py:67-92` | `llm_status(ctx)` | 503 `lca_llm_unavailable` |
| `POST /v1/responses` | `handlers/openai_endpoints.py:96-139` | 同上 | 同上 |
| `GET /journal/live` | `handlers/runs/api/query_endpoints.py:99-108` | `_run_port_of(...).stream_process_journal_live(...) is None` | 503 `legacy_process_journal_unavailable` |
| `GET /journal/live`（legacy） | `handlers/runs/api/routes.py:245-258` | `_registry_of(...).journal.tail` 取不到 | 同上 |

### 2. 行为反模式

每条 route 都把同样的 readiness 探针重复一遍。这违反了 ADR-0115「K1–K8：plugin tree 完成 ready 后才允许向 transport 暴露端口」以及 ADR-0119「webserver 是 Carrier，不重新做 boot 期决定」的原则。具体表现：

- **同一个判断 6 处重复**：每次新增 LLM-触发 route，都会再写一次 `if not llm_status(...)`：注释说"LLM 未配置时返 503"，但这是请求期的早返回，不是 **failing fast** —— 服务**在没 LLM key 时照常接受了 HTTP 连接**，所有静态服务发现（lca-ops health、k8s readiness probe、CDN）都以为"服务可用"，直到第一次真实请求才被告知失败。
- **错误码风格不统一**：`lca_llm_unavailable` vs `legacy_process_journal_unavailable` vs `lca_plugin_ctx_missing`，每个 route 自己起名，没有 registry。
- **readiness 状态没有单一观察点**：`/health` 仍是公开行为，但 readiness 的真相分散在 6 个 handler。
- **`ctx.inject("llm_resolver")` 是 stringly-typed**：与项目「Seam Protocol / Capability token」的风格不一致。

### 3. 目标态需要回答的两个边界问题

1. **LLM 凭证缺失到底是"启动失败"还是"运行时降级"？**
   - 当前实现：启动 OK，请求期返 503。
   - 本 ADR 选：**启动失败**（拒绝 boot）。
2. **RunPort 能力（process-journal、evidence store）若 boot 期未绑定应该怎样？**
   - 当前实现：路由保留，请求期返 503。
   - 本 ADR 选：路由元数据根据 capability 动态扣载；启动期通过 `routes_*.plugin.setup` 的 `require(...)` 失败，boot 失败。

### 4. ADR-0115 决定的对照

ADR-0115 决定 6：路由元数据归 plugin；决定 4：plugin tree 完成 boot 后 transport 才允许 listen。本 ADR 不引入新概念，只是把这两条决定的运行时落地写实：readiness 检查 = plugin tree boot 失败，不在 transport handler 入口重做。

## 第一性原理：time of check == time of use

Service 可用性真相只有一个时点：**service 准备好的时候**。任何"请求进来再查一次"都是 TOT/TOCTOU-flavored 重复劳动，违反 ADR-0063 §I6「动态扩展不扩张核心原语」中关于不建立平行机制的约束（这里平行的是 readiness 检查）。

K7（ADR-0115）`BOOTSTRAP_NAMES` 已规定 `lca-llm-resolver` 是 LLM 凭证的唯一所有者；本 ADR 是把这条契约从"能力所有权"升级为"启动期硬绑定"。

## 决策

### 决策 1：LLM 凭证可用性由 routes 挂载期 `RouteSpec.requires` 决定

`lca.plugins.seams.think.llm_resolver` 的 `setup(ctx, config)` 不再为 credential 缺失抛错（fixture 与 prod 路径都同时需要 boot 成功），readiness 由 routes plugin 显式声明：**OpenAI-compat POST routes 的 :class:`RouteSpec` 把 `("llm_resolver",)` 列入 `requires`**。`lca.plugins.transport.webserver.route_register.register_routes` 调 `ctx.require("llm_resolver")` 检查 capability 是否挂载；缺则抛 ``RuntimeError``，整个 routes plugin 的 ``setup`` 失败，让 kernel boot unit 在 webserver 上 listen 之前就挂掉。

**生产路径**:缺 `LLM_API_KEY` → ``lca-llm-resolver`` 不 ``provide("llm_resolver")`` → routes plugin 失败 → webserver 不 listen。
**测试路径**:fixture 在 lifespan 期间 ``ctx.provide("llm_resolver", ScriptedLLMResolver())``，routes plugin 拿到 capability，挂载成功。
**Plugin setup 不再为 token 缺失抛错**，只服务自己负责的能力（注册 adapter / 解析候选）。

### 决策 2：run/chat/embedding/responses routes 移除 request 期 LLM 检查

`/runs POST`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` 的 `llm_status(ctx)["llm_available"]` 分支全部删除。

要求 `llm_resolver` 的能力提到 routes plugin 挂载阶段（决策 1）。handler 入口不再查。如果有人绕过 boot 直接调 handler（tests/support 之类的脚本路径），`_ctx_of(request)` 仍然存在，但 `_run_port_of(request)` 可能 `cast` 失败 —— 这是 test harness 的责任，不在 carrier 治理。

### 决策 3：process-journal 能力在 boot 期绑定

`lca.plugins.transport.webserver.handlers.runs.session.session.RunRegistry.bind_process_journal` 是 process-wide journal 的 capability 绑定点。`webserver.boot` 阶段（`install_bootstrap_state` 内，**K3 完成后**）已经做了这件事（见 `bootstrap.py:148-156`）。

`stream_process_journal_live` 协议返回值的契约收紧为 **`AsyncIterator[bytes] | None`，当 capability 缺失时返 `None`**：保持现状不动。但请求路径上 `if frames is None` 的「返 503」分支改为：

- **bundled default profile**：默认 profile 在 webserver boot 时允许 process journal 不绑定，但 `/journal/live` 路由元数据从 `routes_runs_sessions.ROUTES` 里被 **boot-time 条件过滤** 移除 —— 不注册路由，请求期收到 Starlette default 404。

具体机制：`routes_runs_sessions.setup(ctx, config)` 在 `require_capability(ctx, "process_journal", optional=True)` 失败时，**跳过** `Route("/journal/live", ...)` 的注册；命令式移除，不是动态 dispatch。

### 决策 4：error code 统一登记

`_err(...)` 的 `code` 命名收敛到 `lca_*` 前缀 + capability 名：

| 旧 code | 新 code | 出现条件 |
|---|---|---|
| `lca_llm_unavailable` | 决策 1+2 后**消失** | boot 失败 |
| `lca_plugin_ctx_missing` | 决策 2 后**消失** | boot 失败 |
| `legacy_process_journal_unavailable` | 决策 3 后**消失** | 路由不注册 |

代码里仅保留的 `code` 是请求体形状错误（4xx 类）：`missing_agent_ref`、`empty_user_text`、`invalid_messages_array`。

### 决策 5：legacy 双份 handler 退役

`lca/plugins/transport/webserver/handlers/runs/api/routes.py`（378 行）当前是**重复实现**—— command/query_endpoints 的旧 Session Spine 双胞胎。两份走两条不同 owner 路径，对同一组路由提供同一组接口：

- `command_endpoints.create_run` 走 `RunPort.create_and_dispatch`
- `routes.create_run` 走 `RunRegistry.find_inflight_run` + `schedule_run`

而 `routes.py` 的 SSE 工具（`iter_live_sse` / `encode_live_gap` / `_is_visible_text_channel` / `_HEARTBEAT*`）**本身又是 `handlers/runs/terminal/live_compat.py` 已经导出的 `iter_live_sse` 的本地 re-implementation**——三重冗余。

仅有 2 个测试 + 1 个 mock.patch 引用 (`tests/test_run_live_sse.py`, `tests/test_journal_live_sse.py`)；`__init__.py` 把它作为 route sibling 用于 mock.patch 解析，删除会让 path 解析失败。退役方式：

1. `routes.py` 里的 SSE 实现整段删除，改 `from ..terminal.live_compat import iter_live_sse, encode_live_gap, TEXT_CHANNEL_ALL, TEXT_CHANNEL_ANSWER, LiveGap, LiveTail`。
2. `routes.py` 变成 sub-module stub：`command_endpoints`/`query_endpoints`/`attachment_staging`/`file_reference_parsing` 的 re-export surface。
3. `routes.create_run`（inflight-run 旧路径）**不再迁移到任何文件**，整段清空（见决策 6）。

### 决策 6：inflight-run 路径彻底退役（不留 legacy 副本）

`inflight run dedupe`（同一 `user_text` + `mode` + `attachment_ids` + `agent_id` 在 inflight 状态下复用）历史上是为 LobeHub 误重发做的兜底。decision_root：

- 当前栈已经从 Session Spine 升到 RunPort（composition root），RunPort 内部 idempotency 由 `RunRequest.options` 决定，不应让 carrier handler 猜测。
- 该兜底没有可见语义文档、也没有 e2e 测试覆盖。
- `command_endpoints.create_run` 的 `RunRequest.options` 路径已支持跨调用幂等（见 `terminal/port.py:RunRequest.options`）。

决策：**不挂任何路由，不留 legacy 副本**。`routes.create_run` 与相关的 `find_inflight_run` / `schedule_run` 调用面随 `routes.py` 一并清空；任何恢复必须开新 ADR。

### 决策 7：测试 fixture 同步切换

- `tests/test_openai_compat_gateway.py::test_unavailable_returns_503`（存在则删）：boot 失败移出测试，改测 `create_app` 在 boot 期抛错。
- `tests/test_journal_live_sse.py` 的两个 `test_*_stream_journal_live_unbound_returns_503`：改为「boot 期 capability 缺失时不注册路由 → 404」。
- `tests/test_runs_sessions.py` 增：新 profile 没 `process_journal` 时 `/journal/live` 不在路由表。
- `tests/test_llm_resolver.py` 增：缺失 `LLM_API_KEY` 的 Config boot 抛 `PluginSetupError`。

### 决策 8：AGENTS.md 表格同步

PR 描述引用本 ADR；AGENTS.md 的"改动 → 最低要求"表 + routes 章节加一行：「读iness 变更：boot guard」，对上 importlinter `transport-isolation` + `kernel-domain-isolation` + 87 kernel / 24 transport / 19 env 测试。

## 决定的反复

> **问：会不会有人想保留 request 期早返回，让"未配置时优雅降级"？**

答：本 ADR 直接否决。`LLM_API_KEY` 是启动必填；没有它跑起来接 run 是把噪音推到 stream 阶段，更难定位。Kernel 启动期已经对未提供 `llm_resolver` 的 plugin tree 抛错；本 ADR 把它落到具体 plugin 行为。

> **问：process journal 缺失为什么不让路由继续注册？**

答：保持旧行为意味着"用户不会第一次请求时得到 503"，但其实还会得到——只要 process journal 没绑，**每次**都是 503。从 SDK 与可观测性角度，把路由**根本不挂**比"挂但返 503"更诚实：HD、k8s readiness、负载均衡都可以基于"路由集 = 实际可用集"做判断。

> **问：legacy `routes.py` 不直接删？**

答：mock.patch 测试仍在用 `lca.plugins.transport.webserver.handlers.runs.api.routes.command_endpoints.X` 这种 sibling 路径，删除会让 patch 解析失败。改成 stub 既满足 mock.patch，又不再有真实逻辑。

## 验证

| 项 | 命令 |
|---|---|
| Plugin setup 错误传播 | `uv run pytest tests/test_llm_resolver.py -q` (新增 boot 抛错用例) |
| Run handler facade 退役 | `uv run pytest tests/lca_plugins/transport/webserver/test_runs_sessions.py -q` (Route count 不变,但 `/journal/live` 出现条件依赖 capability) |
| OpenAI compat 503 删除 | `uv run pytest tests/test_openai_compat_gateway.py -q` |
| Journal live 404 | `uv run pytest tests/test_journal_live_sse.py -q` |
| Boot-time plugin error | `uv run pytest tests/test_plugin_tree_single_owner.py -q` |
| 静态质量 | `uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run vulture lca --min-confidence 80 && uv run python scripts/check_kernel_boundary.py` |
| 全量 | `uv run pytest` |

## 兼容性

- Wire 协议层：删除 `lca_llm_unavailable` / `lca_plugin_ctx_missing` / `legacy_process_journal_unavailable` 三类 error code。客户端应按"`503 + code∈{上述三}`"分支兜底的，需改为"`process exit + lca-ops logs`"。
- HTTP API：`/runs` `/v1/*` `/journal/live` 的请求体契约 0 变化；响应只有 boot 期 4xx 保留 + 5xx 类型固定化。
- Profile：`config.load_dotenv=false` + 无 `LLM_API_KEY` 现在是 boot 错，而非默默接受；release notes 标 **BREAKING**。

## 相关

- ADR-0115 kernel/transport 接缝 (K1–K8)
- ADR-0119 webserver-as-plugin
- ADR-0119-followup webserver route Registry
- ADR-0063 §I6 动态扩展不扩张核心原语
- ADR-0122 single execution path
- ADR-0156 清退三处架构泄漏（参照清退哲学）
