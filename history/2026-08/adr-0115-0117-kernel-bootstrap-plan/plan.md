# Kernel / Transport 边界 + 启动链路收敛实施计划

> **关联 ADR:** [ADR-0115 Kernel/Transport 边界](../../../docs/adr/0115-kernel-transport-boundary.md) · [ADR-0111 启动编译化(修订版)](../../../docs/adr/0111-startup-compilation-as-subpackage.md) · [ADR-0112 Gateway 路由 plugin 化(修订版)](../../../docs/adr/0112-gateway-routes-as-plugins.md) · [ADR-0116 启动事件词表与可观测性收敛](../../../docs/adr/0116-boot-event-observability-convergence.md) · [ADR-0117 Process 生命周期 + Fail-loud + Env 白名单](../../../docs/adr/0117-process-lifecycle-env-whitelist.md) · 父级 [ADR-0083 W1/W6/W7](../../../docs/adr/0083-deepseek-harness-plugin-implementation-plan.md) · [ADR-0062 插件运行时收口](../../../docs/adr/0062-plugin-runtime-cleanup.md)
>
> **Supersedes:** [history/2026-08/adr-0111-0114-boot-link-plan/plan.md](../adr-0111-0114-boot-link-plan/plan.md)(初版 8 PR / 30 commits / 4 周;被 3 个 subagent 评审一致 BLOCK 后重写)
>
> **创建日期:** 2026-08-31
> **预计总工作量:** 12 天,6 个 PR,16 commits
>
> ## 0. 决策点(已锁定,2026-08-31)
>
> | # | 决策 | 答案 |
> |---|---|---|
> | D1 | `lca-kernel/` 顶层包 vs `lca/harness/kernel/` 子包? | **顶层包**(`pyproject.toml` `packages.find include = ["lca*"]` glob 已支持) |
> | D2 | `set_default_ctx` 6 个月 deprecated vs 直接删? | **6 个月 deprecated**(目标 2027-02-28 退役) |
> | D3 | `lca-ops logs --scope boot` 默认显示哪些 stage? | **`all`**(Stage 枚举全部) |
> | D4 | `Stage` IntEnum 起始值 0 还是 1? | **1**(便于与日志 `seq` 区分) |
> | D5 | `BOOTSTRAP_FORBIDDEN` 包括 `LCA_PROFILE`? | **是** |
> | D6 | transport namespace `lca/plugins/transport/` vs `lca/transport/`? | **`lca/plugins/transport/`** |
>
> ## 0.5 第 4 个 subagent 评审 BLOCK 修复(2026-08-31)
>
> | BLOCK | 修复位置 |
> |---|---|
> | B1 `FORBIDDEN_TRANSPORT_DEPS` 自相矛盾 | ADR-0115 决定 3 改为禁 `{lca_kernel.source/resolve/boot/...}` 内部模块,允许公共面 |
> | B2 `compile_result` capability 注册路径缺失 + typo `lca_kernal.` | ADR-0115 决定 3 修 typo;`lca-kernel/__init__.py` 显式 `install_compile_result(ctx, plan)` |
> | B3 importlinter 契约漏 `lca-kernel` | ADR-0115 决定 3 加 importlinter 契约 `forbidden_modules = ["lca-kernel"]` for下层 |
>
> 关键 FLAG 同步入 plan:
> - F3 BOOTSTRAP_PREFIXES 补全 → PR-1 C1.1
> - F8 asyncio.get_running_loop + threading.excepthook → PR-2 C2.4
> - F10 LcaGatewayRouter SEAM → PROVIDER → PR-4 C4.2
>
> ## 0.6 deepseek P0/P1 借鉴补全(并入本期)
>
> | 借鉴项 | deepseek 对应 | 加到哪 |
> |---|---|---|
> | `composeEntries()` 多层 patch 合并 | `app-boot/src/index.ts:composeEntries` | PR-2 C2.2 |
> | `FAIL_LOUD_RELEASE_TIMEOUT_MS = 2000` | `app-boot/src/index.ts:FAIL_LOUD_RELEASE_TIMEOUT_MS` | PR-2 C2.4 |
> | `BOOTSTRAP_PREFIXES` 补全 LCA 实际 env | `app-boot/src/index.ts:BOOTSTRAP_PREFIXES` | PR-1 C1.1 |

## 1. 总体目标

