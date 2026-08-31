# ADR-0110：插件合约统一化与命名收敛 —— 折叠 LogicAddress，让 PluginContract 真正成为插件侧唯一合约

## 状态

**Partially Accepted — 2026-08-31**

> PR-A / B / F / G / H 已落地（branch `back-ui-821-other-keep`, commits
> `5727ef5a` & `885bdd43`）；剩余 PR-C / D / E / I 见 §六。本 ADR 在 PR-C
> 落地后改 Accepted。

Refines:
- ADR-0015（contracts/ 仅类型与接口）
- ADR-0033（声明式 AgentSpec 与协议化门面）
- ADR-0066（Control Slot）
- ADR-0068（CompiledRunPlan）
- ADR-0069 §六（PluginContract 9 段概念）
- ADR-0074（Plugin-Everything 裁剪版实施计划）
- ADR-0070（Reducer-as-Plugin，已落地）
- ADR-0072（Null-Default Discipline，已落地）
- ADR-0099（Service Factory 收敛，已落地 — 为本 ADR 的 Factory 收敛提供形态参考）
- ADR-0103（Locked-Surface and Port Policy）
- ADR-0105（Package Organization Discipline）
- ADR-0106（Naming Constitution）
- ADR-0109（Plugin 4-Element Declaration Mandate）

**核心决策一句话：** 以 `PluginContract` 为插件侧唯一合约；将 6 维 `LogicAddress` 折叠为 `PluginContract` 的 5 段子合约；同一次发布里把同前缀的 `Declarative*` 与三义的 `closure` 重载收口；**先沉淀语义，再规划物理文件移动**。

> ⚠️ **本 ADR 不在同 PR 做文件级重命名**——ADR-0067 / 0074 都吃过同 PR 改 100+ 引用的亏。命名收敛按五批独立 PR 走（见 §六），本 ADR 只确立**语义终态**与**执行规则**。

---

## 一、背景与三件事实

### 1.1 PluginContract 已存在但未启用

`lca/contracts/harness/composition/plugin_contract.py` 已实现 9 段 `PluginContract`：

```
identity        ─ PluginIdentity(id / version / owner)
architecture    ─ ArchitectureContract(group / role / control_slots)
capabilities    ─ CapabilityContract(provides / requires / effect_classes)
ownership       ─ OwnershipContract(reads / emits / state_authority)
authority       ─ AuthorityContract(grants / risk / requires_approval)
lifecycle       ─ LifecycleContract(allowed_scopes / lease / dispose)
observability   ─ EvidenceContract(descriptors / privacy / replay)
verification    ─ VerificationContract(schemas / fixtures / test_suite)
contribution    ─ tuple[Any, ...]      （可选静态补充）
```

ADR-0069 §六明确：「PluginContract 是协议（不是强制门禁）。PluginManifest 可填可空；空 `PluginContract()` 等价于'作者未声明'。」

### 1.2 但生产插件全部走另一条路：LogicAddress

仓库事实（`grep` 在 2026-08-31 跑出，排除 `.venv`）：

| 模式 | 命中数 | 含义 |
|---|---|---|
| `logic_address=LogicAddress(...)` | **195** 处 | PluginManifest 现役入口 |
| `contract=PluginContract(...)` | **0** 处 | 无人使用 |
| `functional_group=FunctionalGroup.X` | **241** 处 | 散布 `@plugin(...)` 装饰器顶层 |
| 同前缀 `DeclarativeRuntime*` | **93** 处 | 命名重载 |
| `RuntimeClosure(` 构造调用 | **0** 处 | 仅作类型 import |

`@plugin(...)` 当前签名（`lca/harness/plugin/plugin_declaration.py`）：

```python
def plugin(
    setup: PluginSetupFn | None = None,
    *,
    id: str,
    Config: type[BaseModel] | None = None,
    provides / requires / implements,
    layer: str,
    kind: PluginKind,
    effects: EffectClass | str | Sequence[...] | None,
    test_suite / description / meta,
    relations / contributes,
    functional_group: FunctionalGroup | str | None = None,  # 入口 A
    logic_address: LogicAddress | None = None,               # 入口 B
    contract: PluginContract | None = None,                  # 入口 C ← 隐性
    spec: PluginSpec | None = None,
    ownership: OwnershipDeclaration | None = None,
) -> ...: ...
```

