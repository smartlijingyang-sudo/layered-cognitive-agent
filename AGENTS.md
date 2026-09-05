# LCA Coding Agent Contract

LCA 是基于 vendored Cordis 的 Python 插件化认知 Agent 框架。

## 0. 权威入口

| 关注点 | 入口 |
|---|---|
| 文档导航与归属 | [docs/specs/documentation-map.md](docs/specs/documentation-map.md) |
| 文档写作规则 | [docs/AGENTS.md](docs/AGENTS.md) |
| 架构检查脚本 | [docs/architecture/checks.md](docs/architecture/checks.md) |
| 观测架构 | [docs/observability/architecture-overview.md](docs/observability/architecture-overview.md) |
| 结构化认知模型 | [docs/specs/lca-structured-cognition-guide.md](docs/specs/lca-structured-cognition-guide.md) |
| Agent Notes 决策 | [docs/notes/README.md](docs/notes/README.md) |
| ADR 索引 | [docs/adr/README.md](docs/adr/README.md) |
| 调试 runbook | [docs/debug/README.md](docs/debug/README.md) |

**迁移态 disclaimer:** Journal / EventSpine / Session 的 SSOT 关系正在迁移中(ADR-0186 Proposed)。in-process 真值走 `Session.append`;durable SSOT 为 `<run_id>.spine.jsonl`;fold 纯函数派生 projection。兼容入口和删除条件跟踪于 ADR-0186 §5。

## 1. 接任务前 7 问(必答,不答不写)

1. **问题是什么?** 用业务/系统行为描述,不含实现名词。
2. **受影响的事实或契约是什么?** 指出 Protocol、事件、Schema、能力、Profile 或副作用。
3. **唯一真值在哪里?** 谁拥有事实,谁只是 projection。
4. **改变哪个边界?** 层、seam、控制面/观察面、进程或外部系统。
5. **现有 Protocol / ADR / Note 能否表达?** 能则扩展,勿新开平行机制。
6. **失败、重试、恢复和幂等语义是什么?** 覆盖成功、拒绝、部分完成和重复调用。
7. **如何验证、何时删除兼容?** 给出实际命令、测试和 delete-when 条件。

| 情况 | 动作 |
|---|---|
| 1–4,不改变契约 | 直接改代码,补测试,跑局部门禁 |
| 改变已有契约,ADR/Protocol 可表达 | 先改契约,同变更闭环实现、消费者、测试和文档 |
| 改变闭集/层边界/SSOT/能力模型 | 停止编码,先提交 ADR/Note 草案 |

**优先(递减):** 不变量与契约正确 → 依赖方向与单一职责 → 可观测真值 → 可删的兼容 → 局部性能 → "少改几行"的幻觉。

## 2. 架构模型

### 2.1 领域依赖层(单向)

```text
contracts → infrastructure → cognition → runtime → agent
```

`application` 是组合根,装配具体实现;下层不得反向 import。`harness` 只依赖 `contracts`,承载 Session/Profile/Boot/声明式阶段。`plugins` 是 Seam/Provider/Loop Driver 实现。`lca_kernel` 是顶层 host 包,下层禁止 import 其内部。transport plugin 独立于认知/运行/Agent。分层由 `lint-imports` 和 `pyproject.toml` 契约检查。

### 2.2 事实/状态/决策/许可/回执/投影

**先分类,再修改。** 任何新字段、对象、事件或副作用,先判断属于哪一类,再决定写入边界。

| 类别 | 代表 | 拥有者 | 写入边界 |
|---|---|---|---|
| 事实 | Journal / Session log / Event | Session | 唯一生产入口(`Session.append`),仅追加 |
| 状态 | `AgentState` | Reducer / 指定 projection | 业务组件不得直接写;按新值替换 |
| 决策 | `Decision` | cognition | 认知阶段产生;候选意图,非已授权 |
| 许可 | `Verdict` | Gate/Policy/Approval | 授权控制面产生 |
| 回执 | Effect Receipt | Body/执行边界 | 副作用执行器产生;追加/不可变 |
| 投影 | Projection / Trace / Metrics | fold/deriver/view | 可缓存可重建;不得反向写事实 |

**核心判定:** 任何对象不能同时承担事实源和投影职责。

### 2.3 控制面与观察面

```
控制面: Command / Approval / Policy / CapabilityGrant → 改变系统行为
观察面: Session / Journal / Trace / Metrics / Projection → 记录或派生
```

- 观察面不得触发控制面副作用。控制面必须留下可追溯事实。
- 诊断命令默认只读;禁止"为展示状态而顺便修复/重启/补写事件"。

## 3. 不变量

