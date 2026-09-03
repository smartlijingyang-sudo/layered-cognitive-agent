# Layered Cognitive Agent（LCA）Coding Agent 指南

LCA（Layered Cognitive Agent）是基于 vendored Cordis 的 Python 插件化认知 Agent 框架。它把**事实、状态、认知、治理、执行、记忆、协作和组合**分成可替换、可验证的层次。本文件面向 coding agent，说明项目上下文、代码位置、架构边界、编码规范和验证方式；完整术语与认知模型见[《LCA 技术名词与结构化层次认知指南》](docs/specs/lca-structured-cognition-guide.md)。

## 1. 开始前必须知道

先读[认知原语宪法 v3](docs/design/2026-08-19-cognitive-primitive-constitution-v3.md)、[Harness Spine Spec](docs/specs/harness-spine-spec.md)、相关[ADR](docs/adr/)和[历史实施记录](history/)。文档中的目标态不等于当前生产事实；修改前必须核对当前入口、实现、测试和 Profile 配置，并标注迁移中或兼容路径。

### 工程思维：追问前提 + 第一性原理

**默认原则**：

- **从第一性原理思考**。拿到需求先问"问题的本质是什么、最干净的形态是什么"，再决定怎么做。先选定机制边界再选 API，而不是反过来照抄别人的实现。
- **架构优雅优先**。代码是给未来的读者读的，不是给评审 pass 用的。模块边界、职责划分、依赖方向先于"能跑"。3 处重复就抽；长 `if/else` 先想 Strategy / Registry / Provider；workflow 扭曲就先重组 seam，再实现细节。
- **职责单一、模块边界清晰**。一个 Protocol / 一个 dataclass / 一个 Plugin 只承担一类关注点。同一段代码同时做"记录 + 计算 + 副作用"就该拆。看到一个函数里同时 import 4 层就应该停手。
- **不写临时/补丁式代码**。一次写对，不要写"先用 `try/except Exception: pass` 兜底回头再补"。TODO/FIXME 必须挂在 ADR 或 plan 里、给出删除条件，不允许留无期限占位符。兼容路径要写"何时删除"。
- **写代码顺手清理垃圾**。动到的区域里如果看到死代码、dead import、注释掉的旧实现、命名错的字段、用错命名空间的别名、藏在角落的 workaround —— **顺手清掉**。但**不**顺手重构不在本任务范围的东西（= scope creep）；清理的范围 = 同一文件、同一 seam、同一次合理改动能覆盖的部分。改完跑 `vulture` / `ruff --fix` / 相关测试确认。
- **正确性高于时效**。"少动一处"是常态，但"少动"不等于"将就"。把 `phase.think.fold` 这种一致性 bug 改对，往往就是 1 行 whitelist 加 1 行覆盖率测试。

**具体抓手**：

- 不要在错误机制上堆补丁。遇到长 `if/else`，先考虑 Registry、Strategy 或 Provider；遇到重复逻辑，检查抽象层；遇到 workaround、死监听或深调用链，检查是否应删除、正式接入或重新划分职责。
- 新增规则若影响架构，应写 ADR 或专题文档，不要默默扩大旧机制。
- 命名要"念得出来、查得到语义"：`emit_phase` 不是 `do_thing`；新枚举值要进 close-set 而不是塞 int/string 双轨。
- 拒绝"魔数、裸 `except Exception`、硬编码路径、无说明的 type: ignore、为了 page 能渲染加的特殊分支"——这些是技术债，留下要写 ADR 解释为什么必须留。
- 修改同时核对周边：契约改了 → 改 entry + 改 receivers + 改测试；Schema 改了 → 改 consumer + 改 migration。

**动手前 · 总闸 4 问（必答，不答不写）：**

1. **问题是什么？** —— 一句话，不含实现词。
2. **最干净的机制边界在哪？** —— 谁拥有真值、谁投影、谁副作用。
3. **现有 seam / Protocol / ADR 能否表达？** —— 能则扩展，勿新开平行机制。
4. **这次改动的删除条件是什么？** —— 兼容、TODO、双写路径必须写明。

答不出 1–3 → 停手，读 ADR / 契约 / 调用方再写代码。答不出 4 却留下兼容分支 → 禁止「合并心态」（本地也不提交那种）。

**契约改动必须闭环（漏一端 = 未完成，不是 follow-up）：**

| 你改了 | 必须同 PR 改 |
|---|---|
| Protocol / 公共签名 | 全部实现 + 测试 + 必要时 mypy |
| 枚举 / close-set / EP 名 | whitelist、catalog、emit 方、消费方、文档 |
| Schema / Journal 字段 | consumer + migration/兼容说明 + 测试 |
| 注册表 key / Plugin id | Profile/Bundle、`why-plugin`、相关装配测试 |