**一个语义事实，三条入口（A/B/C）；A/B 各自有 100+ / 195 处用法。**

### 1.3 ADR-0109 已强制了「显式声明」

ADR-0109（D1）已强制 plugin 显式声明 4 元素事实单元（Identity / Capability / Interaction / Verification），其中「Interaction」即 `logic_address`。

PR-1（2026-08-30 落地）把 `logic_address` 从「可选软约束」提升到 **CI 闸口**（缺即阻断合并）。

问题：ADR-0109 的门禁指向了 `LogicAddress` 这个**被设计为「可与 PluginContract 并存」的扁平容器**——而 PluginContract 是 ADR-0069 §六早已定义的内嵌版同物。**两条路指向同一概念；ADR-0109 强制了一条，但更优雅的一条还是空跑。**

---

## 二、第一性原理

> 第一性问题：插件作者**第一次**应该看到什么、**第二次**应该看到什么？

| 视角 | 第一次 | 第二次 |
|---|---|---|
| 作者写新插件 | 应该**一眼看到唯一一种**合约声明方式 | 应该不被「『我应该填 contract 还是 logic_address 还是 functional_group』」绊住 |
| 读者读陌生插件 | 应该**看到一段语义有名字的合约**（identity / architecture / lifecycle / authority / observability 等），而不是 6 个松散的字段名 | 应该不需要反复对照 ADR-0069 才能解释 `evidence=(...)` |
| 框架做编译/校验/lint | 应该**有 5 个语义段**，每个段对接一个验证器；不是「6 维独立 + 5 个分数拼总分」 | — |

**核心原则：**

### P1. 单一合约面（Single Contract Surface）

任何插件通过 `@plugin(...)` 暴露给框架与读者的**合约事实**有且仅有一条合法入口。多种入口并存时，框架必须在内部归一，但**不让作者绕过**——这条原则下当前 `functional_group=` / `logic_address=` / `contract=` 三入口并存是**反原则**。

### P2. 段语义自描述（Section Self-Describes）

合约字段必须**以名词短语出现**（identity / architecture / authority / lifecycle / observability / verification / contribution），而不是以**维数编号**出现（`LogicAddress` 的 6 维）。给字段组一个**段落名**，读者**不需要看 ADR** 就能猜每一组里装的是什么。

### P3. 字段最小惊讶（Minimal Surprise）

如果两种命名在同一仓库表达**同一概念**，架构层必须二选一保留一个。当前：

- `functional_group` vs `architecture.group`
- `control_slot` vs `architecture.control_slots`
- `scope` vs `lifecycle.allowed_scopes`
- `authority`（元组）vs `authority.grants`（元组）
- `evidence`（元组）vs `observability.descriptors`（元组）
- `revision` vs `identity.version`

每一对都是**同一信息的两种写法**——必须**只保留段化版**。

### P4. 名实不可压缩（Cannot Subtract Without Loss）

折叠不等于删除：`LogicAddress` 6 个字段**全部要保留**——只是它们迁入 `PluginContract` 的 5 个段：

```
functional_group  ────┐
control_slot      ────┼──→  PluginContract.architecture
scope             ────┘                    │
authority         ────────────────→  PluginContract.authority
evidence          ────────────────→  PluginContract.observability
revision          ────────────────→  PluginContract.identity.version
```

不是丢字段，是**换容器**。

### P5. 重命名 ≠ 重设计（Renaming Is Not Redesign）

本 ADR 不重设计 `RuntimeBindings` 与「冻结闭包」概念本身——其**模式正确**（见 §1）。只收**「Declarative*」**前缀噪声与 **「Closure」** 三义冲突。

### P6. 命名收敛不在同 PR（No Big-Bang Rename）

名字是 lexically hard dependency。同 PR 改 100+ 调用点曾在 ADR-0067 / 0074 阶段痛过；不再犯。本 ADR 确认**语义终态**与**门禁规则**，物理重命名交由五批独立 PR 走（每批 ≤ 30 文件入口，可独立合并）。

---

## 三、决策

### D1. `PluginContract` 是插件侧唯一合约面

`PluginContract` 从「可选并存」（ADR-0069 §六 / ADR-0109 既定）升级为**唯一**：

