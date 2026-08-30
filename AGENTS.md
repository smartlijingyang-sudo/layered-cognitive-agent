# Layered Cognitive Agent（LCA）Coding Agent 指南

LCA（Layered Cognitive Agent）是基于 vendored Cordis 的 Python 插件化认知 Agent 框架。它把**事实、状态、认知、治理、执行、记忆、协作和组合**分成可替换、可验证的层次。本文件面向 coding agent，说明项目上下文、代码位置、架构边界、编码规范和验证方式；完整术语与认知模型见[《LCA 技术名词与结构化层次认知指南》](docs/specs/lca-structured-cognition-guide.md)。

## 1. 开始前必须知道

先读[认知原语宪法 v3](docs/design/2026-08-19-cognitive-primitive-constitution-v3.md)、[Harness Spine Spec](docs/specs/harness-spine-spec.md)、相关[ADR](docs/adr/)和[历史实施记录](history/)。文档中的目标态不等于当前生产事实；修改前必须核对当前入口、实现、测试和 Profile 配置，并标注迁移中或兼容路径。

### 工程思维：追问前提

不要在错误机制上堆补丁。遇到长 `if/else`，先考虑 Registry、Strategy 或 Provider；遇到重复逻辑，检查抽象层；遇到 workaround、死监听或深调用链，检查是否应删除、正式接入或重新划分职责。新增规则若影响架构，应写 ADR 或专题文档，不要默默扩大旧机制。

## 2. 仓库地图

```text
docs/                         规范、设计、ADR、计划和专题说明
lca/contracts/                Protocol、枚举、ID、模型、事件和跨层契约
lca/layer0_infra/             LLM、工具、传输、沙箱、文件、观测、插件内核
lca/layer1_cognitive/         感知、Brain、Reasoner、Critic、Gate、Body、Memory
lca/layer2_runtime/           Runtime、停止、恢复、阶段执行、中间件
lca/layer3_agent/             Agent、Team、委派和编排
lca/layer4_app/               组合根、spawn、runtime factory、team wiring
lca/harness/                  Profile、Boot、Session、Plugin API、声明式执行
lca/plugins/                  Seam、Provider、Loop Driver、Strategy、Tool Plugin
gateway/                      FastAPI、SSE、命令入口、运行执行和 projection
profiles/                     Profile YAML；默认 profiles/web-standard.yaml
bundles/                      Bundle 和 scenario 配置
scripts/                      lca-ops、迁移工具和质量门禁
tests/                        单元、契约、架构、集成和场景测试
vendor/                       Cordis、Cosmokit、Schemastery
```

| 关注点 | 入口 |
|---|---|
| Profile 解析/启动 | `lca/harness/profile/{resolve,boot}.py` |
| Plugin Manifest | `lca/harness/plugin_api.py` |
| Loop Driver | `gateway/runs/loop_drivers.py` |
| 声明式阶段图 | `lca/contracts/protocols/declarative_*.py`、`lca/harness/declarative/` |
| Brain / Prompt | `lca/layer1_cognitive/brain/` |
| Body / SafeExecutor | `lca/layer1_cognitive/body/` |
| Journal / Projection | `lca/contracts/models/observability/`、`lca/layer0_infra/observability/` |
| Agent / Team | `lca/layer4_app/spawn.py`、`lca/layer3_agent/` |
| 平台操作 | `./scripts/lca-ops` |

## 3. 架构不变量

### 五层单向依赖

```text
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent
```

`layer4_app` 是组合根，负责装配具体实现；下层不得反向 import 它。Gateway 是 Carrier，只负责 HTTP/SSE、typed command 和 projection，不直接绑定具体 Brain、Body 或 Loop。分层由 `lint-imports` 和 `pyproject.toml` 契约检查。

### 认知闭集与双平面

```text
perceive → think → gate → act → reflect → remember → stop
```

Brain、Reasoner、Critic、Synthesizer、SkillRouter、DecisionGate 属于认知平面，负责读取状态和形成判断；Body、SafeExecutor、Sandbox、Tool Pipeline 属于世界平面，负责受控副作用。插件可以替换实现，但不能无 ADR 增加步骤、核心事件词表或平行插件 schema。

| 不变量 | 要求 |
|---|---|
| C1 闭集 | 改变循环或核心事件语义必须先有 ADR，默认否决 |
| C2 双平面 | 认知不直接写世界；执行不私自改变认知状态 |
| C3 Journal | 模型可见输入、工具调用、协作报告和关键变化可追溯到 Journal；复用现有事件目录 |
| C4 Reducer | Sensor、Gate、Body 不得原地改 `AgentState`；产生 Delta/Event 后由 `reducer.apply_*` 应用 |
| C5 能力衰减 | 子 Agent 的 capability grant ⊆ 父 Agent grant |
| C6 最小化 | 原语默认 no-op；优先组合已有原语 |
| C7 控制/观察分离 | Command、Approval、Policy 改变系统；Journal、Trace、Metrics、Projection 负责记录或派生 |

### 插件与扩展

扩展路径优先是：

```text
Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle
```

`Seam` 是替换接口，`Provider` 是能力实现，`Adapter` 连接外部系统，`Registry` 管理实现，`Plugin` 是可装配行为，`Profile`/`Bundle` 负责组合。插件用 `@plugin` Manifest 声明 `id`、`provides`、`requires`、`layer`、`kind`、`effects`、`test_suite`；Profile 由 `resolve_profile()` 展开，再由 `boot_resolved_profile()` 按 `provides → requires` DAG 启动。使用现有 `cordis.Context` 的服务、事件、scope 和 dispose，不创建模块级单例或迁移期平行 schema。