| ID | 不变量 | 要求 |
|---|---|---|
| C1 | 认知闭集 | 改变循环或核心事件语义必须先有 ADR,默认否决 |
| C2 | 双平面 | 认知不直接写世界;执行不私自改变认知状态 |
| C3 | 事实可追溯 | 输入、工具调用、协作报告和关键变化可追溯;复用现有事件目录 |
| C4 | Reducer 单写 | 业务路径不直接写 State;projection 不得成为新事实源 |
| C5 | 能力单调(三维) | capability/scope/effects 三维都必须 ⊆ 调用者 grant;`CommandEnvelope` 是副作用唯一出口(frozen,不可绕过);违反抛 `CapabilityGrantExceededError` |
| C6 | 最小化 | 原语默认 no-op;优先组合已有原语 |
| C7 | 控制/观察分离 | 见 §2.3 |
| C8 | 确定性 | Profile resolve、fold、projection 必须确定;时间/随机/PID/env 通过 seam 注入 |
| C9 | 幂等/重入 | 启动、恢复、append、observer、teardown 必须定义幂等边界;禁止靠"通常没事" |
| C10 | 执行窄门 | cognition → Body → SafeExecutor → Sandbox 是唯一副作用路径;tool 错误分确定性(不重试)/瞬时(可重试)两类 |
| C11 | 事件闭集 | `EXECUTION_POINTS` 是白名单;新事件必须同时加入白名单 + 注册 SpineHandler + 有测试 + ADR;双事件系统迁移中新事件只走 `Session.append` |
| C12 | Reducer 合约 | `apply_*` 必须 `@_instrument_apply` 装饰;`apply_stop` 先于 `apply_terminal_outcome`;新方法同步更新 `AgentStateProjection` fold |

**闭集:** `perceive → think → gate → act → reflect → remember → stop`。插件可替换实现,不能无 ADR 增加步骤或核心事件词表。

**扩展路径:** `Protocol → Seam → Provider / Adapter → Registry → Plugin → Profile / Bundle`。密钥只能经 Profile `{from_env: ...}` 进入;插件不得自行读取 `os.environ`。

**错误分类:** 认知层错误产生 Decision(rejected);Gate 错误产生 Verdict(rejected);Body 错误产生 Effect Receipt(error)。确定性错误(ValueError/TypeError 等)不重试;瞬时错误(Timeout/Connection)指数退避。Observer 失败 contained,不回滚已 commit 的 append。

## 4. 禁止事项与迁移态

**禁止:**
- 反向依赖 `application`;绕过 Reducer 改 State;绕过 Body 执行副作用
- 业务路径直接写 Journal/Spine/Session 后端;只能调唯一公共生产入口
- 把 projection/trace/metrics/view 当事实源
- `contracts` 引入实现层、I/O、日志、环境读取或第三方依赖
- 用动态 import、全局注册、反射字符串或 context 属性绕过 import 边界
- 用异常吞没、空 catch、隐式 fallback 或默认放行掩盖契约缺失
- 新增平行事件词表、平行 schema、平行 plugin manifest 或第二套 Profile 解析
- 在诊断/观测路径执行修复性副作用(除非命令名和测试明确表达)
- 插件自行读取凭证;Gateway 绑定具体认知实现
- 不直接改 `lobehub-ui/` 或 `vendor/`
- Plugin setup() 只能调 Manifest 声明的 provide/require/register/emit;未声明调用触发 `UndeclaredInteractionError`
- Plugin 间禁止直接 import;只通过 capability key 交互
- 业务代码禁止直接 import journal backends 或 spine derivers(由 import-linter business-event-isolation 守护)
- Session recovery 禁止 checkpoint `working` 状态;`waiting_input` 必须恰好有一个未解决 approval
- env 三层白名单:`BOOTSTRAP_NAMES`(覆盖已有)/`BOOTSTRAP_PREFIXES`(新增)/`BOOTSTRAP_FORBIDDEN`(禁止);`LCA_PROFILE` 必须来自 argv

**迁移态模板(必须填满,无 delete-when = 红灯):**

```text
# COMPAT(owner: ADR-0xxx, from: <旧入口>, to: <新入口>,
#         delete_when: <可观察条件>, forbidden_new_usage: <禁止新增用法>)
```

新代码默认用 `to`。同一变更不能既新增旧用法又声称收敛迁移。删除条件必须包含检测命令或测试。

## 5. 变更闭环

**契约改动必须闭环(漏一端 = 未完成,不是 follow-up):**

