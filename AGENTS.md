# Layered Cognitive Agent（LCA）Coding Agent 指南

LCA 是基于 vendored Cordis 的 Python 插件化认知 Agent 框架。改 `lca/` / `lca_kernel/` 前必读 [docs/architecture.md](docs/architecture.md);文档规则看 [docs/AGENTS.md](docs/AGENTS.md);Agent Notes 决策记录看 [docs/notes/README.md](docs/notes/README.md)。

`CLAUDE.md` 是本文件软链,改本文件即可生效。

## 1. 动手前必须知道

### 工程思维:追问前提 + 第一性原理

**默认原则**:

- **从第一性原理思考**。拿到需求先问"问题的本质是什么、最干净的形态是什么",再决定怎么做。先选定机制边界再选 API,而不是反过来照抄别人的实现。
- **架构优雅优先**。代码是给未来的读者读的,不是给评审 pass 用的。模块边界、职责划分、依赖方向先于"能跑"。3 处重复就抽;长 `if/else` 先想 Strategy / Registry / Provider;workflow 扭曲就先重组 seam,再实现细节。
- **职责单一、模块边界清晰**。一个 Protocol / 一个 dataclass / 一个 Plugin 只承担一类关注点。同一段代码同时做"记录 + 计算 + 副作用"就该拆。看到一个函数里同时 import 4 层就应该停手。
- **不写临时/补丁式代码**。一次写对,不写"先用 `try/except Exception: pass` 兜底回头再补"。TODO/FIXME 必须挂在 ADR 或 plan 里、给出删除条件,不允许留无期限占位符。兼容路径要写"何时删除"。
- **写代码顺手清理垃圾**。动到的区域里如果看到死代码、dead import、注释掉的旧实现、命名错的字段、用错命名空间的别名、藏在角落的 workaround —— **顺手清掉**。但**不**顺手重构不在本任务范围的东西(= scope creep);清理的范围 = 同一文件、同一 seam、同一次合理改动能覆盖的部分。改完跑 `vulture` / `ruff --fix` / 相关测试确认。
- **正确性高于时效**。"少动一处"是常态,但"少动"不等于"将就"。

**动手前 · 总闸 4 问(必答,不答不写):**

1. **问题是什么?** —— 一句话,不含实现词。
2. **最干净的机制边界在哪?** —— 谁拥有真值、谁投影、谁副作用。
3. **现有 seam / Protocol / ADR 能否表达?** —— 能则扩展,勿新开平行机制。
4. **这次改动的删除条件是什么?** —— 兼容、TODO、双写路径必须写明。

答不出 1–3 → 停手,读 ADR / 契约 / 调用方再写代码。答不出 4 却留下兼容分支 → 禁止"合并心态"(本地也不提交那种)。

**契约改动必须闭环(漏一端 = 未完成,不是 follow-up):**

| 你改了 | 必须同 PR 改 |
|---|---|
| Protocol / 公共签名 | 全部实现 + 测试 + 必要时 mypy |
| 枚举 / close-set / EP 名 | whitelist、catalog、emit 方、消费方、文档 |
| Schema / Journal 字段 | consumer + migration/兼容说明 + 测试 |
| 注册表 key / Plugin id | Profile/Bundle、`why-plugin`、相关装配测试 |

**兼容路径模板(必须填满,无删除日 = 无期限补丁 = 红灯):**

```text
# COMPAT(delete-when: <条件>, tracking: ADR-0xxx|issue)
# 条件例: "writable.matrix 单写稳定 14 天" / "无调用方 rg 为零"
```

**离开前 · 卫生清单:** 无新增无期限 TODO;无双写同一 SSOT(除非 COMPAT 块写满删除条件);无"记录+计算+副作用"未拆的新函数;死代码/死 import 已清(本 seam 内);类型标注完整、无无理由 `type: ignore`;契约改了测双方、bugfix 有回归锁;`ruff check --fix`,需要时 `lint-imports` / mypy / vulture;`git diff --check`;提交信息说明"做了什么 / 为什么"。

