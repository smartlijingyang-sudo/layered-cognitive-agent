# AGENTS.md

LCA（Layered Cognitive Agent）是一个基于 vendored Cordis 的 Python 插件化认知 Agent 框架。**一切皆插件**：插件挂载通过 `cordis` `@plugin` 装饰器，扩展通过 seam 注册表，认知内核是封闭六步循环 + 双平面（认知 / 世界）。

变更前必读 [`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`](docs/design/2026-08-19-cognitive-primitive-constitution-v3.md)（**认知原语宪法 v3**，简称「宪法」）与 [`docs/specs/harness-spine-spec.md`](docs/specs/harness-spine-spec.md)（**Harness Spine Spec**，执行规约）。所有架构决策、跨层接口、新原语引入都要追溯到这两个文档之一。

## 0. 工程哲学：追问前提

**不打补丁，追问前提。** 遇到不合理的代码，先问：是机制本身有问题，还是在垃圾机制上做修补？

- 看到 `if/else` 链 → 问"是不是缺了一个注册表或策略模式"
- 看到重复逻辑 → 问"是不是抽象层没提对"
- 看到 workaround → 问"被绕过的东西该不该存在"
- 看到过深的调用链 → 问"是不是职责分错了"
- 主动清理死代码、废弃别名、过渡方案——`vulture` 只是兜底，人工判断优先
- 有更好的架构就提出来，不要沉默地往旧设计里塞新代码

宪法第 **C7** 条：每个原语默认 no-op；第 **C6** 条：改闭集必 ADR，默认否决。

## 1. 仓库布局

```
docs/
  adr/                          已采纳的架构决策（0001-0056）
  specs/harness-spine-spec.md   Harness 执行规约
  design/2026-08-19-cognitive-primitive-constitution-v3.md
                               认知原语宪法 v3
lca/
  contracts/
    atoms/                      枚举、ID、semantic keys、telemetry attrs
    mechanisms/                 跨层机制契约：EventBus / Hook / Registry / Seam
    models/                     纯数据 dataclass（core / observability / team）
    protocols/                  业务协议：infra / cognition / embodiment / runtime / orchestration
    harness/                    Harness 自身的契约：plugin / middleware / projection / session / agent
  layer0_infra/                 基础设施：llm / tools / transport / sandbox / observability / dsh / plane
  layer1_cognitive/             认知原语
    brain/                      ModularBrain + Reasoner + Critic + Synthesizer + decision_gates/
    body/                       ActionRegistry + SafeExecutor + ToolRegistry + SimpleBody
    perceive_hub.py             唯一 ContextManifested 发射者（PR3a）
    perceive_sink.py            ManifestSink 协议
    sensors/                    时钟 / journal / skill 目录 / workspace 制品 / workspace 指令
    collaboration/blackboard.py
    event_bus.py                emit / waterfall / serial 三模分发
    hook_registry.py            生命周期钩子
    memory/ member_status/      记忆与成员状态
  layer2_runtime/               CognitiveRuntime + StopRule + OutcomePolicy + Phase Middleware
  layer3_agent/                 CognitiveAgent + TeamHandle + OrchestrationStrategies
  layer4_app/                   组合根：composer / runtime_factory / team_wiring / harness_bridge
  harness/                      Harness 自身实现：profile / boot / session / agent / middleware / skills / workflow
  plugins/                      cordis 插件（37 个 .py + 子目录）
    seam_definitions/           纯声明 Bundle 插件（13 个 extension_point，零逻辑）
    llm_service.py tools_service.py session_service.py ...
                                Tier-1：服务定义
    providers/                  Tier-2：每 seam 一工厂（llm / tools / sandbox / memory / ...）
    brain/ reasoner/ synthesizer/ loop_cognitive.py team_lead/
                                Tier-3：行为实现
    dsh/bridge.py               DSH alien loop driver
    guards/                     Phase 中间件（已精简：仅 RepeatToolCall / ToolLoopBreaker 等少数）
    llm_resolver.py             LLM_API_KEY 唯一读取者；profile 切换 mode
    run_loop_driver_registry.py Loop 驱动注册中心（cognitive + dsh-bridge 注册到这里）
gateway/                        FastAPI 入口：app.py / openai_shim.py / runs/{api,execute,loop_drivers}
profiles/                       Profile YAML（默认 profiles/web-standard.yaml）
bundles/                        Bundle YAML（base.yaml + web-app.yaml + scenario-* + lead/researcher-*）
scripts/                        平台编排（lca-ops）与质量门禁（check_*.py）
vendor/{cordis,cosmokit,schemastery}/  cordis 1:1 Python 移植；pyproject 通过 [tool.uv.sources] 加载
lca/packages/                   deepseek-harness/packages 1:1 Python 镜像（Surface parity 由 check_port_surface.py 校验）
```

