# Naming Constitution（命名宪法）

> **状态：** Proposed（待 ADR 评审）
> **取代：** 现有 [`docs/specs/naming-conventions.md`](../specs/naming-conventions.md) 升级为本文的"语义后缀附录"，原规范继续保留作为后缀术语表。
> **配套：**
> - [v3 认知原语宪法](./2026-08-19-cognitive-primitive-constitution-v3.md) — 九群归属来源
> - [包组织纪律](../specs/package-organization-discipline.md) — 规模与目录层级约束
> - [命名规范（旧）](../specs/naming-conventions.md) — 语义后缀术语表
> - [结构化认知指南](../specs/lca-structured-cognition-guide.md) — 数据所有权模型
>
> **适用范围：** `lca/`、`gateway/`、`tests/`、`scripts/`、所有 Python 源码及其测试、迁移脚本与 CI 工具。

---

## 0. 一句话

**每个名字必须能完整回答四件事：**

```text
它属于哪个 Layer（5 层单向 + 2 个装配层）
  + 它属于哪个 Concept Group（v3 九群之一）
  + 它扮演什么 Role（强制的角色后缀）
  + 它操作什么 Subject（领域名词）
```

读者从名字能 **0 上下文** 推断它的归属、职责与可替换性。命名失败 = 架构失败。

---

## 1. 第一原理：名称即压缩的架构

| 反模式 | 后果 | 正解 |
|---|---|---|
| 名字只回答"做什么"（`helpers.py`, `utils.py`, `misc.py`） | 不知道属于哪个群，读者靠猜 | 名字回答"哪个群 + 什么角色 + 什么对象" |
| 名字使用过时 jargon（`seam_definitions`, `control_contributions`） | 跨上下文含义漂移 | 名字使用九群关键词 + 角色后缀 |
| 同概念在多层各取一个近义词（`event` vs `journal_event` vs `trace_span`） | 读者需要查 ADR 才知道是否同一个东西 | 同概念在所有层使用同一组名词 |
| 类名 / 文件名 / 目录名各说各话 | 看到 `BrainStrategy` 却找不到对应文件 | 文件名 = 类名 snake_case；目录名 = 群 + 角色 |
| 缩写 / 单字 / 行业 jargon（`plane`, `face`, `text`） | 外部读者零信息 | 只保留白名单缩写，其他必须展开 |

### 1.1 命名失败的 5 种典型模式

| 模式 | 例子 | 修复 |
|---|---|---|
| 概念词不明 | `utils.py`, `common.py` | 拆解到具体的 v3 群 + 角色 |
| 缩写无字典 | `lca_computer.py` | 展开为具名（按 v3 群 + 角色） |
| 名实分离 | `state/` 目录里只有 `stop_policy.py` | 改名为 `phase_policies/stop_policy.py` |
| 群归属不明 | `composer/`、`registries/`、`factories/` 三个目录都在 plugin 下 | 强制按 v3 群命名，jargon 目录只能放"角色词" |
| 角色后缀混杂 | `JournalReducer` vs `journal_reducer_factory.py` | 文件名 = snake_case 化的类名 |

---

## 2. 架构名称空间（v3 九群）

每个名字在归属前必须能回答：**它属于哪一群？**

### 2.1 九群名称空间定义

| # | 群 | 核心职责 | 推荐名词 | 禁止词（容易混） |
|---|---|---|---|---|
| 1 | **State** | Agent 关于自身与世界的当前认知 | `state`, `snapshot`, `projection`, `context`, `status`, `phase` | ~~memory~~（属于 Memory 群） |
| 2 | **Perceive** | 把外部输入转化为可消费信号 | `perceive`, `sense`, `observe`, `manifest`, `context`, `intake` | ~~context~~ 在 State 也用时必须加前缀（如 `perceive_context`） |
| 3 | **Think** | 决策、推理、规划、反思、学习 | `brain`, `think`, `reason`, `plan`, `reflect`, `critic`, `synthesizer`, `strategy`, `hypothesis` | ~~decision~~（属于 Gate） |
| 4 | **Gate** | 守门策略与最终判定 | `gate`, `policy`, `verdict`, `judge`, `rule`, `classifier`, `classifier`, `filter` | ~~strategy~~（属于 Think） |
| 5 | **Act** | 把判定转化为外部副作用 | `act`, `execute`, `body`, `tool`, `effect`, `action`, `receipt`, `command`, `envelope` | ~~tool~~ 与 Think 的 `planner` 必须分清 |
| 6 | **Memory** | 长期存储、检索、压缩 | `memory`, `remember`, `retrieval`, `compactor`, `buffer`, `store`（仅限内存类） | ~~state~~（属于 State） |
| 7 | **Collaboration** | 多 Agent 协作 | `agent`, `team`, `delegate`, `handoff`, `coordinate`, `cast`, `lead`, `member`, `role` | ~~agent~~ 在 Runtime 是 host，在 Collaboration 是协作参与者 |
| 8 | **Journal** | 事实流、追溯、证据 | `journal`, `event`, `trace`, `evidence`, `telemetry`, `span`, `receipt`, `ledger` | ~~state~~（State 是当前投影，Journal 是事实源） |
| 9 | **Composition** | 把上面 8 群装配为可运行实例 | `profile`, `bundle`, `plugin`, `manifest`, `compose`, `boot`, `harness`, `runtime`, `loader`, `resolver`, `binder` | 其他 8 群都不应该用这些词 |

> **第 10 个隐含群 —— Cross-cutting（横切）**：观测、诊断、迁移、工具链不属于任何一群，统一加 `obs_` / `diag_` / `migrate_` / `cli_` 前缀，并标注 `[cross-cutting]` 在文件 docstring。

### 2.2 跨群命名规则

当一个名字必须跨群表达时（例如"被 Journal 记录的 Act receipt"），用 **主群 × 受影响群 × 角色** 的方式连接：

