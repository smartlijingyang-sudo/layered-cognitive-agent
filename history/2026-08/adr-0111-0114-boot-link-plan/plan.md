# 启动链路 Plugin 化实施计划(ADR-0111 / 0112 / 0113 / 0114) — **Superseded**

> **状态：** Superseded by [history/2026-08/adr-0115-0117-kernel-bootstrap-plan/plan.md](../adr-0115-0117-kernel-bootstrap-plan/plan.md)
>
> **关联 ADR:** [ADR-0111 启动编译化](../../../docs/adr/0111-startup-compilation-as-subpackage.md) · [ADR-0112 Gateway 路由 plugin 化](../../../docs/adr/0112-gateway-routes-as-plugins.md) · [ADR-0113 启动 Trace 第一公民(被合并)](../../../docs/adr/0113-boot-trace-first-class-citizen.md) · [ADR-0114 启动事件词表增量(被合并)](../../../docs/adr/0114-boot-event-catalog-increment.md) · 父级 [ADR-0083 W1/W6/W7](../../../docs/adr/0083-deepseek-harness-plugin-implementation-plan.md)
>
> **创建日期:** 2026-08-31(初版)
> **预计总工作量:** 4 周,8 个 PR,30+ commits
>
> ⚠️ **本文初版(2026-08-31 上午)按 8 PR / 30+ commits / 4 周设计;3 个 subagent 评审一致 BLOCK(过度工程化 + YAGNI + Stage 词汇 4 处独立)。新架构方向见 [ADR-0115](../../../docs/adr/0115-kernel-transport-boundary.md)(Kernel/Transport 边界),执行计划见 [新 plan](../adr-0115-0117-kernel-bootstrap-plan/plan.md)。**
>
> **历史命令脚注(2026-09-02):** 本计划里反复出现的 `lca-ops trace boot --tail N --since <dur> --json` 子命令在实现时被替换为 `lca-ops journal trace <run_id> [--human/--no-human --source --locals --json --limit N]`(boot 已不再是独立 trace,而是每个 run 的初始 span)。文档保留以体现决策路径,但请勿按 `trace boot` 调用。

## 1. 总体目标

把 LCA 启动链路从"god module 集中编排"重构为"按职责拆分 + plugin 化":

| 子目标 | ADR | 验收 |
|---|---|---|
| 启动编译拆子包 | 0111 | `lca/harness/profile/compilation/` 6 个文件,每个 ≤ 150 行;`compile_profile()` 是新公共 API;`boot_profile` deprecated alias |
| Gateway 路由 plugin 化 | 0112 | 8 个 L3 routes plugin + 1 个 L0 server seam;`gateway/app.py` ≤ 200 行 |
| 启动 Trace 一等公民 | 0113 | `JsonlFileSink` 默认实现;`JournalSink` 可选;`lca-ops trace boot` 子命令 |
| 启动事件词表增量 | 0114 | 5 个新 JournalEvent + descriptor 登记 + CI 守卫 |

## 2. 依赖图

```text
W0 基线快照(已有,扩展)
   ↓
W1.5-a: profile/compilation/ 子包拆分     [ADR-0111]
   ↓
W1.5-b: boot→compile 公共 API 改名+deprecated alias  [ADR-0111]
   ↓
W1.5-c: 启动事件词表增量 + JournalSink    [ADR-0114 + 0113]
   ↓
W1.5-d: JsonlFileSink + lca-ops trace boot    [ADR-0113]
   ↓
W1.5-e: gateway/server.py + LcaGatewayServer Protocol    [ADR-0112]
   ↓
W1.5-f: gateway/routes/*.py 8 个 plugin 拆分           [ADR-0112]
   ↓
W1.5-g: gateway/app.py 瘦身 + 死代码删除                 [ADR-0111 + 0112]
   ↓
W1.5-h: invariant.py 模板 + check_plugin_paths 门禁      [ADR-0111]
   ↓
W1.5-i: 全量验证 + 文档同步 + Definition of Done
```

各阶段串行,但 W1.5-e/f 可以拆为两条并行分支(L0 seam 协议 vs L3 routes plugin)。

## 3. 任务清单(按 PR/Commit 粒度)

### PR-1 (W1.5-a, ADR-0111):建立 profile/compilation/ 子包

**Commit 序列:**