## 2. 架构约束

### 2.1 五层单向依赖

```
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent
```

`layer4_app` 是组合根，下层禁止反向 import。由 `lint-imports`（import-linter）+ `pyproject.toml` 的 4 个 contract 强制执行。

### 2.2 认知原语宪法 v3（强制）

**6 步闭集循环**（C1）：`perceive → think → gate → act → reflect → remember → stop`。插件只换实现，不在循环上开洞。

**双平面内核**（C2）：
- **认知平面**：Brain / Critic / Reasoner / SkillRouter / DecisionGate——只读 State，不写世界
- **世界平面**：Body / SafeExecutor / Sandbox——执行窄门，所有世界副作用必经此路

**8 个概念群**（§3.2）：State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition。群内原语 + 群内策略 + 观察 hook 三层分离。

**Reducer 唯一写 State**（C4）：Sensor / Gate / Body 禁止原地修改 AgentState，必须经 `reducer.apply_*`。

**Journal 唯一事实源**（C3 / ADR-0037）：模型可见事实必须可由 journal 重建。`SessionService.record(EventType, ...)` 是单一入口。

**Capability 衰减**（C5）：子代理 grant ⊆ 父代理。

### 2.3 Plugin 机制

- 全部基于 vendored **cordis** Python 移植（`taiyi-cordis` via `[tool.uv.sources]`）；不再使用 `PluginManifest / ExtensionPoint / PluginKind / ScopeKind`（已 deprecated，留在 `lca/contracts/harness/plugin.py` 仅做迁移期兼容）
- 公共契约：`cordis.Context.provide/inject/on/once/scope/dispose`（`PluginContext` Protocol 是迁移期别名）
- Bundle 通过 `resolve_profile()` → `boot_resolved_profile()` 加载（`boot_profile()` 为兼容门面）：深合并 patch、校验 Manifest、按 `provides→requires` DAG 启动（[ADR-0061](docs/adr/0061-plugin-manifest-resolve-boot.md)）
- 插件 Manifest：`@plugin(id=..., provides=..., requires=..., layer=L0–L4, kind=..., effects=..., test_suite=...)`（`lca.harness.plugin_api`）；感知/判决向群服务 `add()`（[ADR-0056](docs/adr/0056-plugin-group-contribution.md)）
- Seams：13 个 extension_point（`llm / sandbox / memory / state_store / search / tools / transport / skills / file_store / observability / agent_loop / session_service / system_prompt`），由 `lca.plugins.seam_definitions` 注入
- Loop 驱动注册：`lca-run-loop-driver-registry` 提供空 registry，`lca-loop-cognitive` / `lca-dsh-bridge` 注册自身 driver；`gateway/runs/execute.py:execute_run()` 按 run 配置解析。**无模块级单例**。
- 密钥只经 profile `{from_env:}` 进入；插件不得自行 `os.environ` 读凭证

## 3. 命令速查

### 3.1 平台编排：`./scripts/lca-ops`

无参打印手册。核心子命令：

| 命令 | 用途 |
|---|---|
| `status` / `heal` / `dev` / `restart` / `stop` | 全站生命周期 |
| `gateway` / `lobehub` / `infra` / `daemon` | 单服务管理（`start/stop/restart/status`） |
| `logs` | journal 事实流（`-v` 加 prompt/response，`-d` 加 delta，`--replay` 从 traces 回放） |
| `inspect-tree <profile.yaml>` | 解析后的插件树 + capability graph |
| `dump-profile <profile.yaml>` | 展开 bundle + patch 的 entries |
| `debug tree\|run\|scope` | cordis.Context 视图：tree / run 事件 / scope 服务解析 |
| `diagnose <alias>` | 内置诊断（model_not_seen / loop_stuck / memory_poisoned / approval_rejected） |
| `check-upstream [--sync]` | 对比 `lca/packages/` 与 `~/deepseek-harness/packages/` 的结构差异 |
| `provision` | sandbox-user daemon 部署（包 / venv / 用户 / 工作区 / CLI） |

输出人类可读 / `--json` 给 agent 用。

### 3.2 验证

全量慢在 `pytest --cov=lca`。**默认按 blast radius 选跑**；说不清影响、改契约 / 分层 / 公共 API 或准备提交时再升到全量。`pre-commit` 不跑 pytest。

#### 默认循环

```sh
uv run ruff check --fix <path> && uv run ruff format <path>
uv run pytest --no-cov <对应测试> -q
```