| 形式 | 含义 | 例子 |
|---|---|---|
| `<primary_group>_<role>_<subject>.py` | 主群持有实现 | `journal_projector_otel.py`（Journal 群 + projector 角色 + otel 受众） |
| `<group_a>_<group_b>_*.py` | 跨群协议 / 契约 | `journal_event_descriptor.py` |
| 形容词前缀表示群内修饰 | `cross_cutting_*.py` | `cross_cutting_observability.py` |

**禁止**：`<noun1>_<noun2>.py` 这种没有群归属、没有角色后缀的"双重名词"文件名（容易退化为 `utils.py`）。

---

## 3. 命名四维分解

每个名字都能且只能拆为以下四维：

```text
名字 = [layer_] group_[role_] subject[_qualifier][_instance]
       ─────     ───── ──── ───────  ────────── ─────────
       (可选)     必选  必选  必选     (可选)      (可选)
```

### 3.1 维度 1 — Layer（5 层 + 2 个装配层）

| 缩写 | 全称 | 目录 | 是否对外 |
|---|---|---|---|
| `c` | contracts | `lca/contracts/` | 公共 |
| `i` | infrastructure | `lca/infrastructure/` | 内部 |
| `k` | cognition | `lca/cognition/` | 内部 |
| `r` | runtime | `lca/runtime/` | 内部 |
| `a` | agent | `lca/agent/` | 内部 |
| `h` | harness | `lca/harness/` | 内部 |
| `p` | plugins | `lca/plugins/` | 公共（通过 Profile） |
| `g` | gateway | `gateway/` | 公共 |
| `app` | application | `lca/application/` | 内部 |
| `test` | tests | `tests/` | 内部 |
| `cli` | scripts | `scripts/` | 内部 |

**目录命名约束**：顶层目录只能从这 11 个之中选；新增顶层目录必须先有 ADR。

### 3.2 维度 2 — Concept Group（v3 九群）

见 §2.1。

### 3.3 维度 3 — Role（角色后缀，强制）

见 §4。

### 3.4 维度 4 — Subject（领域名词）

Subject 必须是该群内的领域对象，避免泛词。**禁止 subject**：`data`, `info`, `item`, `thing`, `object`, `entity`, `record`, `model`（最后两个允许作为 dataclass 后缀，但禁止做模块主名）。

---

## 4. 角色后缀强制词表

每个具名对象（类、Protocol、函数、变量）必须带一个明确的后缀。后缀词表如下，**新增后缀必须 ADR**：

### 4.1 类型 / 角色后缀（用于类、Protocol、文件）

| 后缀 | 含义 | 适用群 | 例子 |
|---|---|---|---|
| `Protocol` | 跨层接口契约 | 全部 | `BrainProtocol`, `MemorySystemProtocol` |
| `Adapter` | 跨边界适配器（外部 ↔ 契约） | 全部 | `OpenaiCompatAdapter`, `GenaiLLMAdapter` |
| `Factory` | 创建函数 / 工厂类 | 全部 | `BrainFactory`, `AgentLoopFactory` |
| `Builder` | 构造器（含不可变配置） | 全部 | `RunPlanBuilder`, `CommandBuilder` |
| `Registry` | 索引与发现（不创建） | 全部 | `AgentRegistry`, `ActionHandlerRegistry` |
| `Manifest` | 可审计的声明性清单 | Composition, Journal | `PluginManifest`, `AttachmentManifest` |
| `Plan` | 解析/编译后的不可变计划 | Composition, State | `CompiledRunPlan`, `ActionAuthorityPlan` |
| `Coordinator` | 跨组件生命周期协调 | 全部 | `SubagentActivationCoordinator`, `ApprovalResumeCoordinator` |
| `Composer` | 多协议实现的装配 | Composition | `BrainComposer`, `RuntimeComposer` |
| `Provider` | 给定 key 的实现 | 全部 | `GenaiLLMProvider`, `JournalSchemaProvider` |
| `Resolver` | 把 key / 字符串解析为对象 | 全部 | `ProfileResolver`, `CapabilityPlanResolver` |
| `Validator` | 校验（不修改） | 全部 | `SeamCompletenessValidator`, `PhaseGraphValidator` |
| `Mapper` | 类型 ↔ 类型转换 | 全部 | `JournalEventMapper`, `OtelGenaiMapper` |
| `Projector` | journal → UI / 视图投影 | Journal | `OtelProjector`, `ConsoleProjector`, `JsonlProjector` |
| `Reducer` | journal → state 折叠 | State, Journal | `JournalReducer`, `RunStateReducer` |
| `Driver` | 驱动循环 | Runtime | `LoopDriver`, `PhaseDriver` |
| `Handler` | 处理单个请求 | Act, Journal | `ActionHandler`, `DeltaHandler`, `CommandHandler` |
| `Executor` | 执行单个步骤 | Act | `PhaseExecutor`, `ToolExecutor` |
| `Engine` | 多子系统协作引擎 | Journal, Runtime | `JournalEngine`, `RunEngine` |
| `Scheduler` | 时间 / 资源调度 | Runtime | `TaskScheduler`, `ResumeScheduler` |
| `Router` | 路由 | Act, Collaboration | `AgentCommandRouter`, `ToolBatchRouter` |
| `Sink` | 输出端 | Journal | `JournalSink`, `TelemetrySink` |
| `Source` | 输入端 | Journal | `EventSource`, `JournalSource` |
| `Store` | 持久化 / 内存存储 | Memory, Journal, State | `EvidenceStore`, `RunStore`, `StateStore` |
| `Service` | 业务用例编排（慎用） | 跨群 | `SessionService`, `LiveCommandExecutor`（应为 Coordinator） |
| `Snapshot` | 不可变时间点副本 | State | `StateSnapshot`, `DelegationLedgerSnapshot` |
| `Context` | 可变环境（注意与"上下文协议"区别） | State | `OrchestrationContext`, `RunContext` |
| `Strategy` | 行为家族选择 | Think | `HierarchicalStrategy`, `GraphStrategy` |
| `Rule` | 纯函数规则 | Gate | `StopRule`, `ReflectionRule` |