**兼容路径模板（必须填满，无删除日 = 无期限补丁 = 红灯）：**

```text
# COMPAT(delete-when: <条件>, tracking: ADR-0xxx|issue)
# 条件例: "writable.matrix 单写稳定 14 天" / "无调用方 rg 为零"
```

**离开前 · 卫生清单：** 无新增无期限 TODO；无双写同一 SSOT（除非 COMPAT 块写满删除条件）；无「记录+计算+副作用」未拆的新函数；死代码/死 import 已清（本 seam 内）；类型标注完整、无无理由 `type: ignore`；契约改了测双方、bugfix 有回归锁；`ruff check --fix`，需要时 `lint-imports` / mypy / vulture；`git diff --check`；提交信息说明「做了什么 / 为什么」。

**与「能跑」冲突时的优先级（自上而下递减）：** 不变量与契约正确 → 依赖方向与单一职责 → 可观测真值（能重建现场）→ 可删的兼容 → 局部性能微优化 → 「少改几行」的幻觉。「先让 CI 绿再补设计」仅当失败是无关 flakes 且本 PR 不扩大错误机制；绿灯若靠吞异常 / 跳过断言 / 双写假装一致 → 视为红灯。

## 2. 仓库地图

```text
docs/                         规范、设计、ADR、计划和专题说明
docs/notes/                   Agent Notes — 单点契约 / 原语 / Seam / Profile / runbook / postmortem 的新决策(老 ADR 不动);详见 docs/notes/README.md
lca/contracts/                Protocol、枚举、ID、模型、事件和跨层契约
lca/infrastructure/             LLM、工具、传输、沙箱、文件、观测、插件内核
lca/infrastructure/env/         进程级 env 白名单 + K7 BOOTSTRAP_NAMES(ADR-0117)
lca/cognition/         感知、Brain、Reasoner、Critic、Gate、Body、Memory
lca/runtime/           Runtime、停止、恢复、阶段执行、中间件
lca/agent/             Agent、Team、委派和编排
lca/application/               组合根、spawn、runtime factory、team wiring
lca/harness/                  Profile、Boot、Session、Plugin API、声明式执行
lca/plugins/                  Seam、Provider、Loop Driver、Strategy、Tool Plugin
lca/plugins/transport/        Webserver route registry + lifespan + 4 routes plugin(ADR-0112)
lca_kernel/                   顶层包:编译 profile → 运行中进程(ADR-0115 K1–K8)
profiles/                     Profile YAML；默认 profiles/web-standard.yaml
bundles/                      Bundle 和 scenario 配置
scripts/                      lca-ops、迁移工具和质量门禁
tests/                        单元、契约、架构、集成和场景测试
vendor/                       Cordis、Cosmokit、Schemastery
```

| 关注点 | 入口 |
|---|---|
| Profile 解析/启动 | `lca/harness/profile/{resolve,boot}.py`、`lca_kernel/compile_profile` |
| Plugin Manifest | `lca/harness/plugin_api.py` |
| Loop Driver | `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py` |
| 声明式阶段图 | `lca/contracts/protocols/declarative_*.py`、`lca/harness/declarative/` |
| Kernel(compile → run) | `lca_kernel/`(K1–K8;public 面在 `lca_kernel/__init__.py`) |
| Kernel ↔ Transport 桥 | `lca/plugins/transport/webserver/lifespan_adapter.py` |
| Webserver route registry | `lca/contracts/protocols/gateway_router.py`(文件路径沿用历史名,内容是 ADR-0119 之后的 webserver route Protocol)、`lca/plugins/transport/webserver/router.py`(实现类名 `GatewayRouter` 沿用历史) — 详见 ADR-0119-followup |
| Routes plugin | `lca/plugins/transport/webserver/routes_{health_options,runs_sessions,openai_compat_files,device}.py` |
| Env 白名单(K7) | `lca/infrastructure/env/bootstrap.py` |
| Brain / Prompt | `lca/cognition/brain/` |
| Body / SafeExecutor | `lca/cognition/body/` |
| Journal / Projection | `lca/contracts/models/observability/`、`lca/infrastructure/observability/` |
| Agent / Team | `lca/application/spawn.py`、`lca/agent/` |
| 平台操作 | `./scripts/lca-ops`；按症状路由的命令矩阵见 §6，单 run 调试心智模型见 §6.1 |

## 3. 架构不变量

### 五层单向依赖

```text
contracts → infrastructure → cognition → runtime → agent
```