对应测试：同名 `tests/test_<模块>*.py`，或对改动符号 `rg` 到 `tests/`。`gateway/runs/` → `tests/test_run_*.py`。一次改多处就并上相关测试文件，不要为了省事改跑全量。

#### 影响范围表

| 改了什么 | 必跑 | 再加 |
|---|---|---|
| 仅 `docs/`、`roles/`、注释 | 无 | — |
| 仅测试 | ruff 改动路径 + 这些测试 `--no-cov` | — |
| 实现细节（单模块、无公共 API 扩散） | ruff + 对应测试 `--no-cov` | 签名/类型变了 → `uv run mypy lca/<包>` |
| 新增 / 挪动 import、挪模块 | 上一项 + `uv run lint-imports` | 分层 / 组合根 → `tests/test_layer_boundary.py` `tests/test_refactor_guards.py` |
| `gateway/`、`deploy/lobehub/patches/` | ruff + `tests/test_run_*.py` / `tests/test_gateway*.py` / `tests/test_lobehub*.py` | 改 patch 源后 `patch_lobehub.py apply --reset`（**不要直接改 `lobehub-ui/`**） |
| 删改被多处引用的符号 | 对应测试 + `uv run vulture lca --min-confidence 80` | 引用面大 → 全量 pytest |
| `contracts/`、Protocol、跨层公共签名、`pyproject.toml`、importlinter、注册表 / 枚举、journal catalog | 全量 | — |

层向上传染：改 `contracts` 视为全仓库；改 `layerN` 公共面至少覆盖本层测试和直接上层调用方。

#### 全量（提交 / PR / 升级条件触发；顺序不可乱）

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

`real_llm` 默认不跑。**声称通过前必须贴出所跑命令**；局部绿不能写成「流水线已过」。

### 3.3 质量门禁（pre-commit 自动跑）

| 脚本 | 强制 |
|---|---|
| `scripts/check_no_any.py` | 禁裸 `Any` 类型标注（白名单：`dict[str, Any]` / `**kwargs: Any` / `payload: Any` 等） |
| `scripts/check_no_bare_strings.py` | 领域语义必用枚举（`ActionType` / `TaskStatus` / `HookEvent` / ...） |
| `scripts/check_protocol_impl.py` | 实现 `contracts.Protocol` 的类**必须显式继承** |
| `scripts/check_plugin_typing.py` | 插件 `setup(ctx, config)` 与模块级 `build_*` 工厂必须有完整类型标注（兜底 mypy；与 `plugin()` 装饰器签名 `PluginSetupFn` 互为校验） |
| `scripts/check_assembly_purity.py` | `spawn.py` 不得有 `==` 字符串比较分支（契约 2：装配期只读不算） |
| `scripts/check_port_surface.py` | `lca/packages/` 与 `~/deepseek-harness/packages/` 的 public surface parity |
| `scripts/verify_md_links.py` | Markdown 相对链接必须解析（目标文件存在 + `#fragment` 指向真实标题） |
| `scripts/verify_doc_budgets.py` | 文档字数预算超限拒绝（预算清单在 `scripts/doc_budgets.json`） |

## 4. 编码规范

- 方法 ≤ 200 行，文件 ≤ 1500 行；超过就拆
- 公共接口必须类型标注；`contracts/` 用 stdlib `dataclass`
- **插件 `setup` 签名必须满足 `PluginSetupFn`**（`Callable[[PluginContext, BaseModel], Awaitable[None]]`，见 `lca/harness/plugin_api.py`）。`@plugin` 装饰器在签名层强制；`scripts/check_plugin_typing.py` 是绕过 mypy 时的确定性兜底。**未标注 `ctx: PluginContext` 的 setup 函数无法通过编译**——不要再加 `# type: ignore[no-untyped-def]`。
- **模块级 `build_*` 工厂函数必须完整标注**（参数 + 返回），否则 `check_plugin_typing.py` 阻断
- 层间只通过 Protocol 通信，同层通过依赖注入协作
- 多种实现 → `Protocol` + 注册表；外部集成 → 适配器
- 配置走 pydantic-settings / 环境变量；`LLM_API_KEY` 由 `lca.plugins.llm_resolver` 唯一读取
- 禁止魔数、硬编码密钥、裸 `except Exception`、`print`；用 `structlog`
- 不生成 TODO / FIXME 占位
- 文件以恰好一个换行结尾（`git diff --cached --check` 门禁）

## 5. 领域语言

### 5.1 Team 形态（ADR-0034）