### 4.2 函数 / 变量前缀（用于函数、方法、变量）

| 前缀 | 含义 | 是否可变 | 例子 |
|---|---|---|---|
| `get_`, `fetch_`, `read_` | 查询（无副作用） | 否 | `get_run_state`, `fetch_journal_events` |
| `find_`, `lookup_`, `resolve_` | 查找（可能跨索引） | 否 | `find_capability`, `resolve_profile` |
| `compute_`, `evaluate_`, `calculate_` | 计算（纯函数） | 否 | `compute_budget_remaining` |
| `fold_`, `reduce_` | 折叠 journal → state | 否 | `fold_run_state` |
| `build_`, `create_`, `make_` | 构造（返回新对象） | 否 | `build_manifest_from_items` |
| `set_`, `update_`, `apply_`, `transition_` | 修改（必须经 Reducer / Coordinator） | 是 | `apply_run_delta`, `transition_run_status` |
| `emit_`, `publish_`, `record_`, `append_` | 写入 journal | 是 | `emit_journal_event`, `record_gate_decided` |
| `await_`, `wait_for_` | 等待异步 | 否 | `await_run_finished` |
| `parse_`, `from_` | 解析（反序列化） | 否 | `parse_partial_tool_args` |
| `serialize_`, `to_` | 序列化 | 否 | `to_jsonl` |
| `is_`, `has_`, `can_`, `should_` | 谓词（返回 bool） | 否 | `is_cross_cutting` |
| `validate_`, `check_`, `assert_` | 校验 | 否 | `validate_slot_iterable` |
| `recover_`, `retry_`, `restore_` | 恢复 | 是 | `recover_leaked_tool_calls` |
| `start_`, `stop_`, `pause_`, `resume_` | 生命周期 | 是 | `start_run_loop` |

### 4.3 禁止后缀 / 前缀

| 反模式 | 为什么禁止 |
|---|---|
| `Impl`, `Implementation` | 只说"怎么实现"，不说"对外什么角色"。改用 `Adapter` / `Provider` / 群名 |
| `Manager` | 太泛，几乎任何协调器都可叫 Manager。改用 `Coordinator` / `Registry` / `Driver` |
| `Engine`（滥用） | 仅在真正协调多个子系统时使用，单子系统不要叫 Engine |
| `Helper`, `Util`, `Utility`, `Common`, `Shared`, `Misc` | 无信息。改用具体群 + 角色 |
| `Base`, `Abstract` | Python 没有真正的"抽象基类"语义，统一用 Protocol |
| `Wrapper`, `Facade` | 通常意味着适配，改用 `Adapter` |
| `Service`（滥用） | 仅用于真正的业务用例编排。底层工具方法不叫 Service |
| `Info`, `Data`（作为后缀） | 信息 = 什么信息？数据 = 什么数据？必须改成具体领域名词 |
| `_v2`, `_new`, `_old` | 同名新版本必须替换旧版本，保留需 ADR |

---

## 5. 目录命名规则

### 5.1 目录名公式

| 层级 | 公式 | 例子 |
|---|---|---|
| 顶层包 | `<layer>`（固定 11 个） | `lca/contracts/`, `gateway/` |
| 一级子目录（业务包内） | `<concept_group>\|<cross_cutting_role>` | `journal/`, `composer/`, `diagnostics/` |
| 二级子目录（业务包内） | `<group>_<role>` 或 `<vendor>_<subject>` | `journal/otel/`, `providers/genai_llm/` |
| 测试桶 | `tests/{unit,contract,architecture,integration,scenario,fixtures,smoke}/` | `tests/contract/test_journal_contract.py` |

### 5.2 目录名关键词清单

**Allowed keywords**（按 v3 九群）：

| 群 | 允许的目录关键词 |
|---|---|
| State | `state`, `snapshot`, `projection`, `context` |
| Perceive | `perceive`, `sensor`, `intake`, `context`（需带 `perceive_` 前缀） |
| Think | `brain`, `think`, `reason`, `plan`, `reflect`, `critic`, `synthesizer`, `strategy` |
| Gate | `gate`, `policy`, `verdict`, `judge`, `rule`, `classifier` |
| Act | `act`, `execute`, `body`, `tool`, `effect`, `action`, `command`, `envelope` |
| Memory | `memory`, `remember`, `retrieval`, `compactor`, `buffer` |
| Collaboration | `team`, `agent`, `delegate`, `handoff`, `coordinate`, `cast`, `lead` |
| Journal | `journal`, `event`, `trace`, `evidence`, `telemetry`, `span`, `ledger` |
| Composition | `profile`, `bundle`, `plugin`, `manifest`, `compose`, `boot`, `harness`, `runtime`, `loader`, `resolver` |
| 横切 | `obs_`, `diag_`, `cli_`, `migrate_`, `tools` |

**Forbidden keywords**（禁止用作目录名主词）：

| 反模式词 | 原因 |
|---|---|
| `utils`, `helpers`, `common`, `misc`, `shared`, `support`, `lib` | 无信息 |
| `new`, `old`, `v1`, `v2`, `legacy`（除非迁移期 ADR） | 时间性后缀 |
| `stuff`, `things`, `objects` | 完全无信息 |
| `external`, `third_party`, `vendored` | vendored 必须在 `vendor/` |
| `temp`, `tmp`, `scratch` | 临时目录不能进包 |
| `sandbox`（作为主词） | 与 `lca_computer/` 中的 `sandbox` 含义重叠；明确 `runtime_plane/sandbox/` 或 `sandbox_runtime/` |
| `face`, `persona`（作为目录主词） | 应是 `personas/` 复数，子目录按角色人 |