`application` 是组合根，负责装配具体实现；下层不得反向 import 它。Webserver transport 是 Carrier，只负责 HTTP/SSE、typed command 和 projection，不直接绑定具体 Brain、Body 或 Loop。分层由 `lint-imports` 和 `pyproject.toml` 契约检查。

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

`./scripts/lca-ops` 不带参数打印分层手册。**详细命令清单、debug SOP、工具对照表都在 [`docs/debug/run-debug-guide.md`](../debug/run-debug-guide.md)**（与 CLI 实测对齐，CLI 改动时改 docs/debug，不要改本节）。本节只留 coding agent 最常用的指针 + 验证矩阵。

### "最新一次 run 全面分析"流程（最常用触发）

用户表达"**最新一次 run** / **刚才那个 run** / **最近一次** / **上一个 run** / **看看刚才发生了什么** / **分析一下这次**" → **直接按这个流程走，不要先去翻代码、问 run_id、或 ls traces/runs**。

```sh
# 1. 取最新 run_id（pointer 文件，不是 ls -t）
LATEST=$(jq -r .run_id traces/latest.json)

# 2. 一键 8 段诊断（首选；所有症状入口）
./scripts/lca-ops debug-run "$LATEST"
#    注：[3/8] kernel.log 多数 run 没有，[5/8] 不含完整 traceback。

# 3. 看完整 spine 事件流（理解过程；模型所见即日志）
#    表格视图（控制点 + channel + outcome）：
./scripts/lca-ops journal logs -r "$LATEST" -v
#    树视图（人读；不带 run_id 默认最新一个；--human：缩进 + payload 原文 + Δms + 自动折叠 reducer.apply/token 噪声）：
./scripts/lca-ops journal trace            # 最新 run
./scripts/lca-ops journal trace "$LATEST"  # 显式 run_id

# 3.5 【必跑】读 run 目录的 <sha256>.json sidecar：traceback 通常在这里
#      不是在 events.jsonl（大 event > 4 KB → I10 offload：FileSink._ATOMIC_THRESHOLD）。
#      debug-run [2/8] journal 只读主 ledger，看不到完整 traceback。
SIDECAR=$(ls traces/runs/"$LATEST"/*.json 2>/dev/null \
  | grep -vE 'events\.jsonl|manifest\.json|profile_snapshot\.json' | head -1)
[ -n "$SIDECAR" ] && jq -r '
  "exception_class: \(.payload.exception_class // "-")",
  "exception_message: \(.payload.exception_message // "-")",
  "source_location: \(.payload.source_location // "-")",
  (.payload.traceback_text // "(no traceback_text)")
' "$SIDECAR"

# 4. 失败原因投影（仅 run 失败时有意义）
./scripts/lca-ops explain "$LATEST"

# 5. step 树 / 因果链 / narrative（早期失败的 run 可能 journal.json 不存在，正常）
./scripts/lca-ops journal steps "$LATEST" 2>/dev/null
./scripts/lca-ops journal narrative "$LATEST" 2>/dev/null
```

**口语映射**（agent 看到这些词就直接走流程，不要先分析语义）：

| 用户说 | 走的流程 |
|---|---|
| "最新一次 run" / "刚才那个" / "上次" / "最近" | 上面 5 步全套**含 3.5 sidecar** |
| "分析一下这次" / "看看发生了什么" | 上面 1-3 + **3.5 sidecar** |
| "为啥这次失败" / "这次出错了" | 上面 1-2 + **3.5 sidecar**(traceback 的第一站) + 4 |
| "理解一下过程" / "走了一遍啥逻辑" | 上面 1 + 3 + 5 |
| "DSH 风格轨迹" / "给我个 HTML" | 加 `./scripts/lca-ops journal trajectory "$LATEST"` |
| "模型都做了啥" / "调了啥工具" | `./scripts/lca-ops trace "$LATEST" --focus llm\|tools\|delegation`（`--focus` 是 trace 的选项；`journal logs` 不支持） |
| "给我个像 journal 那样的树视图" / "人读 trace" | `./scripts/lca-ops journal trace`（**默认 --human**：树缩进 + Δms + payload 原文，默认最新 run） |

**取 run_id 的硬规则**：永远 `jq -r .run_id traces/latest.json`，**不要** ls、find、按 mtime 排序——pointer 文件是 SSOT。

### 最常用命令指针