**与"能跑"冲突时的优先级(自上而下递减):** 不变量与契约正确 → 依赖方向与单一职责 → 可观测真值(能重建现场)→ 可删的兼容 → 局部性能微优化 → "少改几行"的幻觉。

## 2. 仓库地图

```text
docs/                 规范、设计、ADR、计划和专题说明
docs/notes/           Agent Notes — 单点契约 / 原语 / Seam / Profile / runbook / postmortem(老 ADR 不动);见 docs/notes/README.md
lca/contracts/        Protocol、枚举、ID、模型、事件、跨层契约
lca/infrastructure/   LLM、工具、传输、沙箱、文件、观测、插件内核
lca/infrastructure/env/  进程级 env 白名单 + K7 BOOTSTRAP_NAMES(ADR-0117)
lca/cognition/        感知、Brain、Reasoner、Critic、Gate、Body、Memory
lca/runtime/          Runtime、停止、恢复、阶段执行、中间件
lca/agent/            Agent、Team、委派和编排
lca/application/      组合根、spawn、runtime factory、team wiring
lca/harness/          Profile、Boot、Session、Plugin API、声明式执行
lca/plugins/          Seam、Provider、Loop Driver、Strategy、Tool Plugin
lca_kernel/           顶层包:编译 profile → 运行中进程(ADR-0115 K1–K8)
profiles/             Profile YAML;默认 profiles/web-standard.yaml
bundles/              Bundle 和 scenario 配置
scripts/              lca-ops、迁移工具和质量门禁
tests/                单元、契约、架构、集成和场景测试
vendor/               Cordis、Cosmokit、Schemastery
```

| 关注点 | 入口 |
|---|---|
| Profile 解析/启动 | `lca/harness/profile/{resolve,boot}.py`、`lca_kernel/compile_profile` |
| Plugin Manifest | `lca/harness/plugin_api.py` |
| Loop Driver | `lca/plugins/transport/webserver/handlers/runs/execute/loop_drivers.py` |
| 声明式阶段图 | `lca/contracts/protocols/declarative_*.py`、`lca/harness/declarative/` |
| Kernel ↔ Transport 桥 | `lca/plugins/transport/webserver/lifespan_adapter.py` |
| Webserver route registry | `lca/contracts/protocols/gateway_router.py` + `lca/plugins/transport/webserver/router.py`(ADR-0119-followup)|
| Routes plugin | `lca/plugins/transport/webserver/routes_*.py` |
| Brain / Prompt | `lca/cognition/brain/` |
| Body / SafeExecutor | `lca/cognition/body/` |
| Journal / Projection | `lca/contracts/models/observability/`、`lca/infrastructure/observability/` |
| Agent / Team | `lca/application/spawn.py`、`lca/agent/` |
| 平台操作 | `./scripts/lca-ops`;命令矩阵见 §6 |

## 3. 架构不变量

### 五层单向依赖

```text
contracts → infrastructure → cognition → runtime → agent
```

`application` 是组合根,负责装配具体实现;下层不得反向 import 它。Webserver transport 是 Carrier,只负责 HTTP/SSE、typed command 和 projection,不直接绑定具体 Brain、Body 或 Loop。分层由 `lint-imports` 和 `pyproject.toml` 契约检查。

### 认知闭集与双平面

```text
perceive → think → gate → act → reflect → remember → stop
```

Brain、Reasoner、Critic、Synthesizer、SkillRouter、DecisionGate 属于认知平面;Body、SafeExecutor、Sandbox、Tool Pipeline 属于世界平面。插件可以替换实现,但不能无 ADR 增加步骤、核心事件词表或平行插件 schema。