### 5.3 顶层业务包结构模板

每个业务包的一级子目录数量 ≤ 7，按下列顺序排列（让读者按认知顺序阅读）：

```text
<layer>/
├── <group_state>/          # State / 数据模型
├── <group_perceive>/       # Perceive
├── <group_think>/          # Think
├── <group_gate>/           # Gate
├── <group_act>/            # Act
├── <group_memory>/         # Memory
├── <group_collaboration>/  # Collaboration
├── <group_journal>/        # Journal
├── composition/            # Composition 群（如果适用）
└── diagnostics/            # 横切诊断（如果适用）
```

---

## 6. 文件命名规则

### 6.1 文件名公式

| 文件类型 | 公式 | 例子 |
|---|---|---|
| 单类型 / 单概念文件 | `<subject>.py`（snake_case） | `run_state.py` 定义 `RunState` |
| 带角色后缀的文件 | `<subject>_<role>.py` | `journal_reducer.py` 定义 `JournalReducer` |
| Provider / Adapter 实现 | `<vendor>_<subject>.py` | `genai_llm.py` 定义 `GenaiLLMAdapter` |
| 测试文件 | `test_<subject>_<aspect>.py` | `test_journal_reducer_state_fold.py` |
| 模块级常量 / 枚举 | `<subject>.py` | `action_type.py` 定义 `ActionType` |
| 协议 / SPI 文件 | `<subject>_protocol.py` 或 `<subject>.py`（按群统一） | `brain_protocol.py` 或 `brain.py` |
| CLI 命令 | `<verb>_<subject>.py` | `serve_observability.py`, `migrate_journal_v1_to_v2.py` |

### 6.2 禁止文件名

| 反模式 | 为什么 |
|---|---|
| `utils.py`, `helpers.py`, `common.py`, `misc.py`, `shared.py` | 无信息 |
| `interfaces.py`, `protocols.py`, `types.py`, `models.py`（在业务实现层） | 契约层专用，业务实现层不应该再有泛化包装 |
| `__main__.py` 之外的 `index.py` | Python 包没有 index 概念 |
| `aaa.py`, `bbb.py`, `untitled.py` | 无信息 |
| `<concept>_impl.py`, `<concept>_v2.py` | 同名新版本应替换旧版本 |
| `tmp_<anything>.py`, `test.py`, `foo.py` | 临时 / 占位 / 无意义 |

### 6.3 文件名与类名一一对应

**强制规则**（CI 校验）：

- 文件 `foo_bar.py` 必须定义（且只定义）`FooBar` 类或协议，且 export。
- 例外：模块级常量文件（如 `enums.py`）和 Protocol 集合文件（如 `seam_definitions/memory.py` 集中定义 `MemoryProtocol` 及其 factory）。

### 6.4 `__init__.py` 命名

`__init__.py` 必须满足：

- **禁止** 使用 `__all__ = list(globals())` 自动 barrel。
- **必须** 使用显式 `__all__ = ["Symbol1", "Symbol2"]`。
- 显式 barrel 文件本身也是命名的一部分：必须在 docstring 写清"包核心概念 + 不变量 + 公共入口"。

---

## 7. 类 / 接口命名规则

### 7.1 PascalCase + 角色后缀（强制）

| 类形态 | 命名公式 | 例子 |
|---|---|---|
| 数据类（dataclass） | `<Subject>` 或 `<Subject>Snapshot` | `RunState`, `JournalEvent`, `AgentSnapshot` |
| 抽象协议 | `<Subject>Protocol` | `BrainProtocol`, `JournalStoreProtocol` |
| 适配器 | `<Vendor><Subject>Adapter` | `OpenaiCompatAdapter`, `GenaiLLMAdapter` |
| 工厂 | `<Subject>Factory` 或 `<Subject>Builder` | `BrainFactory`, `RunPlanBuilder` |
| 注册表 | `<Subject>Registry` | `AgentRegistry`, `ActionHandlerRegistry` |
| 协调器 | `<Subject>Coordinator` | `SubagentActivationCoordinator` |
| 装配器 | `<Subject>Composer` | `BrainComposer`, `RuntimeComposer` |
| Provider | `<Vendor><Subject>Provider` | `GenaiLLMProvider` |
| Resolver | `<Subject>Resolver` | `ProfileResolver` |
| Validator | `<Subject>Validator` | `SeamCompletenessValidator` |
| Mapper | `<From>To<To>Mapper` 或 `<Subject>Mapper` | `JournalEventMapper`, `OtelGenaiMapper` |
| Projector | `<Subject>Projector` | `OtelProjector`, `ConsoleProjector` |
| Reducer | `<Subject>Reducer` 或 `<Subject>StateReducer` | `JournalReducer`, `RunStateReducer` |
| Strategy | `<Subject>Strategy` | `HierarchicalStrategy`, `GraphStrategy` |
| Snapshot | `<Subject>Snapshot` | `StateSnapshot`, `DelegationLedgerSnapshot` |
| Context | `<Subject>Context` | `OrchestrationContext`, `RunContext` |
| Exception | `<Subject>Error` 或 `<Reason>Error` | `RunStoreClosedError`, `UnregisteredJournalEventError` |

### 7.2 命名风格统一

| 维度 | 规则 |
|---|---|
| 大小写 | PascalCase，无下划线分隔单词（专有名词如 `LLM`、`JSONL`、`OTel`、`A2A`、`MCP` 保留大写） |
| 缩写 | 同 §3.4 白名单；其他展开 |
| 复数 | 类名永远单数；集合变量才用复数 |
| 前缀 | 不要 `My`、`Abstract`、`Base`、`Concrete` 前缀（Python 用 Protocol + 鸭子类型） |
| 后缀 | 必须带角色后缀；无角色 = 数据类（不强制后缀） |