- `Agent`：单角色；`Team`：members + **恰好一种**协作机制
- 有主导者：`Team(lead=TeamLead.board(pm))`，`lead.mandate ∈ {routing, consult, board}`
- 无主导者：`Team(coordination=Pipeline()|FanOut()|PeerRelay()|PeerSwarm()|Debate()|Graph(...))`
- `lead.mandate` 与 `coordination` 互斥，类型层不可同时存在
- 编排策略实现：`lca.layer3_agent.orchestration_strategies/{lead,sequential,parallel,debate,swarm,handoff,graph}.py`
- 场景 YAML 在 `bundles/scenario-*.yaml`；团队测试夹具在 `tests/fixtures/team_scenarios/`，加载用 `tests/support/scenario_loader.py`

### 5.2 认知原语命名

- 决策行动：`ActionType.{RESPOND, USE_TOOL, DELEGATE, HANDOFF, STOP, ASK_HUMAN}`
- 任务状态：`TaskStatus.{WORKING, COMPLETED, FAILED, ...}`
- 反射判定：`ReflectionVerdict.{ON_TRACK, NEEDS_CORRECTION, BLOCKED, DEGRADED_BUT_COMPLETED}`
- 钩子事件：`HookEvent.{ON_START, PRE_PERCEIVE, POST_PERCEIVE, PRE_THINK, POST_THINK, PRE_ACT, POST_ACT, PRE_REFLECT, POST_REFLECT, ON_ERROR, ON_COMPLETE}`
- 新增裸字符串 → 改用枚举；改枚举值字符串视为 break wire（PR6 ExecutionEnvelope）

## 6. 关键路径速查

| 关注点 | 位置 |
|---|---|
| 文档管理体系 | `docs/AGENTS.md`（层级分类 + 写作规范 + 字数预算） |
| 宪法原文 | `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` |
| Harness 执行规约 | `docs/specs/harness-spine-spec.md` |
| 已采纳 ADR | `docs/adr/`（0001-0056） |
| 平台编排入口 | `./scripts/lca-ops`（无参 = 手册） |
| Profile 默认 | `profiles/web-standard.yaml`（bundles + patch） |
| Bundle 集 | `bundles/{base,web-app,scenario-*,lead-standard,researcher-*-tools}.yaml` |
| 启动入口 | `lca/harness/profile/boot.py:boot_profile()` 异步返回 `cordis.Context` |
| 插件视图 | `lca-ops inspect-tree` / `lca-ops dump-profile` / `lca-ops debug tree` |
| 启动诊断 | `lca/harness/diagnostics/boot_report.py`（BootReport：plugins + capability graph） |
| Agent / Team 闭合 | `lca/layer4_app/spawn.py`（`spawn_agent` / `spawn_team`；ADR-0056） |
| Profile Resolve/Boot | `lca/harness/profile/{resolve,boot}.py`（ADR-0061） |
| 插件 Manifest API | `lca/harness/plugin_api.py`；Capability 键 `lca/contracts/capabilities.py` |
| LLM seam | `lca.plugins.llm_resolver`（env 唯一读取者）+ `lca.plugins.providers.llm`（adapter 工厂） |
| Loop 驱动 | `gateway/runs/loop_drivers.py:{CognitiveRunDriver, DshRunDriver}`，由 `lca-run-loop-driver-registry` 收集 |
| Prompt 模板 | `lca/layer1_cognitive/brain/prompts/*.md`；加载 `load_builtin_prompt` |
| Journal 词表 | `lca/contracts/models/observability/{journal,journal_catalog}.py`（v3 增 PR2/PR3a/PR4/PR6/PR7/PR8/PR9 控制原语） |
| 真实 LLM 测试 | `uv run pytest -m real_llm -v`（需 `LLM_API_KEY`） |
| 本地探针 | `uv run python scripts/run_team_mode.py` |
| 上游对齐 | `scripts/check_port_surface.py`（lca/packages ↔ ~/deepseek-harness/packages） |

## 7. 禁止事项

- 不绕过 pre-commit（`--no-verify`）
- 不让 `contracts` / `layer0~3` import `layer4_app`
- 不直接改 `lobehub-ui/`——改 `deploy/lobehub/patches/` 后 `patch_lobehub.py apply --reset`
- 不在 6 步循环上开洞、不引入新 step / 新事件词表 / 新插件 schema（**C6：改闭集必 ADR**）
- 不让 Sensor / Gate / Body 原地改 `AgentState`（**C4：Reducer 唯一写**）
- 不绕过 `LLM_API_KEY` 路径——所有 key 经 `lca.plugins.llm_resolver` 解析

## 8. 编辑本文件

本文件是 LCA 的根级 AGENTS 指引；保持条目独立、命令具体、链接高价值文档。需要新增指引前先问：是否应放进对应 ADR？是否属于宪法范围（→ 更新 spec 而不是本文件）？