| 不变量 | 要求 |
|---|---|
| C1 闭集 | 改变循环或核心事件语义必须先有 ADR,默认否决 |
| C2 双平面 | 认知不直接写世界;执行不私自改变认知状态 |
| C3 Journal | 模型可见输入、工具调用、协作报告和关键变化可追溯到 Journal;复用现有事件目录 |
| C4 Reducer | Sensor、Gate、Body 不得原地改 `AgentState`;产生 Delta/Event 后由 `reducer.apply_*` 应用 |
| C5 能力衰减 | 子 Agent 的 capability grant ⊆ 父 Agent grant |
| C6 最小化 | 原语默认 no-op;优先组合已有原语 |
| C7 控制/观察分离 | Command、Approval、Policy 改变系统;Journal、Trace、Metrics、Projection 负责记录或派生 |

### 插件与扩展

扩展路径优先:`Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle`。插件用 `@plugin` Manifest 声明 `id`、`provides`、`requires`、`layer`、`kind`、`effects`、`test_suite`;Profile 由 `resolve_profile()` 展开,再由 `boot_resolved_profile()` 按 `provides → requires` DAG 启动。密钥只能经 Profile 的 `{from_env: ...}` 进入,由 LLM Resolver 统一读取;插件不得自行读取 `os.environ`。详见 [docs/architecture.md](docs/architecture.md)。

## 4. 结构化认知

`AgentState` 是当前投影;`Journal` 是追加式事实;`Checkpoint` 是状态和游标的恢复边界;`Projection` 是面向 UI、SSE 和诊断的派生视图。`Decision` 是候选意图,`Verdict` 是经过预算、权限、安全和审批后的允许结果,`Effect Receipt` 是副作用回执。完整链路与闭集定义见 [docs/specs/lca-structured-cognition-guide.md](docs/specs/lca-structured-cognition-guide.md);Team 协作语义见 [docs/specs/glossary.md](docs/specs/glossary.md)。

## 5. Conventions