### 7.3 协议（Protocol）命名

- **必须以 `Protocol` 结尾**。
- 同概念的 Protocol 与 Reference 实现放不同文件：Protocol 在 `contracts/`，Reference 在 `infrastructure/` 或 `plugins/`。
- 例子：`BrainProtocol`（contract）、`BrainComposer`（composer in plugins）。

### 7.4 异常（Exception）命名

- 必须以 `Error` 结尾。
- 命名公式：`<What>Error` 或 `<Reason>Error`。
- 避免模糊命名 `Exception`、`BaseException`、`RuntimeError`（保留给标准库语义）。

---

## 8. 函数 / 方法命名规则

### 8.1 snake_case + 动词前缀（强制）

| 行为类别 | 前缀 | 是否可变 | 例子 |
|---|---|---|---|
| 查询 | `get_`, `fetch_`, `read_`, `find_`, `lookup_`, `resolve_` | 否 | `get_run_state`, `find_capability` |
| 计算 | `compute_`, `evaluate_`, `calculate_`, `fold_`, `reduce_` | 否 | `compute_budget_remaining`, `fold_run_state` |
| 构造 | `build_`, `create_`, `make_`, `compose_` | 否（返回新对象） | `build_manifest_from_items` |
| 写入 | `set_`, `update_`, `apply_`, `transition_`, `mutate_` | 是（必须经 Reducer / Coordinator） | `apply_run_delta`, `transition_run_status` |
| 记录 | `emit_`, `publish_`, `record_`, `append_`, `commit_` | 是（写 journal） | `emit_journal_event`, `record_gate_decided` |
| 异步等待 | `await_`, `wait_for_` | 否 | `await_run_finished` |
| 解析 / 序列化 | `parse_`, `from_`, `serialize_`, `to_` | 否 | `parse_partial_tool_args` |
| 谓词 | `is_`, `has_`, `can_`, `should_`, `must_` | 否 | `is_cross_cutting` |
| 校验 | `validate_`, `check_`, `assert_` | 否 | `validate_slot_iterable` |
| 恢复 | `recover_`, `retry_`, `restore_` | 是 | `recover_leaked_tool_calls` |
| 生命周期 | `start_`, `stop_`, `pause_`, `resume_`, `cancel_` | 是 | `start_run_loop`, `resume_run` |

### 8.2 函数命名禁忌

| 反模式 | 为什么禁止 |
|---|---|
| `do_thing()`, `handle_thing()`, `process_thing()` | 动词太泛。改为 `parse_thing` / `validate_thing` / `transform_thing` |
| `foo()`, `bar()` | 占位 / 临时 |
| `magic()`, `__magic__()`（除非真的是 dunder） | magic method 仅限 Python 协议定义 |
| 名词开头的函数（`event_loop`, `journal_run`） | 不是动词，读者无法判断何时调用 |

---

## 9. 变量 / 常量 / 枚举命名规则

### 9.1 变量（snake_case）

| 变量形态 | 公式 | 例子 |
|---|---|---|
| 局部变量 | snake_case 名词短语 | `run_state`, `journal_event`, `decision_verdict` |
| 布尔 | `is_`, `has_`, `can_`, `should_` 前缀 | `is_active`, `has_grant`, `can_recover` |
| 集合 | 复数名词 | `events`, `capabilities`, `tool_batches` |
| 字典 | `<key>_<by>_<value>` 命名 | `events_by_session`, `capabilities_by_phase` |
| 计数器 | `<noun>_count` | `event_count`, `retry_count` |
| 私有 / 模块内部 | `_` 前缀 | `_internal_cache`, `_parse_helper` |

### 9.2 常量（UPPER_SNAKE_CASE）

| 常量形态 | 公式 | 例子 |
|---|---|---|
| 模块级配置 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| 错误码 | `<DOMAIN>_<NUMBER>` | `JOURNAL_001`, `PROFILE_002` |
| 协议键 | `SEAM_<CAPABILITY>` | `SEAM_LLM`, `SEAM_MEMORY` |
| 事件名 | `<EVENT>`（全大写动词） | `RUN_STARTED`, `GATE_DECIDED` |

### 9.3 枚举（Enum）

**强制使用 `str, Enum` 子类**，值与字面量字符串一致（兼容序列化）。

| 枚举类型 | 命名公式 | 例子 |
|---|---|---|
| 动作 / 行为 | `<Subject>Action` / `<Subject>Type` | `ActionType.RESPOND`, `HookEvent.PRE_PERCEIVE` |
| 阶段 / 状态 | `<Subject>Phase` / `<Subject>Status` | `RunActivityPhase.LLM_THINKING`, `RunStatus.RUNNING` |
| 角色 / 范围 | `<Subject>Scope` / `<Subject>Role` | `ActionScope.LEAD`, `ActionScope.MEMBER` |
| 错误码 | `<Subject>Code` | `ErrorCode.JOURNAL_UNREGISTERED` |

**枚举值命名**：UPPER_SNAKE_CASE，**保留语义**：

- `RESPOND` vs `respond` —— **永远大写作为属性名**，值的字符串与属性名相同。
- 跨群引用：在值前面加群前缀避免歧义：`JOURNAL_EVENT_TYPE_X` 而非 `EVENT_TYPE_X`。

### 9.4 字符串字面量（Domain String）

裸字符串仅允许在以下场景：

- 日志消息、用户错误提示文案（i18n 边界）。
- 测试断言。

其余必须经枚举或常量引用。**禁止** 在代码中使用裸字符串作为事件名、阶段名、动作名（已有 `check_no_bare_strings.py`）。

---

## 10. 既有名称重新映射表（精选）

> 完整列表见后续 ADR / migrate 脚本。下面是 **必须改动** 的顶层命名。