| Commit | 内容 | 文件清单 |
|---|---|---|
| C1.1 | 新建 `compilation/stages.py`:`Stage` 枚举 + `StageTimer` 数据类 | 新建 1 |
| C1.2 | 新建 `compilation/errors.py`:`StageError / FiberBootError / ObservabilityAssemblyError` | 新建 1 |
| C1.3 | 新建 `compilation/fiber.py`:`spawn_fiber(ctx, definition, config) -> AuditedPluginContext`(从 `boot.py:_boot_plugin` 迁出) | 新建 1,改 1(`boot.py`) |
| C1.4 | 新建 `compilation/observability.py`:`install_observability(ctx) -> BoundObservability`(从 `boot.py:_install_observability` 迁出) | 新建 1,改 1 |
| C1.5 | 新建 `compilation/dispose.py`:`dispose_safely(ctx)`(从 `boot.py:_dispose_context` 迁出) | 新建 1,改 1 |
| C1.6 | 新建 `compilation/__init__.py`:`compile_resolved / compile_profile / compile_entries` 公共 API;`boot_*` deprecated alias | 新建 1,改 1 |
| C1.7 | 删 `boot.py` 重复/已迁出内容,保留 thin compat | 改 1 |

**依赖:**
- W0 完成(已有 `lca-ops diagnose plugin-tree` 基线命令)
- 测试覆盖:fiber 启动幂等性、setup 异常时 dispose 路径、deprecated alias 发警告

**验证命令:**
```sh
uv run ruff check --fix lca/harness/profile/compilation/
uv run ruff format lca/harness/profile/compilation/
uv run mypy lca/harness/profile/compilation/
uv run pytest tests/harness/profile/compilation/ -v
uv run pytest tests/harness/profile/test_boot_compat.py -v   # 验证 alias
uv run lca-ops diagnose plugin-tree profiles/web-standard.yaml
```

### PR-2 (W1.5-c, ADR-0114):启动事件词表增量

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C2.1 | `journal.py` 加 5 个 frozen dataclass(`BootProfileResolved / BootPluginFiberSpawned / BootObservabilityAssembled / BootTraceFlushed / BootLifecycleFailed`) |
| C2.2 | `event_descriptors_data.py` 在 `build_default_registry()` 末尾追加 5 行 `_descriptor(...)` |
| C2.3 | `JOURNAL_EVENT_CLASSES` 末尾追加 5 行映射 |
| C2.4 | `tests/test_journal_catalog_boot_events.py`:词条形状 + descriptor 完整性 |
| C2.5 | `tests/harness/profile/compilation/test_journal_emitted.py`:模拟 boot 流程,断言每个 stage emit 对应事件 |

**依赖:**
- PR-1 的 `compilation/stages.py` 完成(Stage 名要跟 event.stage 一致)

**验证命令:**
```sh
uv run pytest tests/test_observability_boundary.py -v
uv run pytest tests/test_journal_catalog_boot_events.py -v
uv run pytest tests/harness/profile/compilation/test_journal_emitted.py -v
uv run lint-imports
```

### PR-3 (W1.5-d, ADR-0113):启动 Trace sink + lca-ops 子命令

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C3.1 | `lca/contracts/models/observability/trace.py`:`TraceEvent / Trace` frozen dataclass |
| C3.2 | `lca/contracts/protocols/trace_sink.py`:`TraceSink` Protocol |
| C3.3 | `lca/contracts/protocols/trace_sink_registry.py`:`TraceSinkRegistry` Protocol |
| C3.4 | `lca/harness/trace/sinks/file.py`:`JsonlFileSink` 实现 |
| C3.5 | `lca/harness/trace/sinks/journal.py`:`JournalSink` 实现(依赖 PR-2 的 JournalEvent) |
| C3.6 | `lca/plugins/observability/trace_file.py`:`@plugin lca-boot-trace-file-sink` |
| C3.7 | `lca/plugins/observability/trace_journal.py`:`@plugin lca-boot-trace-journal-sink` |
| C3.8 | `bundles/observability.yaml`(新建):装载两个 trace sink plugin |
| C3.9 | `profiles/web-standard.yaml` patch:追加 `bundles/observability.yaml` |
| C3.10 | `scripts/lca-ops trace boot` 子命令(tail/since/profile/failures/json 选项) |
| C3.11 | 测试套件(sink 协议一致性 / JsonlFileSink append 幂等 / retention 清理 / journal 转发) |