| 场景 | 第一调用 | 失败退路 |
|---|---|---|
| 不知道 LCA 服务在不在跑 | `./scripts/lca-ops status --json` | `./scripts/lca-ops heal` |
| 刚改完代码想重启 | `./scripts/lca-ops kernel-restart` | `./scripts/lca-ops kernel_serve` 打印启动命令 |
| **触发一个新 run** | **`./scripts/lca-ops runs create --user-text "..."`** | `curl -X POST http://127.0.0.1:8765/runs -d '{"messages":...}'` |
| run 失败定位 | **`./scripts/lca-ops debug-run <run_id>`** | `debug-env <run_id>` 只看摘要 |
| 看完整流程 | `./scripts/lca-ops trace <run_id> --focus llm\|tools\|delegation` | `./scripts/lca-ops journal trace`（**默认 --human** + 默认最新 run） |
| 失败原因投影 | `./scripts/lca-ops explain <run_id>` | `minimal-repro <run_id>` |
| profile 拓扑 | `./scripts/lca-ops inspect-tree <profile>` | `dump-profile <profile>` |
| 能力归属 | `./scripts/lca-ops why <capability>` / `why-plugin <id>` | `graph <profile>` |
| 审计 hardcode / Reducer 单写 | `./scripts/lca-ops audit-control-surface` / `audit-state-writers` / `audit-direct-commands` / `audit-hook-attach` | `audit` |
| ADR 监督 / 历史迁移 | `./scripts/lca-ops status-adr-supervision` | `./scripts/lca-ops diagnose-package-organization` |
| 预设症状诊断 | `./scripts/lca-ops diagnose-{model-not-seen,loop-stuck,memory-poisoned,approval-rejected}` | `docs/debug/run-debug-guide.md` §5 |
| DSH 风格 HTML 轨迹 | `./scripts/lca-ops journal trajectory` | `journal narrative` |

### 通用参数

`--json` 结构化 JSON（给 agent）；`-q` / `--quiet` 少说话；`-c PATH` 配置，默认 `./lca-ops.yaml`；密码文件 `.lobehub-stack/sudo.pass`。需要给脚本消费时统一加 `--json`。

> **命令细节、日志/SSOT 路径、fail-loud 开关、常见症状映射、对照表**全部在 [`docs/debug/run-debug-guide.md`](../debug/run-debug-guide.md)。改命令时**改那一处**，本节作为指针不动。

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

关键门禁包括：`check_protocol_impl.py`、`check_plugin_typing.py`、`check_no_any.py`、`check_no_bare_strings.py`、`check_assembly_purity.py`、`check_no_flat_runs.py`、`verify_md_links.py`、`verify_doc_budgets.py`、`scripts/check_kernel_boundary.py`(本批 PR-7 增,聚合 `tests/lca_kernel/test_boundary.py` AST + 全量 kernel 测试 + importlinter `kernel-domain-isolation` / `transport-isolation`)、importlinter 契约 `kernel-domain-isolation` + `transport-isolation`(pyproject.toml;PR-7 重配为 forbidden top-level `lca_kernel` + `ignore_imports` 白名单,因 importlinter 2.13 不支持 forbid 外部包子模块)。

| 改动 | 最低要求 |
|---|---|
| 仅文档、角色、注释 | `git diff --check`、Markdown 链接检查 |
| 单模块实现 | Ruff + 相关测试；改签名加局部 mypy |
| import / 模块移动 | 上一项 + `lint-imports` |
| 路由 + 运行入口 + LobeHub patch | Ruff + 对应 routes/run/lobehub 测试；只改 patch 源 |
| 删除共享符号 | 相关测试 + `vulture`；影响大时全量 pytest |
| `lca-kernel/` / `lca/plugins/transport/` / `lca/infrastructure/env/` | `scripts/check_kernel_boundary.py` + importlinter `kernel-domain-isolation` & `transport-isolation` + 87 + 24 + 19 kernel/transport/env 测试 (含本批新增 28 项 K8 HMR + 5 项 boot event emission) |
| Contracts、Protocol、枚举、注册表、Journal、Profile | 全量验证 |

## 7. Git 与禁止事项

使用 Conventional Commits：`<type>(<scope>): <subject>`，正文说明做了什么和为什么；常用类型为 `feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`。一个提交只包含一个主题；不要使用 `--no-verify`，不要提交密钥、运行产物或环境文件；远程更新优先 `git pull --rebase`。

禁止反向依赖 `application`、无 ADR 扩大闭集、绕过 Reducer 改 State、绕过 Body 执行副作用、Gateway 绑定具体认知实现、插件自行读取凭证、通过新事件词表或新 schema 绕过现有机制。不要直接改生成的 `lobehub-ui/` 或 vendor；LobeHub 改 `deploy/lobehub/patches/` 后重新应用，vendor 改动必须有明确升级或修复理由。

根级 AGENTS.md 只保留 coding agent 高频需要的上下文、判断规则、强制约束、命令和验证矩阵；详细解释放专题文档，架构原因放 ADR，实施状态放计划或报告。