### 10.1 目录重命名（按 v3 群 + 角色重映射）

| 现路径 | 现名 | 建议路径 | 理由 |
|---|---|---|---|
| `lca/infrastructure/plane/` | 名实冲突 | `lca/infrastructure/runtime_plane/` | 避免与"双平面"含义冲突；明确"执行环境类型" |
| `lca/infrastructure/plane/` | 名实冲突 | `lca/infrastructure/runtime_plane/` | 避免与"双平面"含义冲突；明确"执行环境类型" |
| `lca/infrastructure/text/` | 名实不符 | 删除或迁到 `lca/infrastructure/observability/narrative/text_utils.py` | 目录名与内容不符 |
| `lca/infrastructure/ops/` | 含义重叠 | `lca/infrastructure/cli/` | 与 `gateway/`、`scripts/` 的 ops 概念分离 |
| `lca/infrastructure/observability/cost/` | 损坏包 | `lca/infrastructure/observability/journal/cost/` | 属于 Journal 投影面 |
| `lca/plugins/creator/` | 空 README | `lca/plugins/composer/personas/`（代码迁出） | creator 是 composition 角色 |
| `lca/plugins/creator/faces/` | jargon | `lca/plugins/composer/personas/` | `face` → `personas` 复数 |
| `lca/plugins/team_lead/` | 空包 | 删除 | 合并到 `lca/plugins/strategies/hierarchical.py` |
| `lca/plugins/registries/` | 1 文件 + README | 删除；文件迁 `lca/plugins/seams/` 或 `lca/harness/registries.py` | ADR-0062 占位 |
| `lca/plugins/state/` | 名实不符 | 合并到 `lca/plugins/phase_policies/stop_policy.py` | 目录里只有 stop policy |
| `lca/plugins/graph_nodes/` + 4 个 `phase_*` | 同切同概念 | 合并为 `lca/plugins/phase_graph/`（按节点 / 边 / 执行器 / 策略 / 拓扑分子目录） | 5 目录承担同概念 |
| `lca/plugins/compose/` | 与 `composer/` 1 字母差 | 改 `lca/plugins/factories/` | 命名差异显式化 |
| `lca/plugins/composer/` | 21 文件 | `lca/plugins/composer/{brain,body,perceive,runtime,team,fixtures}/` | 按群拆 |
| `lca/plugins/control_contributions/` | 13 个认知动词前缀文件 | `lca/plugins/cognitive_steps/{perceive,think,gate,act,reflect,remember,stop,failure_stop,capabilities,common}.py` | 目录名显式化 |
| `lca/plugins/seam_definitions/` | jargon + 55 文件 | `lca/plugins/seams/`（按群分子目录） | 去掉 `_definitions`；改短名 |
| `lca/plugins/phase_executors/` | 已对齐 v3 群 | 保持；细分按认知动词（已部分对齐） | OK |
| `lca/plugins/critic/`、`synthesizer/`、`reasoner/`、`brain/`、`perceive/` | 良好 | 保持 | OK |
| `lca/plugins/memory/` | 损坏包（无 `__init__.py`） | `lca/cognition/memory/`（迁到 cognition 层） | 恢复 `__init__.py` 或迁出 |
| `lca/plugins/learning/` | 良好 | 保持 | OK |
| `lca/plugins/insight/` | 含义不明 | `lca/plugins/diagnostics/insight_report.py`（合并到 diagnostics） | "insight" 在 cognition 是 reflect 输出 |
| `lca/harness/sdk/` | 空包 | 删除 | ADR 占位未实现 |
| `lca/runtime/completion/`、`outcome_policies/` | README-only | 删除 | ADR 占位未实现 |
| `lca/packages/identity/anonymous_user_id/` | 完全空 | 删除 | 死代码 |
| `lca/packages/runtime_diagnostics/invariants/src/` | 完全空 | 删除 | 死代码 |
| `lca/infrastructure/observability/exporters/` | 0 文件 + 已声明迁移 | 删除 | ADR-0055 迁移完成 |
| `lca/infrastructure/observability/narrative/` | 4 文件 + 大部分已迁 | 评估保留理由或合并到 `journal/stream/narrative_sidecar.py` | 文档已说"仅存 span 诊断" |
| `gateway/runs/` | 57 平铺 | `gateway/runs/{api,lifecycle,session,ingest,execute,terminal,doctor,wire,observability}/` | 按职责切 |

### 10.2 文件 / 类重命名（精选）

| 现名 | 问题 | 建议名 |
|---|---|---|
| `lca/contracts/protocols/__init__.py`（314 行自动 barrel） | 自动 barrel | 拆 `__init__.py` 到 `__init__.py`（每个子包）+ `declarative/` 子包 |
| `lca/infrastructure/llm_adapter/`、`llm/` | 同义重叠 | `lca/infrastructure/llm/` 保留底层；`llm_adapter/` 改名为 `lca/infrastructure/llm/adapters/` 或迁到 `lca/plugins/providers/llm/` |
| `lca/infrastructure/sandbox/` 与 `lca/infrastructure/tools/lca_sandbox/` | 含义重叠 | 改名 `lca_sandbox` → `computer_sandbox`（明确是 `computer` 子系统的 sandbox 实现） |
| `lca/infrastructure/tools/lca_computer/` | "computer" 名实不符（实为 LobeHub API 适配） | `lca/infrastructure/computer_apis/` 或迁到 `lca/plugins/providers/computer/` |
| `lca/infrastructure/observability/coding_agent_tools/` | 应迁出 observability | `lca/plugins/tools/diagnostics/`（既然是诊断工具） |
| `lca/cognition/brain/decision_gates/`（9 文件）vs `lca/plugins/gates/`（9 文件） | 两层重复 | 区分：`brain/decision_gates/` 是 Brain 的 Gate 内部实现；`plugins/gates/` 是 Gate 协议插件；前者迁到 `lca/cognition/brain/gates/` |
| `JournalProjector` 文件名 vs `journal_projector.py` 文件名（多实现时） | 一个文件只能有一个主类 | `journal/projectors/otel.py` 定义 `OtelProjector`（不再带 Journal 前缀） |