- `@plugin(...)` 中 `functional_group=` 与 `logic_address=` 在 **PR-A 落地时**（见 §六）变为**别名键**，内部直接喂入 `PluginContract` 对应段；
- `contract=` 是**正式键**；
- ADR-0109 D1「Interaction 必须声明」的门禁改为核对 `contract` 段的存在与否，而不是 `logic_address` 这个**字段名**。

这是**唯一带不可兼容性的变更**——但实现是**兼容性 alias**，旧插件**完全不动也能继续通过门禁**：

```python
@plugin(
    id="phase.act.standard",
    provides=("phase.act.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,        # ← 仍合法（alias）
    logic_address=LogicAddress(                             # ← 仍合法（alias）
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('phase_act_standard.checked',
                  'phase_act_standard.served'),
        revision="v1",
    ),
) -> ...: ...
```

⇓ 等价新写法（推荐；PR-A 后 CI 鼓励） ⇓

```python
@plugin(
    id="phase.act.standard",
    provides=("phase.act.standard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(                          # ← 正式键
        identity=PluginIdentity(id="phase.act.standard", version="v1", owner="lca-runtime"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        capabilities=CapabilityContract(
            provides=("phase.act.standard",),
            requires=(),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_act_standard.checked", "phase_act_standard.served"),
        ),
        verification=VerificationContract(test_suite="tests/declarative/test_phase_graph.py"),
    ),
) -> ...: ...
```

### D2. `LogicAddress` 退役（生产面），保留为**适配类型**

`lca/contracts/protocols/composition/logic_address.py` 中 `LogicAddress` / `LogicAddressScore` **进入 deprecated 区**：

- 模块顶部追加 `warnings.warn(..., DeprecationWarning, stacklevel=2)`；
- `__post_init__` 不变；
- 仅作为**『旧式扁平化数据』↔『段化 PluginContract』的桥**保留：
  ```python
  def from_logic_address(addr: LogicAddress) -> PluginContract: ...
  def to_logic_address(c: PluginContract) -> LogicAddress: ...    # 删 evidence_list 双向空容差
  ```
- `from lca.contracts.protocols.composition.logic_address import LogicAddress` 仍可 import，但开发者会看到 deprecation warning（PR-A 阶段）。

**退役分两阶段：**
- PR-B：deprecated 警告，0 处强制迁移；
- PR-C：`lca plugin check` 警告，**新的 plugin 不再用 LogicAddress**；
- **6 个月后** PR-D：删除文件，先冻结 v0.6 兼容线一条。

### D3. `functional_group=` 与 `logic_address=` 装饰器键退化为 alias

落地在 `@plugin(...)` 装饰器函数（`lca/harness/plugin/plugin_declaration.py`）：

- `functional_group=` 与 `logic_address=` 被装饰器内层吸收，**不出现于** `PluginDefinition.functional_group` / `logic_address` 的终态 `meta` dict；
- 终态 meta 只存 **canonical** 形式：即 `contract=PluginContract(...)` → 折叠为 5 段摘要写入 `meta.contract_snapshot`；
- `definition_from_plugin` 与 `native_spec_from_declaration` 同步收敛——不再读取旧 `functional_group` / `logic_address` 平铺键。

**保留 alias 是兼容性考量；alias 调用点本身**在新插件中不再被推荐使用**。

### D4. 段化「layer」+「kind」折叠为 `architecture.tier`

`@plugin(...)` 的 `layer=` / `kind=` 是**架构战术信号**——它们与 `architecture` 段语义重合：

```python
# 现在
@plugin(layer="L2", kind=PluginKind.PRIMITIVE, ...)

# 等价段化（仍允许）
@plugin(
    contract=PluginContract(
        architecture=ArchitectureContract(
            tier=Tier.L2_PRIMITIVE,    # 枚举 L0_KERNEL / L1_SEAM / L2_PROVIDER / L3_PRIMITIVE / L4_BUNDLE
            ...
        ),
    ),
)
```

- PR-A：**只新增 alias**（`tier=` 键作为折中形态），不破坏现有 `layer=` / `kind=`；
- PR-D：把 `layer` 与 `kind` 折叠为单一 `Tier` 枚举（enum value 同时编码层与种类）。

### D5. 「Declarative」前缀在公开 API 中淘汰

**Phase 1 候选（PR-E）** 仅释放**公开 re-export**——类型内部名不动，避免 100+ 引用崩溃：