把 LCA 启动链路从"kernel 越界做 transport"重构为**kernel/transport 二元边界**,严格借鉴 deepseek-harness 的 `app-boot` + `host-webserver` 互不知晓模式:

| 子目标 | ADR | 验收 |
|---|---|---|
| **lca-kernel/ 顶层包**(12 文件,8 大职责)| 0115 + 0111 修订 + 0117 | `lca-kernel/` ≤ 13 文件,每个 ≤ 200 行;零 transport 知识(lint-imports 强制) |
| **transport/webserver/ plugin 化** | 0115 + 0112 修订 | `lca/plugins/transport/webserver/` + 4 个 routes plugin;`gateway/app.py` ≤ 60 行 thin factory |
| **boot 可观测性收敛** | 0116 | 3 个 typed JournalEvent + 2 个 RuntimeObserved;`lca-ops logs --scope boot` 复用现有 CLI |
| **Process 生命周期 + Fail-loud + Env 白名单** | 0117 | K6+K7 完整,deepseek `installFailLoud` + `BOOTSTRAP_NAMES` 模式 |
| **`lca/application/api.py` set_default_ctx 删除** | 0115 决定 7 | ADR-0062 违反债清零 |

## 2. 依赖图(6 PR 串行,中间可分支)

```text
PR-1 (K6 + K7 基础设施)
   ↓
PR-2 (lca-kernel/ 顶层包 + 12 文件)
   ↓
PR-3 (3 个 typed JournalEvent + Stage IntEnum)
   ↓
PR-4 (lca/plugins/transport/webserver/ + GatewayRouter + 4 routes)
   ↓
PR-5 (gateway/app.py thin factory + set_default_ctx 删除)
   ↓
PR-6 (全量验证 + 文档同步 + Definition of Done)
```

PR-1 → PR-2 → PR-3 严格串行(Stage 枚举、env 加载被后续 PR 依赖);PR-4 可与 PR-5 合并但为 review 清晰分开;PR-6 是收尾验证。

## 3. 任务清单

### PR-1(K6+K7 基础设施,~2 天,2 commits)

**Commit 序列:**

| Commit | 内容 | 文件清单 |
|---|---|---|
| C1.1 | 新建 `lca/infrastructure/env/__init__.py + bootstrap.py`:`BOOTSTRAP_NAMES` / `BOOTSTRAP_PREFIXES` / `BOOTSTRAP_FORBIDDEN` 三个 frozenset 常量(纯常量,不 import os/sys/dotenv);**`BOOTSTRAP_PREFIXES` 补全 LCA 实际 env 变量**(`LLM_ / GATEWAY_ / LOBE_ / LOBEHUB_ / ONLYBOXES_ / MARKET_ / AGENCY_ / WAL_ / DB_ / S3_ / REDIS_ / OTEL_ / VAULT_` 等,从本期实施前的 `grep -rh 'os.environ' lca/` 完整盘点结果填入) | 新建 2 |
| C1.2 | 新建 `lca/infrastructure/env/layered.py`:`filter_env_keys(raw_env, ambient) -> tuple[frozenset[str], frozenset[str]]` 返回 (allowed_keys, blocked_keys);纯函数无副作用;+ 测试 `tests/lca/infrastructure/env/test_bootstrap.py` + `test_layered.py` | 新建 2,改 0 |

**验证命令:**
```sh
uv run ruff check --fix lca/infrastructure/env/
uv run ruff format lca/infrastructure/env/
uv run mypy lca/infrastructure/env/
uv run pytest tests/lca/infrastructure/env/ -v
uv run python -c "from lca.infrastructure.env import BOOTSTRAP_NAMES, BOOTSTRAP_PREFIXES; print(len(BOOTSTRAP_NAMES), len(BOOTSTRAP_PREFIXES))"
uv run grep -rE 'import os|import sys|from dotenv' lca/infrastructure/env/  # 必须为空
```