### 10.3 既有良好命名（保留作为模板）

下面这些命名已对齐宪法，应作为后续命名的参考：

| 类型 | 例子 | 为什么好 |
|---|---|---|
| 协议 | `BrainProtocol`, `MemorySystemProtocol`, `JournalStoreProtocol` | 统一 `Protocol` 后缀 |
| 协调器 | `SubagentActivationCoordinator`, `ApprovalResumeCoordinator` | 显式角色 |
| Projector | `OtelProjector`, `ConsoleProjector`, `JsonlProjector` | Vendor 前缀 + Projector 后缀 |
| Reducer | `JournalReducer`, `RunStateReducer` | 群 + Subject + 角色 |
| Factory | `BrainFactory`, `AgentLoopFactory` | Subject + Factory |
| Registry | `AgentRegistry`, `ActionHandlerRegistry` | Subject + Registry |
| Composer | `BrainComposer`, `RuntimeComposer` | Subject + Composer |
| Coordinator | `AgentCommandRouter`（应是 Router 而非 Coordinator） | 部分已是好模式 |
| Manifest | `PluginManifest`, `AttachmentManifest` | Subject + Manifest |
| Plan | `CompiledRunPlan`, `ActionAuthorityPlan` | Subject + Plan |
| Snapshot | `StateSnapshot`, `DelegationLedgerSnapshot` | Subject + Snapshot |
| Validator | `SeamCompletenessValidator`, `PhaseGraphValidator` | Subject + Validator |
| Mapper | `JournalEventMapper`, `OtelGenaiMapper` | Subject + Mapper |
| 函数 | `build_manifest_from_items`, `record_gate_decided`, `recover_leaked_tool_calls`, `apply_run_delta`, `emit_journal_event` | 动词前缀 + Subject + 角色 |
| 谓词 | `is_cross_cutting`, `validate_slot_iterable` | `is_` / `validate_` 前缀 |
| 枚举类 | `ActionType`, `HookEvent`, `RunActivityPhase`, `ActionScope` | 统一 `<Subject>Type/Event/Phase/Scope` 模式 |
| 枚举值 | `RESPOND`, `USE_TOOL`, `PRE_PERCEIVE`, `LLM_THINKING`, `TOOL_RUNNING`, `SANDBOX_EXEC` | 大写动词 / 名词短语 |
| 常量 | `SLOT_PHASE_OWNER`, `V3_TO_0069_MAPPING`, `RELATION_GROUP_HINT` | 全大写 + 语义后缀 |

---

## 11. 新增命名流程（PR 自检模板）

提交 PR 前，对照下面 6 项：

```text
[ ] 1. 这个名字属于 v3 九群中的哪一群？
        答：____________
        若是横切，标注 [cross-cutting] 并说明为何不属于九群。

[ ] 2. 它扮演什么角色（见 §4.1 后缀表）？
        答：____________（Protocol / Adapter / Factory / ...）

[ ] 3. 它属于哪一层（5 层 + 2 装配层）？
        答：____________（contracts / infrastructure / cognition / runtime / agent / harness / plugins / gateway / application）

[ ] 4. 是否避开了 §1.1 全部反模式？
        答：☐ 避开 utils/helpers/common/misc
            ☐ 避开 Impl/Manager/Wrapper/Facade 等无信息后缀
            ☐ 避开缩写（除白名单 LLM/JSONL/OTel/SSE/A2A/MCP）

[ ] 5. 文件名是否与主类 / 主常量一一对应？
        答：☐ foo_bar.py 定义 FooBar；不混定义多个无关类型

[ ] 6. __init__.py 是否显式 __all__？
        答：☐ 是 / ☐ 否（说明为什么）
```

任何一项答"否" 或"我不知道" → 不允许合并。

---

## 12. CI 门禁（命名版）

| 检查 | 工具 | 规则 |
|---|---|---|
| 文件名 vs 类名一致 | `scripts/check_filename_class_match.py`（新增） | `foo_bar.py` 必须定义 `FooBar` |
| 禁止 `utils.py` 等 | `scripts/check_no_utility_modules.py`（已有） | 禁止新增；存量入迁移 backlog |
| 禁止 `__all__ = list(globals())` | `scripts/check_no_barrel_glob.py`（新增） | 必须显式 `__all__` |
| 禁止 `*Impl` / `*Manager` / `*Helper` 后缀 | `scripts/check_forbidden_suffix.py`（新增） | 见 §4.3 |
| 禁止裸字符串 | `scripts/check_no_bare_strings.py`（已有） | 仅枚举常量 |
| 包目录规模 | `scripts/check_package_size.py`（新增） | 8/10/15 阈值 |
| 缩写白名单 | `scripts/check_known_abbrev.py`（新增） | `LLM`/`JSONL`/`OTel`/`SSE`/`A2A`/`MCP` |
| 目录名 vs v3 群关键词 | `scripts/check_package_noun.py`（新增） | 群归属可解释 |
| 函数动词前缀 | `scripts/check_function_verb_prefix.py`（新增） | 必须有 §8.1 之一的前缀 |
| 枚举值一致性 | `scripts/check_enum_str_value.py`（新增） | `enum.Enum.value` 必须与属性名匹配 |

新增子命令：`lca-ops diagnose naming`，输出违规清单 + 修复建议。

---

## 13. 迁移路线（与 ADR-0105 包组织纪律合并执行）

> 详细 PR 顺序见 [`docs/specs/package-organization-discipline.md` §12](../specs/package-organization-discipline.md)。本文增加命名层面动作。