常见 Seam：`llm`、`tools`、`transport`、`memory`、`sandbox`、`state_store`、`search`、`skills`、`file_store`、`observability`、`agent_loop`、`session_service`、`system_prompt`。密钥只能经 Profile 的 `{from_env: ...}` 进入，由 LLM Resolver 统一读取；插件不得自行读取 `os.environ`。

## 4. 结构化认知与数据所有权

按此链路定位问题：

```text
Fact → State → Decision / Plan → Verdict → Effect → Observation / Journal
```

`AgentState` 是当前投影；`Journal` 是追加式事实；`Checkpoint` 是状态和游标的恢复边界；`Projection` 是面向 UI、SSE 和诊断的派生视图。`Decision` 是候选意图，`Verdict` 是经过预算、权限、安全和审批后的允许结果，`Effect Receipt` 是副作用回执。

声明式运行中，`PluginSpec` 声明能力，Phase Graph 定义节点和边，`CompiledRunPlan` 负责编译，`PhaseInput`/`PhaseResult` 定义阶段数据，`PhaseRunCursor` 支持恢复，Interpreter/Driver 负责遍历，Outcome Projection 分别处理完成、审批暂停、失败和停止。图遍历不应负责写失败事实；失败投影不应决定下一条图边。横切行为优先使用 Middleware，不要无限增加 Hook。

## 5. Team、领域语言与编码规范

`Agent` 是单一角色；`Team` 是多个 Agent 加一种协作机制。`lead` 与 `coordination` 互斥。常见策略是 `Pipeline`、`FanOut`、`PeerRelay`、`PeerSwarm`、`Debate`、`Graph`，场景在 `bundles/scenario-*.yaml`。

领域语义必须使用枚举：`ActionType`（`RESPOND`、`USE_TOOL`、`DELEGATE`、`HANDOFF`、`STOP`、`ASK_HUMAN`）、`TaskStatus`、`ReflectionVerdict`、`HookEvent`。修改枚举值、事件 catalog、wire 字段或公共 Protocol 可能是破坏性变更，必须扩大验证范围。

公共接口完整类型标注；`contracts/` 使用标准库 `dataclass`；Protocol 实现显式继承；层间通过 Protocol，同层通过依赖注入；多实现使用 Registry，外部集成使用 Adapter。插件 `setup(ctx, config)` 必须满足 `PluginSetupFn`，模块级 `build_*` 工厂必须完整标注；不要用 `# type: ignore[no-untyped-def]` 掩盖问题。

禁止硬编码密钥、魔数、裸 `except Exception`、无理由的 `print`、无期限 TODO/FIXME 和未经说明的兼容别名。日志使用项目既有 `structlog`。方法超过 200 行或文件超过 1500 行时按职责拆分。提交前保持一个末尾换行并运行 `git diff --check`。

## 6. 命令与验证

`./scripts/lca-ops` 不带参数打印手册。常用命令：`status/heal/dev/restart/stop` 管理生命周期；`logs [-v] [-d] [--replay]` 查看 Journal；`inspect-tree <profile>` 查看插件树；`dump-profile <profile>` 展开配置；`debug tree|run|scope` 查看 Context；`diagnose <alias>` 运行诊断；`provision` 部署 daemon。需要给脚本消费时使用 `--json`。

默认循环：

```sh
uv run ruff check --fix <changed-path>
uv run ruff format <changed-path>
uv run pytest --no-cov <related-tests> -q
```

修改 `contracts/`、Protocol、公共签名、枚举、注册表、Journal Catalog、Profile 解析、import 边界、`pyproject.toml` 或多个运行层时，升级为：

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

`real_llm` 默认不运行；需凭证和明确意图时才执行 `uv run pytest -m real_llm -v`。报告结果必须写出实际命令；局部测试通过不能称为全量通过。

关键门禁包括：`check_protocol_impl.py`、`check_plugin_typing.py`、`check_no_any.py`、`check_no_bare_strings.py`、`check_assembly_purity.py`、`check_no_flat_runs.py`、`verify_md_links.py`、`verify_doc_budgets.py`。

| 改动 | 最低要求 |
|---|---|
| 仅文档、角色、注释 | `git diff --check`、Markdown 链接检查 |
| 单模块实现 | Ruff + 相关测试；改签名加局部 mypy |
| import / 模块移动 | 上一项 + `lint-imports` |
| Gateway、运行入口、LobeHub patch | Ruff + 对应 gateway/run/lobehub 测试；只改 patch 源 |
| 删除共享符号 | 相关测试 + `vulture`；影响大时全量 pytest |
| Contracts、Protocol、枚举、注册表、Journal、Profile | 全量验证 |

## 7. Git 与禁止事项

使用 Conventional Commits：`<type>(<scope>): <subject>`，正文说明做了什么和为什么；常用类型为 `feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`。一个提交只包含一个主题；不要使用 `--no-verify`，不要提交密钥、运行产物或环境文件；远程更新优先 `git pull --rebase`。

禁止反向依赖 `layer4_app`、无 ADR 扩大闭集、绕过 Reducer 改 State、绕过 Body 执行副作用、Gateway 绑定具体认知实现、插件自行读取凭证、通过新事件词表或新 schema 绕过现有机制。不要直接改生成的 `lobehub-ui/` 或 vendor；LobeHub 改 `deploy/lobehub/patches/` 后重新应用，vendor 改动必须有明确升级或修复理由。

根级 AGENTS.md 只保留 coding agent 高频需要的上下文、判断规则、强制约束、命令和验证矩阵；详细解释放专题文档，架构原因放 ADR，实施状态放计划或报告。