| 旧名（保持） | 公开 re-export 别名（新增） | 含义 |
|---|---|---|
| `DeclarativeRuntimeBindings` | `RuntimeBindings` | 冻结闭包 |
| `DeclarativeRuntimeDriver` | `RuntimeDriver` | 跑闭包的 carrier |
| `DeclarativeExecution` | `TurnExecutor` | 单 turn 解释 |
| `DeclarativeInterpreter` | `PlanInterpreter` | 真正的图解释器 |
| `DeclarativeInterpreterFactory` | `InterpreterFactory` | 上面那个的工厂 |
| `DeclarativeRuntimeSeams` | `RuntimeSeams` | providers 实现侧 |
| `lca.harness.declarative` | `lca.harness.execution` | 解释器 + Phase 观察 + 控制 |

`declarative.py` / `declarative_runtime.py` **文件本身不立即改名**（避免 100+ import 一次性改坏），但**所有面向作者的公开文档与新代码**采用上表「别名」。

### D6. 「Closure」三义收口

`Closure` 词在 LCA 仓库至少三义：

| 旧用法 | 改用 | 含义 |
|---|---|---|
| `lca.harness.declarative.MappingRestrictedScope`（行为闭包） | 保留命名（该用法本就正确） | 函数式闭包 |
| `lca.harness.profile.runtime_closure.RuntimeClosure`（profile 侧装配要求目录） | 改名 `RuntimeRequirements`（PR-F） | 「必须装哪些能力」 |
| `DeclarativeRuntimeBindings`（已组装的冻结闭包） | （已 D5 改名 `RuntimeBindings`） | 运行期事实 |

**LR-CLOSURE-1（PR-F）：** 所有「Closure」作名词出现在公开 import、文档、类型名时，**必须不再用作「profile 装配要求」的同义词**。函数式闭包用法保留（含义不同）。

### D7. v3 9 群与 ADR-0069 13 群：维持并存，文档合并

不复用同一名字空间——v3 9 群是**宪法内化认知**，0069 13 群是**工程外化分类**。两者并存合法。但：

- 013 群映射文档（`docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md` §1.1）目前散落在设计文件；PR-G 把这一映射表**落进** `docs/architecture/functional-group-mapping.md` 作为**单一权威**；
- `FunctionalGroup.V3_TO_0069_MAPPING` 字典已经在代码里，但**文档没有指向代码**；PR-G 加指针；
- 同时在 `scripts/check_plugin_metadata.py` 输出 end-of-run 提示「1 PDF 调用解析映射」。**不**变 schema。

### D8. 硬软门禁单一矩阵

ADR-0069 / 0074 / 0109 三处分散写了「软 / 硬」。本 ADR 在**单一文件** `docs/architecture/plugin-check-matrix.md`（PR-H）出 6 行 cheat sheet：

```
1. 不填 contract / 不填 functional_group     →  warning（lint 不阻断，CI 报告）
2. contract 写在 9 段以外字段                  →  error
3. plugin.serve 在 capability grant 不在 closure →  error（fail-fast at resolve）
4. evidence descriptor 不在 journal catalog     →  warning（journal 是 ground truth）
5. 多群 / 矛盾 tier                            →  error（--strict 时；非 strict 仅 warning）
6. capability grant ⊆ 父 grant 违反             →  error（构建期 fail）
```

**`lca plugin check --strict` 是这条规则的执行面，不是不同规则的来源。**

### D9. Factory 收敛为短方法

仓库里 `EffectGatewayFactory` / `DeltaReducerFactory` / `DeclarativeInterpreterFactory` / `RuntimeJournalFactory` / `ResultFinalizerFactory` / `CheckpointStateResolverFactory` 至少 6 个工厂协议，每个工厂协议的 `.create(...)` 方法**做的事都是单行**（构造一个 dataclass / 拉一个注册器）。它们的存在**增加了 6+ 类的命名表，但零行为增益**。

PR-I（与 D5 同步）：

- 工厂协议 `XFactory.create(...)` 一律保留**作为抽象可替换 seam**（这是 C6 最小化的反向——非 plugin 化的协作）；
- 但 `RuntimeBindings`（D5 后）的 `new_xxx` 方法（`new_checkpoint_state_resolver` / `new_result_finalizer` / `new_effect_gateway` / `new_delta_reducer` / `new_interpreter` / `new_driver`）作为**唯一引用面**，所有其他 helper（`assemble` 之外）折叠为 6 个 `new_*` 即可——单「seam」接口承载 6 工厂。