**依赖:**
- PR-1(Stage 枚举已就绪,emit hook 落在 fiber.py)
- PR-2(JournalEvent 已登记,JournalSink 才有 contract)

**验证命令:**
```sh
uv run pytest tests/harness/trace/ -v
uv run pytest tests/test_lca_ops_trace.py -v
uv run pytest tests/integration/test_boot_trace_e2e.py -v
uv run lca-ops trace boot --tail 50 --json
uv run lca-ops trace boot --since 1h
```

### PR-4 (W1.5-e, ADR-0112):LcaGatewayServer Protocol + lca-gateway-server plugin

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C4.1 | `lca/contracts/protocols/gateway_server.py`:`LcaGatewayServer` Protocol |
| C4.2 | `lca/plugins/gateway/server.py`:`@plugin lca-gateway-server` + `GatewayServer` 实现 |
| C4.3 | `bundles/web-app.yaml` patch:装载 `lca-gateway-server` |
| C4.4 | `tests/plugins/gateway/test_server.py`:Protocol 一致性 + register/dispose 幂等 |

**依赖:**
- PR-1(`compile_profile` 公共 API 就绪,lifespan 通过 compile 装配)

**验证命令:**
```sh
uv run pytest tests/plugins/gateway/test_server.py -v
uv run pytest tests/test_lca_gateway_server_compliance.py -v
uv run lca-ops diagnose plugin-tree bundles/web-app.yaml
```

### PR-5 (W1.5-f, ADR-0112):8 个路由 plugin 拆分

**Commit 序列(可拆为 8 个 sub-PR):**

| Commit | 内容 | requires |
|---|---|---|
| C5.1 | `lca/plugins/gateway/routes_health.py`:`/health`、`/options` | `gateway_server` |
| C5.2 | `lca/plugins/gateway/routes_context.py`:`/context` | `gateway_server`, `run_registry` |
| C5.3 | `lca/plugins/gateway/routes_journal.py`:`/journal/live`(SSE) | `gateway_server`, `journal` |
| C5.4 | `lca/plugins/gateway/routes_runs.py`:`/runs` 系 7 个 endpoint | `gateway_server`, `run_registry`, `compile_profile` |
| C5.5 | `lca/plugins/gateway/routes_sessions.py`:`/v1/sessions` 系 8 个 endpoint | `gateway_server`, `agent_registry`, `command_gateway` |
| C5.6 | `lca/plugins/gateway/routes_files.py`:`/files/{id}`、`/files/{id}/meta` | `gateway_server`, `file_store` |
| C5.7 | `lca/plugins/gateway/routes_openai_shim.py`:`/v1/models`、`/v1/chat/completions`、`/v1/embeddings`、`/v1/responses` | `gateway_server`, `llm_resolver` |
| C5.8 | `lca/plugins/gateway/routes_device.py`:`/api/device/*`(8 个 endpoint) | `gateway_server`, `device_hub`, `machine_resolver` |
| C5.9 | `bundles/web-app.yaml` patch:装载 8 个 routes plugin |
| C5.10 | 8 个 test_server_routes_*.py 测试 |

**依赖:**
- PR-4 完成(`gateway_server` seam 可注入)

**验证命令:**
```sh
uv run pytest tests/plugins/gateway/ -v
uv run pytest tests/test_architecture_gateway.py -v
uv run pytest tests/gateway/ -v
uv run lca-ops serve &   # 启动后 curl 验证
curl -s http://127.0.0.1:3080/health | jq .
curl -s http://127.0.0.1:3080/runs -X POST -H "Content-Type: application/json" -d '{}' | jq .
```

### PR-6 (W1.5-g, ADR-0111 + 0112):gateway/app.py 瘦身

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C6.1 | 删 `gateway/app.py:_load_harness_profile`(死代码) |
| C6.2 | 删 `gateway/app.py:_configure_structlog`(由 ADR-0115 替代,本期 stub 化) |
| C6.3 | 删 `gateway/app.py:_download_file / _get_file_meta`(迁给 `routes_files.py`) |
| C6.4 | 删 `gateway/app.py` bootstrap 重复块 |
| C6.5 | 重构 `create_app()` 为 thin adapter(只装配 starlette + lifespan + plugin tree) |
| C6.6 | 重构 `app = create_app()` 为 lazy 装配(uvicorn `--factory` 兼容) |