### PR-2(lca-kernel/ 顶层包 + 12 文件,~3 天,4 commits)

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C2.1 | 新建 `lca-kernel/__init__.py + stages.py + errors.py`:`Stage(IntEnum)` SSOT(`SOURCE=1 / RESOLVE=2 / TOPO=3 / PLAN=4 / BOOT=5 / OBSERVABILITY=6`,起始值 1)+ `KernelError / FailLoudError / StageError` + 公共面 `compile_profile / run_kernel / stop_kernel / run_kernel_lifespan / install_compile_result(ctx, plan)` 占位(stub) |
| C2.2 | 从 `lca/harness/profile/{source,resolve,declarations,plan_compiler,capability_plan_resolver,runtime_binding_validator,runtime_closure,boot_products,boot_projection}.py` **迁文件内容到 `lca-kernel/{source,resolve,declarations,plan,closure,boot_products,projection}.py`**;**`source.py` 加 `compose_entries()` 借鉴 deepseek 多层 patch 合并**(`bundlePatches + profilePatches + homePatches + overlays`);旧路径保留 compat forwarding,6 个月删除 |
| C2.3 | 把 `lca/harness/profile/boot.py` 拆为 `lca-kernel/{boot,observability}.py`:`spawn_fiber` + `install_observability`(单一装配点)+ `dispose_safely`;`_install_trace` 拆为独立 `install_trace(ctx) -> BootTrace` |
| C2.4 | 新建 `lca-kernel/{lifecycle,env}.py`:`install_fail_loud`(用 `asyncio.get_running_loop()` + `sys.excepthook` + `threading.excepthook`)+ `install_signal_handlers` + `create_shutdown_coordinator`(带 `FAIL_LOUD_RELEASE_TIMEOUT_MS = 2000` 常量借鉴 deepseek)+ `load_layered_env`(调 `lca/infrastructure/env/`);+ `lca-kernel/trace.py:BootTrace`;+ 测试 `tests/lca_kernel/test_{lifecycle,env,stage,boundary}.py` |

**注意**:`lca-kernel/` 整包必须是**新顶层包**(跟 `lca/` 平级,**不在** `lca/` 树下);根目录 `pyproject.toml` 加 `packages = [" ", "lca-kernel"]`(`packages.find` glob 改成 `["lca*"]` 或显式列表)。

**验证命令:**
```sh
uv run ruff check --fix lca-kernel/
uv run ruff format lca-kernel/
uv run mypy lca-kernel/
uv run pytest tests/lca_kernel/ -v
uv run python -c "from lca_kernel import compile_profile, run_kernel, Stage; print(Stage.RESOLVE, int(Stage.SOURCE))"
uv run python scripts/check_kernel_boundary.py    # 零 transport 知识门禁
wc -l lca-kernel/*.py | tail -1                   # 单文件 ≤ 200 行
ls lca-kernel/ | wc -l                            # ≤ 13 文件
```

### PR-3(3 个 typed JournalEvent + Stage IntEnum 引用,~1 天,1 commit)

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C3.1 | `lca/contracts/models/observability/journal.py` 加 3 个 frozen dataclass(`BootProfileResolved / BootPluginFiberSpawned / BootObservabilityAssembled`),`BootPluginFiberSpawned.stage` 引用 `lca_kernel.stages.Stage`;`event_descriptors_data.py` build_default_registry() 末尾追加 3 行 `_descriptor(...)`;`journal_catalog.py` JOURNAL_EVENT_CLASSES dict 加 3 个 entry;+ 测试 `tests/test_journal_catalog_boot_events.py` + `tests/lca_kernel/test_stage_enum_is_ssot.py` |

**验证命令:**
```sh
uv run pytest tests/test_journal_catalog_boot_events.py -v
uv run pytest tests/test_observability_boundary.py -v
uv run pytest tests/lca_kernel/test_stage_enum_is_ssot.py -v
uv run python -c "from lca_kernel import Stage; from lca.contracts.models.observability.journal import BootPluginFiberSpawned; print(BootPluginFiberSpawned(stage=Stage.BOOT, ...))"
uv run lca-ops logs --scope boot --tail 5         # 复用现有 CLI
```