- **类型标注完整**;`contracts/` 用标准库 `dataclass`;Protocol 实现显式继承;层间通过 Protocol,同层通过依赖注入;多实现使用 Registry,外部集成使用 Adapter。
- **命名要念得出来、查得到语义**:`emit_phase` 不是 `do_thing`;新枚举值进 close-set,不塞 int/string 双轨。
- **方法 ≤ 200 行、文件 ≤ 1500 行**,超限按职责拆分。提交前保持一个末尾换行并跑 `git diff --check`。
- **JSDoc / docstring 写完整契约**:precondition、failure 语义、时序、所有权、外部后果——**不**复述代码、不写 walkthrough、不留 reviewer residue。完整规则链 [.agents/skills/lca-prose-standard](.agents/skills/lca-prose-standard/SKILL.md)。
- **不留无期限 placeholder**:TODO/FIXME 必须挂在 ADR 或 plan 里、给出删除条件。Compat 模板见 §1。
- **不写魔数、裸 `except Exception`、无说明的 `type: ignore`、硬编码路径**;留下了要写 ADR 解释为何必须留。
- **日志用项目既有 `structlog`**,不私自 `print()`。
- **测试分层**(单元 / 契约 / 架构 / 集成 / 场景),`scripts/check_*` 与 `scripts/verify_*` 守护。Flaky 测试修测试不修 normalizer;见 [.agents/skills/lca-ci-test-reliability](.agents/skills/lca-ci-test-reliability/SKILL.md)。
- **Common commits** 用 `<type>(<scope>): <subject>`(Conventional Commits),正文说"做了什么 / 为什么"。
- **邻接原则**:改一处,顺带清本 seam 死代码/死 import;**不**顺手重构范围外的东西(。

### Plugin 范式(`lca/plugins/` 下)

每个 plugin **一个 .py 文件**,目录名 = `kind`,入口唯一 = `@plugin(...)` 装饰器。

```text
@plugin(
    id="lca.plugins.<dir>.<name>",     # 短 id 与目录层级对齐
    provides=("..."),                  # capability key
    requires=("..."),                  # 依赖的 capability
    layer="L0".."L4",                  # 显式层级
    kind=PluginKind.PROVIDER | SEAM | PRIMITIVE | BRIDGE,
    effects=(EffectClass.FILESYSTEM,), # 副作用类必声明;空 = NONE
    test_suite="tests/plugins/<dir>/<test>.py",
    description="一句话:做什么 + 不做什么",
)
async def setup_<name>(ctx: PluginContext, config: Config) -> None: ...
```

- **禁止**:`lca/plugins/<dir>/<subdir>/manifest.py + plugin.py` 双文件;`__init__.py` 写 `@plugin`;同 id 在多个文件
- **bundle 形态**:`bundles/<bundle>.yaml:plugins:` 列短 id,**不引路径**
- **校验**:`./scripts/lca-ops audit-plugin-shape`(effects 缺失 / 双形态残留 / 同 id 镜像);基线见 `docs/notes/baselines/plugin-shape.json`
- **新 plugin 必须满足以上三条**,存量违例在 `docs/notes/implemented/seam/2026-09-03-plugin-shape-baseline.md` delete-when 跟踪

## 6. 命令与验证

`./scripts/lca-ops` 不带参数打印分层手册;`./scripts/lca-ops <cmd> --help` 看子命令。

### Before X,读 Y.md

- **改单 run 调试 / 解读失败 traceback / 看 journal 树视图** → [docs/debug/README.md](docs/debug/README.md)(含"5 步 debug-run + 口语映射")
- **改 Journal / Trace / Metrics / Projection** → [docs/specs/harness-spine-spec.md](docs/specs/harness-spine-spec.md)
- **写生命周期 / 并发 / subprocess / 拆解 teardown 代码** → 防御性模式专题(规划中,先参考 [.agents/skills/lca-ci-test-reliability](.agents/skills/lca-ci-test-reliability/SKILL.md))
- **写散文 / comment / prompt** → [.agents/skills/lca-prose-standard](.agents/skills/lca-prose-standard/SKILL.md) + [.agents/skills/lca-trim-cot-leakage](.agents/skills/lca-trim-cot-leakage/SKILL.md)
- **写新 Agent Note** → [.agents/skills/lca-write-note](.agents/skills/lca-write-note/SKILL.md);归档 [.agents/skills/lca-archive-notes](.agents/skills/lca-archive-notes/SKILL.md)

### 最常用命令指针

| 场景 | 第一调用 | 失败退路 |
|---|---|---|
| 不知道 LCA 服务在不在跑 | `./scripts/lca-ops status --json` | `./scripts/lca-ops heal` |
| 刚改完代码想重启 | `./scripts/lca-ops kernel-restart` | `./scripts/lca-ops kernel_serve` 打印启动命令 |
| 触发一个新 run | `./scripts/lca-ops runs create --user-text "..."` | `curl -X POST http://127.0.0.1:8765/runs -d '{...}'` |
| run 失败定位 | `./scripts/lca-ops debug-run <run_id>` | `debug-env <run_id>` 只看摘要 |
| 看完整流程 | `./scripts/lca-ops trace <run_id> --focus llm\|tools\|delegation` | `./scripts/lca-ops journal trace`(默认 --human + 默认最新 run) |
| 失败原因投影 | `./scripts/lca-ops explain <run_id>` | `minimal-repro <run_id>` |
| traceback 一刀命中 | `./scripts/lca-ops journal exceptions <run_id>` | `--grep <Class>` / `--json` |
| profile 拓扑 | `./scripts/lca-ops inspect-tree <profile>` | `dump-profile <profile>` |
| 能力归属 | `./scripts/lca-ops why <capability>` / `why-plugin <id>` | `graph <profile>` |
| 审计 hardcode / Reducer 单写 | `./scripts/lca-ops audit-control-surface` / `audit-state-writers` / `audit-direct-commands` / `audit-hook-attach` | `audit` |
| ADR 监督 / 历史迁移 | `./scripts/lca-ops status-adr-supervision` | `./scripts/lca-ops diagnose-package-organization` |
| notes/ 体检(新决策门禁) | `./scripts/lca-ops notes-check` | `python scripts/check_notes_tree.py` |
| ADR 健康审计(诊断 only,不动 ADR) | `./scripts/lca-ops notes-audit` | `python scripts/audit_adr_health.py --out docs/notes/audit-<date>.md` |
| docs/ 散文 stale-time 扫描 | `./scripts/lca-ops notes-slop` | `python scripts/verify_doc_slop.py` |
| notes/ 枚举(JSON 给 agent) | `./scripts/lca-ops notes-list --json` | `python` 读 `docs/notes/` |
| 预设症状诊断 | `./scripts/lca-ops diagnose-{model-not-seen,loop-stuck,memory-poisoned,approval-rejected}` | [docs/debug/run-debug-guide.md](docs/debug/run-debug-guide.md) §5 |
| DSH 风格 HTML 轨迹 | `./scripts/lca-ops journal trajectory` | `journal narrative` |

### 默认循环

```sh
uv run ruff check --fix <changed-path>
uv run ruff format <changed-path>
uv run pytest --no-cov <related-tests> -q
```

修改 `contracts/`、Protocol、公共签名、枚举、注册表、Journal Catalog、Profile 解析、import 边界、`pyproject.toml` 或多个运行层时,升级为:

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

`real_llm` 默认不运行;需凭证和明确意图时才执行 `uv run pytest -m real_llm -v`。报告结果必须写出实际命令;局部测试通过不能称为全量通过。完整推送前检查 [.agents/skills/lca-pre-push-checks](.agents/skills/lca-pre-push-checks/SKILL.md)。

## 7. Prose 纪律

agent 写的所有 prose(JSDoc / comment / prompt / 文档 / commit message) 必须:① 用直接、具体的词,不写隐喻;② 写事实(契约、失败、时序、所有权、外部后果),不复述代码、不留 review 答辩痕迹;③ 当前态 + 短链,不长篇 history;④ 双语按 [docs/i18n/contract](docs/i18n/README.md);⑤ slop 词汇(`previously / used to / now / no longer / 退役 / 曾经 / 合并心态`)由 `scripts/verify_doc_slop.py` 机械抓,详见 [.agents/skills/lca-prose-standard](.agents/skills/lca-prose-standard/SKILL.md) + [.agents/skills/lca-trim-cot-leakage](.agents/skills/lca-trim-cot-leakage/SKILL.md)。

## 8. Git 与禁止事项

使用 Conventional Commits:`<type>(<scope>): <subject>`,正文说明做了什么和为什么;常用类型为 `feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`。一个提交只包含一个主题;不要使用 `--no-verify`,不要提交密钥、运行产物或环境文件;远程更新优先 `git pull --rebase`。

**禁止**:反向依赖 `application`;无 ADR 扩大闭集;绕过 Reducer 改 State;绕过 Body 执行副作用;Gateway 绑定具体认知实现;插件自行读取凭证;通过新事件词表或新 schema 绕过现有机制。**不直接改**生成的 `lobehub-ui/` 或 `vendor/`;LobeHub 改 `deploy/lobehub/patches/` 后重新应用,vendor 改动必须有明确升级或修复理由。

## 9. 如何改本文件

**只装 standing rule**:工程思维、约束、命令指针、禁区。**不装** walkthrough、debug 步骤、Team 策略、术语枚举 —— 那些 home 已有,留指针。

具体判定 — 内容**满足任一**才放根:

- 每次任务 agent **第 0 步必须答的** → 留(§1 总闸 4 问)
- **每次提交前必须过的** → 留(§1 卫生清单、§8 Git)
- **改了代码立即影响**的 → 留(§3 不变量、§5 Conventions)
- **agent 接任务第一查询的** → 留(§2 仓库地图、§6 命令表、§6 Before X 读 Y)
- **不在上述 4 类** → 移到 home

改前必读 §1;改后跑 `git diff --check` + `wc -l AGENTS.md`(目标 ≤ 220 行)。