**依赖:**
- PR-5 完成(所有路由已迁移到 plugin,`create_app` 不需要再注册)

**验证命令:**
```sh
uv run ruff check --fix gateway/
uv run ruff format gateway/
uv run mypy gateway/
uv run pytest tests/test_gateway_app_*.py -v
wc -l gateway/app.py   # 断言 ≤ 200 行
```

### PR-7 (W1.5-h, ADR-0111):invariant.py + check_plugin_paths

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C7.1 | `scripts/check_plugin_paths.py`:扫所有 profile/bundle,每个 `$module` 必须能 import;manifest 与装饰器一致 |
| C7.2 | `lca-ops diagnose plugin-invariants --all` / `--plugin <id>` 子命令 |
| C7.3 | 给 5 个 plugin 包(`lca-observability-assembly` / `lca-gateway-server` / 8 个 routes_* / `lca-boot-trace-*`)写 `invariant.py` |
| C7.4 | CI 接入 `check_plugin_paths` + `plugin-invariants` 阻断 |

**依赖:**
- PR-3 + PR-5(plugin 包稳定)

**验证命令:**
```sh
uv run scripts/check_plugin_paths.py profiles/ bundles/
uv run scripts/check_plugin_paths.py --strict
uv run lca-ops diagnose plugin-invariants --all
uv run lca-ops diagnose plugin-invariants --plugin lca-observability-assembly
```

### PR-8 (W1.5-i, ADR 全部):全量验证 + Definition of Done

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C8.1 | 删 `gateway/app.py` 的最后兼容垫片(已无调用方) |
| C8.2 | `lca/infrastructure/env/bootstrap.py` stub(ADR-0115 后续实施,本期留 todo) |
| C8.3 | `docs/specs/documentation-map.md` 加 4 个 ADR 索引 |
| C8.4 | `AGENTS.md` §6 验证矩阵扩展:加 `lint-imports + check_plugin_paths` 行 |
| C8.5 | `bundles/web-app.yaml` README 同步 routes_* plugin 列表 |
| C8.6 | `profiles/web-standard.yaml` README 加 `bundles/observability.yaml` |

**验证命令(全量,遵循 AGENTS.md §6 contracts 改动级别):**
```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca gateway scripts
uv run pytest                                          # 全量测试
uv run vulture lca --min-confidence 80                 # 死代码扫描
uv run scripts/check_plugin_paths.py --strict
uv run scripts/check_no_barrel_glob.py
uv run scripts/check_function_verb_prefix.py
uv run scripts/check_package_size.py
uv run lca-ops diagnose plugin-tree profiles/web-standard.yaml
uv run lca-ops trace boot --tail 50
uv run lca-ops trace boot --since 1h
uv run lca-ops trace boot --failures --json | jq .
uv run lca-ops diagnose plugin-invariants --all
```

## 4. 验证矩阵

按 AGENTS.md §6 "改动 → 最低要求" 表 + 借鉴 deepseek 的"替换性测试" 理念:

| 改动类型 | 任务 | 验证命令 |
|---|---|---|
| contracts / Protocol / 枚举 | PR-1 (fiber.py) + PR-2 (JournalEvent) + PR-4 (gateway_server Protocol) | `ruff + lint-imports + mypy + 全量 pytest` |
| import / 模块移动 | PR-1 (boot.py → compilation/) + PR-6 (gateway/app.py 瘦身) | 上一项 + `lint-imports` |
| Gateway 路由 | PR-5 + PR-6 | ruff + gateway 测试 + e2e curl |
| Plugin Manifest 新增 | PR-3 + PR-4 + PR-5 | ruff + plugin 测试 + `lca-ops diagnose plugin-tree` |
| Journal Catalog 增量 | PR-2 | `tests/test_observability_boundary.py` + `tests/test_journal_catalog_boot_events.py` |
| 删除共享符号 | `boot_profile` 兼容期保留,deprecated alias | `tests/harness/profile/test_boot_compat.py` |
| 包组织 / 命名 | 全 PR | `check_plugin_paths + check_no_barrel_glob + check_function_verb_prefix + check_package_size` |