### PR-4(lca/plugins/transport/webserver/ + GatewayRouter + 4 routes,~3 天,4 commits)

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C4.1 | 新建 `lca/contracts/protocols/gateway_router.py`:`LcaGatewayRouter` Protocol(`register_http / register_websocket / set_fallback / install`,每个返回 `Callable[[], None]` disposer) |
| C4.2 | 新建 `lca/plugins/transport/__init__.py + webserver/__init__.py + webserver/router.py`:`@plugin lca-gateway-router`(L0 SEAM,`provides=("gateway_router",)`)+ `GatewayRouter` 实现(mutable class,deepseek WebServer 形态,不用 frozen + __setattr__) |
| C4.3 | 新建 `lca/plugins/transport/webserver/lifespan_adapter.py`:把 starlette lifespan 桥到 `lca_kernel.run_kernel_lifespan`(starlette → kernel,反向 kernel 不知道有 starlette) |
| C4.4 | 新建 4 个 routes plugin:`routes_health_options.py` / `routes_runs_sessions.py` / `routes_openai_compat_files.py` / `routes_device.py`;每个 ≤ 40 行,`@plugin(requires=("gateway_router",), kind=PluginKind.PROVIDER)` + `setup` 仅 register + `ctx.effect(dispose, label=...)`;+ `bundles/web-app.yaml` patch 加 4 个 entry;+ 测试 `tests/lca_plugins/transport/webserver/test_*.py` × 5 |

**验证命令:**
```sh
uv run ruff check --fix lca/plugins/transport/
uv run ruff format lca/plugins/transport/
uv run mypy lca/plugins/transport/
uv run pytest tests/lca_plugins/transport/ -v
uv run lca-ops diagnose plugin-tree bundles/web-app.yaml  # 应包含 lca-gateway-router + 4 routes
uv run python -c "from lca.plugins.transport.webserver.router import GatewayRouter; print(GatewayRouter)"
ls lca/plugins/transport/webserver/ | wc -l  # ≤ 7 文件
```

### PR-5(gateway/app.py thin factory + set_default_ctx 删除,~1 天,2 commits)

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C5.1 | `gateway/app.py` 重写为 thin factory(≤ 60 行):`create_app()` 接受 `ctx_provider: Callable[[], Context]`,只装配 starlette + lifespan_adapter,**不再调 `boot_profile()`**;删 `_load_harness_profile / _configure_structlog / _download_file / _get_file_meta / bootstrap 重复块` |
| C5.2 | `lca/application/api.py` 删除 `set_default_ctx / _default_ctx_holder` import;`lca/application/default_context.py` 保留 `ensure_default_ctx / get_or_create_default_ctx` 但标记 deprecated;所有调用点改 `await run_kernel(...)` 显式拿 ctx;+ `scripts/lca-ops` 新增 `kernel` 子命令 group:`boot / serve / stop / reload / compose` |

**验证命令:**
```sh
wc -l gateway/app.py                                    # ≤ 60 行
uv run pytest tests/gateway/test_thin_factory.py -v
uv run grep -rE 'set_default_ctx|_default_ctx_holder' lca/ scripts/ tests/  # 必须只剩 compat
uv run python -c "from lca.infrastructure.cli import cli; cli(['kernel', 'boot', 'profiles/web-standard.yaml', '--dry-run'])"
uv run lca-ops kernel compose profiles/web-standard.yaml --json | jq .
```

### PR-6(全量验证 + Definition of Done,~2 天,1 commit)

**Commit 序列:**

| Commit | 内容 |
|---|---|
| C6.1 | `pyproject.toml` `packages` 加 `lca-kernel`;`[tool.lint-imports]` 加 kernel-boundary 配置;`docs/specs/documentation-map.md` + `AGENTS.md §2 仓库地图` + `docs/adr/README.md` + `bundles/web-app.yaml README` + `profiles/web-standard.yaml README` 全量同步;`tests/lca_kernel/test_no_transport_knowledge.py`(扫整个 `lca-kernel/` 不能 import transport);`tests/test_no_process_singleton.py`(LCA 全局无 `_shutdown_coordinator` 类单例) |

**全量验证命令(AGENTS.md §6 contracts 改动级别):**
```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run python scripts/check_kernel_boundary.py
uv run python scripts/check_no_utility_modules.py
uv run python scripts/check_no_barrel_glob.py
uv run python scripts/check_function_verb_prefix.py
uv run python scripts/check_package_size.py
uv run mypy lca lca-kernel gateway scripts
uv run pytest                                            # 全量
uv run vulture lca --min-confidence 80
uv run lca-ops diagnose plugin-tree profiles/web-standard.yaml
uv run lca-ops kernel compose profiles/web-standard.yaml --json
uv run lca-ops logs --scope boot --tail 10
```

## 5. Definition of Done