| 改了 | 必须同 PR 改 |
|---|---|
| Protocol / 公共签名 | 全部实现 + 测试 + 必要时 mypy |
| 枚举 / close-set / EP 名 | whitelist、catalog、emit 方、消费方、文档 |
| Schema / Journal 字段 | consumer + migration 说明 + 测试 |
| 注册表 key / Plugin id | Profile/Bundle、`why-plugin`、装配测试 |

**默认要求:** 新公共接口先写 Protocol/DTO;新副作用先写 capability/effects;新状态转移先定义合法/拒绝/恢复状态;每个 bugfix 至少一个回归测试;每个兼容分支必须有 owner 和 delete-when。

**离开前卫生:** 无新增无期限 TODO;无双写同一 SSOT(除非 COMPAT 写满);死代码/死 import 已清;类型标注完整;`ruff check --fix`;`git diff --check`;提交信息说明"做了什么 / 为什么"。

**Plugin 硬约束:** 每个 plugin 一个 `.py` 文件;`@plugin(...)` 为唯一入口;`effects` 必声明;setup() 只能调 Manifest 声明的 provide/require/register/emit(未声明触发 `UndeclaredInteractionError`);Plugin 间禁止直接 import;`bundles/*.yaml:plugins:` 列短 id 不引路径;校验 `./scripts/lca-ops audit-plugin-shape`。

## 6. 验证矩阵

| 变更类型 | 最低验证 | 必须追加 |
|---|---|---|
| 普通实现,单 seam | `ruff check` + `ruff format` + 相关 pytest | 回归测试 |
| Protocol/公共签名 | 上述 | 全部实现 + 消费者 + mypy + 契约测试 |
| contracts/枚举/事件 | 上述 | catalog/whitelist + 序列化兼容 + 重放测试 |
| Profile/Plugin/Bundle | plugin shape + resolve 测试 | DAG + 能力归属 + effects 审计 |
| 分层/import/组合根 | `lint-imports` + package contracts | 依赖方向 + 禁止绕过扫描 |
| Journal/Session/Projection | fold + 持久化 + 恢复测试 | SSOT + 幂等 + flush 隔离 |
| 并发/生命周期 | 单元 + 集成 | 重入 + 取消 + teardown + 资源释放 |

**基线失败协议:** `lint-imports` 和 `check_package_contracts.py` 当前存在既有失败。提交报告必须区分**本次引入** vs **既有失败**;禁止用"全量通过"描述未通过的门禁;只有退出码为 0 的命令才能写为"通过"。完整推送前检查 [.agents/skills/lca-pre-push-checks](.agents/skills/lca-pre-push-checks/SKILL.md)。`real_llm` 默认不运行。

## 7. 最小命令入口

`./scripts/lca-ops` 不带参数打印分层手册;`./scripts/lca-ops <cmd> --help` 看子命令。

| 场景 | 命令 |
|---|---|
| 服务状态 / 重启 / 触发 run | `status --json` / `kernel-restart` / `runs create --user-text "..."` |
| run 失败 / E2E 冒烟 | `debug-run <run_id>` / `e2e timeline` |
| notes 体检 / ADR 审计 | `notes-check` / `notes-audit` |
| 审计 Reducer 单写 / 能力归属 | `audit-state-writers` / `why <capability>` |

**Before X,读 Y:** 调试 → [docs/debug/README.md](docs/debug/README.md);Journal/Trace → [docs/specs/harness-spine-spec.md](docs/specs/harness-spine-spec.md);散文 → [.agents/skills/lca-prose-standard](.agents/skills/lca-prose-standard/SKILL.md);新 Note → [.agents/skills/lca-write-note](.agents/skills/lca-write-note/SKILL.md);CI 测试可靠性 → [.agents/skills/lca-ci-test-reliability](.agents/skills/lca-ci-test-reliability/SKILL.md)。

## 8. Git 与文档卫生

Conventional Commits:`<type>(<scope>): <subject>`,正文说"做了什么 / 为什么"。一个提交一个主题;不用 `--no-verify`;不提交密钥或运行产物;远程 `git pull --rebase`。

Prose:直接具体,不复述代码,不留 review 答辩痕迹;slop 由 `scripts/verify_doc_slop.py` 检查。详见 [.agents/skills/lca-prose-standard](.agents/skills/lca-prose-standard/SKILL.md) + [.agents/skills/lca-trim-cot-leakage](.agents/skills/lca-trim-cot-leakage/SKILL.md)。

**改本文件:** 只装 standing rule — 决策闸门、当前不变量、禁止事项、变更闭环、验证矩阵、权威入口。满足任一才放根:① 每次任务第 0 步必答;② 每次提交前必过;③ 改了代码立即影响;④ agent 接任务第一查询。改后跑 `git diff --check` + `wc -l AGENTS.md`(目标 ≤ 220 行)。