## 5. Definition of Done

- [ ] `lca/harness/profile/compilation/` 6 个文件,每个 ≤ 150 行,单文件 ≤ 200 行
- [ ] `gateway/app.py` ≤ 200 行,无 module-level 副作用,无死代码
- [ ] `boot_profile` 仍能调用,但发 `DeprecationWarning`,所有调用点标记迁移
- [ ] `compile_profile` 是新公共 API,文档/diag/AGENTS.md 引用之
- [ ] 8 个 routes_* plugin 注册的 endpoint 与迁移前完全一致(curl 验证)
- [ ] 启动 trace 默认写到 `traces/boot/boot-<utc>.jsonl`,retention = 7 天
- [ ] `lca-ops trace boot --tail 50` 可读,`--since 1h` 可过滤,`--json` 机器可读
- [ ] 5 个 JournalEvent 在 catalog 登记,`tests/test_observability_boundary.py` 全过
- [ ] `lca-ops diagnose plugin-tree profiles/web-standard.yaml` 输出 164 nodes / edges 数与迁移前一致(基线对比)
- [ ] `lca-ops serve` 启动后,`curl /health` 返回 200,`curl /runs -X POST` 返回 200/400(合法请求)
- [ ] 启动失败时,`traces/boot/boot-<utc>.jsonl` 含 `BootLifecycleFailed` event
- [ ] 全量 `pytest` 通过,`mypy lca` 无 error,`vulture lca --min-confidence 80` 无新发现

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `boot_profile` deprecated alias 6 个月期满后大量 warnings | CI 切 warning→error 前,grep 全仓 import,批量替换为 `compile_profile` |
| 路由拆分后某 endpoint 漏注册 | `tests/test_architecture_gateway.py` 扩展:对照 ADR-0103 列出的 endpoint 清单,断言每个 path 在某个 routes_* plugin 中注册 |
| Trace sink 写文件阻塞启动 | JsonlFileSink 用 `threading.Lock`,实测 < 1ms/event;CI 跑 100 次 boot 取 P95 |
| JournalEvent 词条膨胀 | `tests/test_observability_boundary.py` 已经 fail-fast,新加 event 必须 descriptor,否则阻断 |
| import 路径大改引发 merge conflict | 每个 PR 拆细,merge 后 rebase 下一 PR;e2e tests 必须在 PR-6 之后才能跑 |
| deepseek `host/webserver` 是 JS,LCA 是 Python,vendor Cordis API 不完全等价 | LcaGatewayServer Protocol 是适配层,不可变 dataclass + `__setattr__` 绕过保证 frozen 不变量;语义等价 deepseek register/dispose |

## 7. 范围外(留待后续 ADR)

| 主题 | 备注 |
|---|---|
| deepseek `cordis-plugin-loader` npm-name resolution | LCA 走 `$module` + 门禁,见 PR-7 |
| BOOTSTRAP_NAMES 白名单 env 加载 | ADR-0115 待立项 |
| LcaService 长期实例 Protocol | ADR-0116 待立项,只对需要状态的 plugin(`FileStoreService` 等) |
| `@inject('foo')` consumer 依赖装饰器 | ADR-0117 待立项 |
| structlog 配置完全归 plugin | ADR-0115 合并项 |

## 8. 决策点(等你拍板)

| # | 决策 | 默认 | 替代 |
|---|---|---|---|
| D1 | `boot_profile` deprecated 保留多久? | 6 个月 | 3 个月激进 / 12 个月保守 |
| D2 | trace 默认开? | 是,JsonlFileSink 默认 | 默认关,profile opt-in |
| D3 | JournalSink 默认开? | 是(跟 JsonlFileSink 一起) | 默认关,profile opt-in |
| D4 | routes plugin 拆 8 个 vs 按 ADR-0085 重新分组合并 | 8 个 1:1 对应原 endpoint 组 | 合并为 3-4 个大组(运行 / 会话 / 文件 / OpenAI) |
| D5 | 启动 trace retention 默认值 | 7 天 | 3 天 / 30 天 |
| D6 | `lca-ops trace boot` 是否同时输出到 stdout? | 否,只走 JSONL | 是,加 `--stdout` flag |

请审阅本计划 + 4 个 ADR 后回这 6 个决策点。回完之后进入实施阶段。