### Phase A（1 周）—— 零风险命名清理

- 删除空包 / 损坏包 / README-only 包（与包组织 Phase A 共用）。
- 修复 3 个 `__init__.py` 缺失。
- 改 `lca/contracts/protocols/__init__.py` 自动 barrel → 显式 `__all__`。
- 删 `lca/plugins/state/` 中的 `stop_policy.py` → 迁到 `lca/plugins/phase_policies/stop_policy.py`。
- 删 `lca/plugins/registries/` 中的 `factory_seams.py` → 迁到 `lca/plugins/seams/`。

### Phase B（3 周）—— 超大目录拆分 + 命名统一

- 拆分 8 个超大目录（每个 1 PR，自带 import 映射表 + 迁移脚本）。
- 同步重命名：拆出的子目录按 §10.1 / §10.2 映射表执行。
- 在每个 PR 中检查类名 / 文件名一致性。

### Phase C（2 周）—— 命名规范化收敛

- `plane/` → `runtime_plane/`
- `creator/faces/` → `composer/personas/`
- 5 个 `phase_*` + `graph_nodes/` → `phase_graph/`
- `compose/` → `factories/`
- `ops/` → `cli/`
- `lca_sandbox/` → `computer_sandbox/`
- `lca_computer/` → `computer_apis/`
- `coding_agent_tools/` → `plugins/tools/diagnostics/`

### Phase D（1 周）—— CI 门禁落地

- 实现 §12 全部 10 个 `scripts/check_*.py`。
- 接入 `lca-ops diagnose naming`。
- 在 CI 主流程加 `naming` job（合并前置）。

### Phase E（持续）—— 长尾收尾

- 扫描所有 `*Impl` / `*Manager` / `*Helper` / `*Wrapper`，逐个改名。
- 扫描所有 snake_case 文件名 vs 类名不一致，逐个对齐。
- 在 ADR 中归档所有"豁免"和"过渡态"。

---

## 14. 附录 A：快速决策表（贴墙可用）

### A.1 "我要新建一个目录，它应该叫什么？"

```text
Q1. 它属于 v3 九群哪一群？
    → 群关键词 + 角色 = 目录名（例：journal + projector = journal/projectors/）

Q2. 它跨多群？
    → 用受影响群 + 主群前缀（例：journal_event_descriptor）
    → 或归到 composition / 横切

Q3. 它是 vendor 实现？
    → vendor 名称 + subject（例：providers/genai_llm/、observability/otel/）
```

### A.2 "我要新建一个类，它应该叫什么？"

```text
Q1. 它是什么角色？
    - 跨层接口      → <Subject>Protocol
    - 数据快照      → <Subject>Snapshot
    - 适配外部      → <Vendor><Subject>Adapter
    - 创建          → <Subject>Factory / <Subject>Builder
    - 索引          → <Subject>Registry
    - 协调多组件    → <Subject>Coordinator
    - 装配多协议    → <Subject>Composer
    - 投影 journal  → <Subject>Projector
    - 折叠 state    → <Subject>Reducer
    - 校验          → <Subject>Validator
    - 路由          → <Subject>Router
    - 调度          → <Subject>Scheduler
    - 驱动循环      → <Subject>Driver
    - 处理单事件    → <Subject>Handler
    - 执行单步      → <Subject>Executor
    - 异常          → <Subject>Error / <Reason>Error
    - 纯数据        → <Subject>

Q2. 它跨群？
    → 用主群前缀（例：JournalReducer 而非 Reducer）
```

### A.3 "我要新建一个函数，它应该叫什么？"

```text
Q1. 它有副作用吗？
    无 → get_/fetch_/find_/compute_/build_/parse_/validate_/is_
    有 → set_/apply_/emit_/record_/transition_/recover_/start_/stop_

Q2. 它操作什么对象？
    → 用该群的领域名词（例：journal_event、run_state、gate_verdict）

Q3. 拼起来
    → 动词前缀 + subject + 必要角色后缀
    → 例：emit_journal_event()、fold_run_state()、apply_run_delta()
```

### A.4 "我要新建一个变量 / 常量 / 枚举值，它应该叫什么？"

```text
变量    → snake_case 名词（复数表示集合；is_/has_ 前缀表示 bool）
常量    → UPPER_SNAKE_CASE（带域前缀避免冲突：JOURNAL_001）
枚举类  → <Subject>Type / <Subject>Phase / <Subject>Scope / <Subject>Event
枚举值  → UPPER_SNAKE_CASE，跨群引用加群前缀
```

---

## 15. 附录 B：与其他规范文档的索引

| 主题 | 文档 |
|---|---|
| 命名后缀（旧） | `docs/specs/naming-conventions.md`（本文为超集） |
| 包目录规模 | `docs/specs/package-organization-discipline.md` |
| 认知原语宪法 | `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` |
| 声明式阶段图 | `docs/specs/declarative-phase-graph-spec.md` |
| 运行时骨架 | `docs/specs/harness-spine-spec.md` |
| 结构化认知指南 | `docs/specs/lca-structured-cognition-guide.md` |
| 数据所有权 | `docs/specs/lca-structured-cognition-guide.md` §4 |
| ADR 索引 | `docs/adr/` |
| 术语表 | `docs/specs/glossary.md` |

---

## 16. 附录 C：宪法演进规则

本宪法修改需满足：

1. 修改必须新增 ADR，标注 "Supersedes Naming Constitution §X.Y" 或 "Amendment to Naming Constitution §X.Y"。
2. 不允许"静默修改"——任何新增角色后缀 / 新增群 / 修改禁止词清单都必须经过 ADR 评审。
3. 本宪法与 v3 认知原语宪法冲突时，以 v3 为准；本宪法是 v3 在命名层的细化。
4. 本宪法与 harness-spine-spec 冲突时，以本文为准（命名优先于实现细节）。