- [ ] `lca-kernel/` 顶层包,12 文件,每个 ≤ 200 行
- [ ] `lca-kernel/` 通过 `check_kernel_boundary.py`:零 `starlette/fastapi/uvicorn/gateway/transport` import
- [ ] `lca/plugins/transport/webserver/` 7 文件,`GatewayRouter` 是 mutable class(不 frozen + __setattr__)
- [ ] 4 个 routes plugin,每个 requires `gateway_router` + `kind=PROVIDER`
- [ ] `gateway/app.py` ≤ 60 行,**不再调 `boot_profile()`**
- [ ] `lca/application/api.py` 不再 import `set_default_ctx` / `_default_ctx_holder`(compat 注释保留)
- [ ] 3 个 typed JournalEvent(`BootProfileResolved / BootPluginFiberSpawned / BootObservabilityAssembled`)在 catalog 登记;`BootPluginFiberSpawned.stage` 引用 `Stage` IntEnum
- [ ] `Stage(IntEnum)` 在 `lca-kernel/stages.py` 单一定义,所有引用都走这里
- [ ] K6 Fail-loud:`install_fail_loud` + `create_shutdown_coordinator` 实装;SIGTERM → exit 0、SIGINT → exit 130、unhandledRejection → exit 1
- [ ] K7 BOOTSTRAP_NAMES:`lca/infrastructure/env/bootstrap.py` 列出白名单/前缀/黑名单;`load_layered_env` fail-loud 默认开启
- [ ] `lca-ops kernel {boot,serve,stop,reload,compose}` 5 个子命令可用
- [ ] `lca-ops logs --scope boot --tail 50` 输出 ≥ 3 条 boot event(BOOT+RESOLVE+OBSERVABILITY)
- [ ] 全量 `pytest` 通过,`mypy lca lca-kernel gateway scripts` 无 error,`vulture lca --min-confidence 80` 无新发现
- [ ] AGENTS.md §6 验证矩阵扩展:`lint-imports + check_kernel_boundary` 行
- [ ] `lca/infrastructure/env/` README + AGENTS.md 仓库地图同步

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `lca-kernel/` 顶层包需要 root `pyproject.toml` 改 packages | 提前在 PR-2 验证 `pip install -e .` 仍能找到 `lca_kernel`;如有问题回退为 `lca/harness/kernel/` 子包(妥协方案) |
| `set_default_ctx` 删除后所有调用点都需要改 | PR-5 实施前先 `grep -r 'set_default_ctx' lca/ scripts/ tests/`,列完整迁移清单;CI 切 error 前 6 周先发 warning |
| Stage IntEnum 改名会让 `lca-journal-emit-test.py` 失败 | PR-3 之前先 grep 所有 `stage="..."` 字符串字面量,逐一改为 `stage=Stage.X`;CI 阻断 |
| `BOOTSTRAP_NAMES` 白名单漏 LCA 当前实际用的 env 变量 | PR-1 实施前先 `grep -rhE 'os.environ\[|os\.getenv\(' lca/ scripts/` 列清单,保证白名单覆盖 |
| `gateway/app.py` thin factory 改造后旧测试假设的 30+ 路由仍在 | PR-5 之前先 `grep -r 'app.state\|create_app' tests/`,确认所有测试改用 `run_kernel + lifespan_adapter` |
| uvicorn `gateway.app:app` 启动契约破坏 | PR-5 保留 `--factory gateway.app:create_app` 入参,只是 create_app 内部不再调 boot_profile,改为从 `app.state.ctx` 读(ctx 由 lifespan_adapter 通过 lifespan startup 注入) |
| deepseek `host-webserver` 的 `Service.init` 在 cordis Python 这边需要等价机制 | 用 `setup` async 函数作为入口,listen 在 setup 内显式 await;dispose 走 `ctx.effect(dispose_callable)` |

## 7. 范围外(留待后续 ADR)

| 主题 | 备注 |
|---|---|
| ADR-0118 cordis-patch HMR(K8) | 单独 ADR,本期只占位 |
| ADR-0119 ACP/JSON-RPC transport | `lca/plugins/transport/acp/`,后续立项 |
| ADR-0120 stdio CLI transport | `lca/plugins/transport/cli/`,把 `scripts/lca-ops` 迁过去 |
| ADR-0121 `@plugin` 装饰器加 `invariants` 字段 | 后续(原 ADR-0111 决定 4 invariant.py 简并方案) |
| LcaService Protocol | ADR-0083 W6 提及,FileStoreService 改用,后续 |