### D10. 新概念拒绝机制（明确写在 ADR）

任何后续想引入**又一个**插件侧合约维度（例如「policy set」「budget override surface」）必须：

1. 先证伪 PluginContract 9 段不能表达；
2. 写 ADR 提案并 **relates-to** 本 ADR；
3. 在没通过前，**只能**塞进 `PluginContract.contribution` 段（已留的「可选静态补充」位）。

`contribution` 段本身不为运行时引用——只供 codegen、lint 报告使用。这条规则**等价于 ADR-0069 §一末尾**——本 ADR 只是让 **004-0069 那条对 plugin 化的护栏**也覆盖 plugin 侧合约。

---

## 四、不变量继承

| 不变量 | 继承 ADR | 本 ADR 内的语义 |
|---|---|---|
| C1 闭集 | 0002 / 0069 | **段化不增加段**——9 段不变（最多合并；不允许新增） |
| C2 双平面 | 0002 | **不变** |
| C3 Journal | 0037 | `observability.descriptors` 仍必须出现在 `journal_catalog`——由 ADR-0069 §三 11 关系代数保证 |
| C4 Reducer | 0070 | 不变：`PluginContract` 不引入 reducer 入口 |
| C5 能力衰减 | 0066 | `AuthorityContract.grants` 与生命周期 grant 衰减链照旧 |
| C6 最小化 | 0001 | **§D10** 是 C6 在合约维度的延伸 |
| C7 控制/观察分离 | 0074 | **不变**：`observability` 段只描述「会留什么痕」，不描述「谁可以订阅」 |

---

## 五、ADR-0069 §六 PluginContract 与 ADR-0110 PluginContract 的关系

ADR-0069 §六给的是**概念**——可填可空、与 `PluginDefinition` 并存。

本 ADR 把它**做实**——`PluginContract` 成为**插件唯一的合约载体**：

| 维度 | ADR-0069 §六 | ADR-0110（本次） |
|---|---|---|
| 状态 | 概念，可选并存 | **唯一**——`functional_group=` / `logic_address=` 是 alias |
| 校验 | 空 `PluginContract()` 等价「未声明」 | **空合约 → warning**（不阻断） |
| 入口 | 通过元注解存入 `meta` | **canonical meta key `contract_snapshot`（PR-A 引入）** |
| 文档定位 | ADR 提及 | 插件作者 onboarding 一行：「always start with `contract=PluginContract(...)`」 |
| 关系代数 | 提供 9 段基础，**不强制用** | **强制段化**——6 dim LogicAddress 折叠进既有段 |

`PluginContract` 的 dataclass 与字段本身**不动**——这是 ADR-0069 已稳定的语义成果。本 ADR 只**收口使用**与**对齐入口**。

---

## 六、迁移（5 批独立 PR）

| 序 | 名称 | 风险 | 触线 | 合并顺序 |
|---|---|---|---|---|
| **PR-A** | `@plugin(...)` 接 `contract=PluginContract`，alias 三键共存 | 低 | `plugin_declaration.py` 单文件；底层 `meta` 新增 `contract_snapshot` 键 | PR-1 (D3 落地) |
| **PR-B** | `LogicAddress` deprecation warning | 低 | 单文件顶部加 warning | PR-2 |
| **PR-C** | codemod 把 195 处 `logic_address=LogicAddress(...)` 改 `contract=PluginContract(...)` | 中 | 影响约 195 文件；codemod 用 `libCST` | PR-3（PR-A 合后 1 周） |
| **PR-D** | 6 个月后删除 `LogicAddress`；tier 合并 | 中-高 | 删文件 + tier 枚举合并 | PR-4（冻结 v0.6 兼容线） |
| **PR-E** | 「Declarative」前缀 re-export 别名 | 低 | `lca/runtime/__init__.py` 等 6 处 re-export | PR-5 |
| **PR-F** | 「Closure」三义收口（`RuntimeClosure` → `RuntimeRequirements`） | 中 | `runtime_closure.py` 模块文件 + alias 兼容 | PR-6 |
| **PR-G** | 文档合并（functional group mapping） | 低 | 1 个新文件 + 1 个 README 修订 | PR-7 |
| **PR-H** | 硬软门禁 cheat sheet（`plugin-check-matrix.md`） | 低 | 1 个新文件 | PR-8 |
| **PR-I** | Factory 收敛（`new_*` 单 seam） | 中-高 | `runtime_bindings.py` 改 API | PR-9（与 E/F 并行） |