## 8. 决策点(已锁定 2026-08-31)

| # | 决策 | 锁定答案 |
|---|---|---|
| **D1** | `lca-kernel/` 顶层包 vs `lca/harness/kernel/` 子包? | **顶层包**(`pyproject.toml` `packages.find include = ["lca*"]` glob 已支持) |
| **D2** | `set_default_ctx` 6 个月 deprecated vs 直接删? | **6 个月 deprecated**(目标 2027-02-28 退役;5 个直接调用 + 6 个间接引用) |
| **D3** | `lca-ops logs --scope boot` 默认显示哪些 stage? | **`all`**(Stage 枚举全部;后续可加 `--stage resolve` 过滤) |
| **D4** | `Stage` IntEnum 起始值 0 还是 1? | **1**(便于与日志 `seq` 从 0 开始区分) |
| **D5** | `BOOTSTRAP_FORBIDDEN` 包括 `LCA_PROFILE`? | **是**(profile 必须由 argv 决定,不被 .env 覆盖) |
| **D6** | transport namespace `lca/plugins/transport/` vs `lca/transport/`? | **`lca/plugins/transport/`**(跟 `seam_definitions/providers` 平级,plugin 概念清晰) |

## 9. ADR-0115 新增"游离于插件之外"边界清单(本轮回应用户)

ADR-0115 新增**决定 9(Kernel vs Plugin 边界硬约束)** + **决定 10(游离于插件之外完整清单)**,回应用户"还有那些游离于插件之外":

- **游离层(无法 plugin 化,共 4 类)**:
  1. **Kernel 自身**(`lca-kernel/` 顶层包)—— "启动 plugin 的东西"不能由 plugin 实现(循环依赖)
  2. **Composition Root**(`lca/application/` + `apps/cli/web/acp`)—— "选择 bundle + 装配 plugin 树"是单实例决策
  3. **Vendored 框架**(`cordis` / `pydantic` / `Cosmokit`)—— upstream 维护,LCA 只是 user
  4. **Python stdlib + 基础设施**(`os` / asyncio / signal 等;`lca/infrastructure/env/` 是延伸)

- **必须 plugin 化的层**:观测 seam/sink、能力 seam/provider、Transport、生命周期钩子、Phase executor / control slot、Team / Agent / Role、业务 tool/mode/adapter

- **Kernel-Plugin 通信唯一通道 = cordis Context**:`ctx.registry.plugin / ctx.effect / ctx.inject / ctx.provide / ctx.on`

- **5 个反模式清单**(被 lint-imports 阻断):kernel import plugin 路径 / plugin import kernel 内部模块 / plugin 之间直接 import / kernel 有 module-level 单例 / transport 反向调用 cognition/agent 业务

## 10. 后续 ADR 立项清单(本轮外)

| ADR | 主题 | 优先级 |
|---|---|---|
| ADR-0118 | cordis-patch HMR(K8 完整落地)+ `watchUserPatches()` | P1 |
| ADR-0119 | ACP/JSON-RPC transport(`lca/plugins/transport/acp/`) | P2 |
| ADR-0120 | stdio CLI transport(`lca/plugins/transport/cli/`)+ scripts/lca-ops 迁移 | P2 |
| ADR-0121 | `@plugin` 装饰器加 `invariants` 字段(原 ADR-0111 决定 4 简并方案) | P3 |
| ADR-0122 | snapshot/replay 模式(借鉴 deepseek `resolveConfigPath` snapshot) | P3 |
| ADR-0123 | LcaService Protocol(借鉴 deepseek `WebServer extends Service`,给 LCA FileStoreService 等长期实例用) | P3 |

---

**最终交付**:本 plan + 5 个 ADR(0115 新建 / 0116 新建 / 0117 新建 / 0111 修订 / 0112 修订)+ 2 个旧 ADR 标记 superseded + 1 个旧 plan 标记 superseded。

**等你拍板**:如果方案无误,回复"开始实施",我就按 PR-1 → PR-6 顺序串行提交(每个 PR 跑 AGENTS.md §6 全量验证),并 spawn 第 5 个 subagent 评审 BLOCK 修复 + 每个 PR merge 后跑 diff 核对 Definition of Done。