**PR-A → PR-H 累计影响**：~250 文件（按 6 个月工期摊销 ~10 / 周）。**PR-D 前不删任何现行类型**。

---

## 七、副作用与权衡

### 7.1 取舍

| 失 | 得 |
|---|---|
| 9 段 dataclass 比 6 元 flat dataclass 写起来稍繁 | 字段不再平铺，认知维度立即收敛 |
| 旧 `LogicAddress` 用户要轻迁移（IDE 自动 convert） | 内部 `meta` 字典减少 6 键，profile resolve 阶段一次归一 |
| 工厂收敛（PR-I）让一部分人失去「自造新工厂协议」自由 | 6 个 `new_*` 入口单 seam，boot 阶段可一次校验 |
| 多一层段化，对纯调研场景（「一行告诉我这个 plugin 是几群」）需要走到 `architecture.group` | 同一段里 `role` / `control_slots` 信息**同时出现**，调研效率反而↑ |

### 7.2 未解决（明确写下，下一个 ADR）

| 项 | 后续 ADR |
|---|---|
| `v3 9 群 vs 13 群` 文档收敛（PR-G 已含） | 与 `docs/specs/lca-structured-cognition-guide.md` 单向对齐 |
| `ControlSlot` 11 槽是否合并到 9 槽 | 单独 ADR（**不是本 ADR 范围**） |
| `AuthorityContract.grants` 与 `EffectClass` 是否能合一 | 单独 ADR（**不是本 ADR 范围**） |
| `PluginContract.contribution` 段是否要删 | 待看 ADR-0085 后续采纳情况再说 |

---

## 八、验收（Definition of Done）

每批 PR 落地后：

1. **CI 全绿**：`uv run pytest` 全量通过；`lca plugin check --strict` 通过；
2. **`grep -rn "logic_address=LogicAddress" lca/`** 在 PR-C 落地后 ≤ 0（codemod 改完）；
3. **`grep -rn "Declara\w*Runtime\w*" lca/`** 在 PR-E 落地后 ≤ 0（公开 API）；
4. **`check_plugin_metadata.py`** 输出引用 `plugin-check-matrix.md`（PR-H）；
5. **新增 plugin onboarding 文档** `docs/guides/plugin-authoring.md` 单段示例（首行写到「always start with `contract=...`」）。

终态：

- 任何插件作者读「`tests/declarative/test_phase_graph.py`」一段示例就能写出合规 plugin——**不读 ADR-0069 也能写出合法 functional_group**。
- `lca plugin check` 报告含**段名级别**结果（如 `architecture.group: G7_EXECUTION (✓ known)`）而非「6 维 75 / 100」分制。

---

## 九、参考资料

- ADR-0001 五层单向依赖：分层方向不变
- ADR-0033 声明式 AgentSpec：原 contract 表达共识的来源
- ADR-0066 控制槽：11 槽归宿于 `architecture.control_slots`
- ADR-0068 CompiledRunPlan：`PluginContract` 不进 plan，**只**作 plugin 自身文档
- ADR-0069 §六 PluginContract：本 ADR 的语义继承点
- ADR-0074 Plugin-Everything 裁剪：分类学作为软约束——本 ADR 不颠覆
- ADR-0109 4-Element Mandate：补完 4 元素 100% 强制后的语义合并
- ADR-0106 命名宪法：本 ADR 的命名收敛需符合该宪法术语级别
- ADR-0103 Locked-Surface：`lca/plugins/seams/` / `lca/plugins/providers/` 边界保持
- `docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md`：v3 9 群与 13 群映射文件
- `docs/specs/lca-structured-cognition-guide.md`：作者面向的术语表
- `lca/contracts/harness/composition/plugin_contract.py`：9 段类型定义（已存在，未启用）
- `lca/contracts/protocols/composition/logic_address.py`：6 维扁平（待退役）
- `lca/runtime/runtime_bindings.py`：冻结闭包定义（不动，保留 `new_*` 单 seam）
