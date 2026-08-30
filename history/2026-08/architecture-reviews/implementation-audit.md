# ADR-0066–ADR-0076 当前代码落地审计

**审计日期：2026-08-24**

本报告核对 ADR-0066、ADR-0067、ADR-0068、ADR-0069、ADR-0074、ADR-0075 和 ADR-0076 的当前代码、测试、实施账本与架构门禁。结论是：**核心声明式计划链已经进入代码并可通过大部分针对性测试，但整体尚未达到“全部落地、全量验收通过”的状态。** 当前仓库的 `origin/main` 与本地 `main` 在审计开始时一致且工作区干净；本次变更仅补充审计结论和修正文档中的失效测试路径，没有把未完成能力标记为已完成。

## 一、总体结论

| ADR | 当前判定 | 已落地的主要能力 | 尚未闭环的主要问题 |
|---|---|---|---|
| ADR-0066 | **核心已落地，验收存在回归** | ControlSlot、ControlPlan、单调聚合、Reducer 单写约束和声明式控制贡献均有实现与针对性测试。 | 旧测试仍要求已删除的 `_loop` 直接调用 `self.stop_rule.decide`；全量测试因此失败，需更新测试契约或补充等价的声明式证据。 |
| ADR-0067 | **按 ADR-0074 裁剪版落地** | 四状态 Artifact、四个 Creator 面、三道闸和两类运行子空间已进入当前实现。 | ADR-0067 原始的五子空间、八状态、七 Creator 面和六道闸并非当前目标；它们已被 ADR-0074 部分取代，不能按原始全集宣称全部实现。 |
| ADR-0068 | **核心已落地，运行结果传播有回归** | `CompiledRunPlan`、PlanCompiler、CommandEnvelope、ArtifactController、plan_ref 和声明式解释器均存在。 | `tests/declarative/test_runtime_driver.py` 有一项失败：运行已调用 body/memory，但 stop 结果未传播为最终输出，`Result.from_state()` 将其判定为 FAILED。 |
| ADR-0069 | **数据面和模板能力已落地** | 13 个功能群、LogicAddress、11 种关系、6 个 contribution verbs、PluginContract 和 12 个 PlanTemplate 均有实现及测试。 | 其能力仍受 ADR-0075/0076 的替换性、类型安全和全量回归问题约束，尚不能单独代表整套插件化架构已经 sign-off。 |
| ADR-0074 | **实施账本已完成，但整体 sign-off 不成立** | tracker 标记 PR-0 至 PR-12 完成；核心 Plugin-Everything 数据面、编译、执行、四状态 Artifact 和 Creator 四面均已进入代码。 | 验收规约曾引用已删除测试文件并声称全绿；当前全量 pytest 仍有 27 项失败，验收文档已被本次修订为与现状一致。 |
| ADR-0075 | **核心路径已落地，11 项整改仍未全部完成** | `CompiledRunPlan → GraphAssembler → GenericPlanInterpreter → RuntimeEffectGateway` 主链、Effect/Delta registry、Journal committer、控制贡献和进程内幂等均存在。 | 仍有旧兼容入口、隐式默认/回退、静态 action scope、artifact closure 自由函数、未知 delta 静默忽略、部分 `Any` 类型以及 Recovery plugin 未实现。 |
| ADR-0076 | **P0/W1 能力已落地，替换测试与生产闭合仍不完整** | 六平面 taxonomy、team seam、run_mode_registry、boot binding validator、mode adapter 和静态替换门禁均已实现。 | `CognitiveRuntime` 仍保留运行时 registry 默认回退；action catalog 尚未进入 compiled plan；部分 Composer 仍有直接默认选择；门禁主要是静态扫描；全量回归、Protocol 显式继承和类型门禁仍失败。 |

## 二、ADR-0075 的 11 项整改逐项状态

| 编号 | 整改项 | 当前状态 | 代码证据和判断 |
|---:|---|---|---|
| 1 | DecisionClassifier seam | **部分实现** | `DecisionClassifier` Protocol、provider 和 `ModularBrain` 注入路径存在，但 `llm_result.py` 的旧分类函数和默认 provider 回退仍保留，尚未形成生产路径的严格 seam-only 约束。 |
| 2 | EffectHandler registry | **部分实现** | `EffectHandlerRegistry`、两个默认 handler 和 RuntimeEffectGateway 已接线；但 RuntimeEffectGateway 仍保留兼容 facade 和无 registry 时的默认构造，生产路径尚未完全做到 profile binding 唯一来源。 |
| 3 | DeltaHandler registry | **部分实现** | 11 个 delta handler 和 registry 已存在，解决了原先只覆盖 5 个操作的问题；未知 operation 当前返回原 state，属于静默忽略，未达到 fail-closed 的完整契约。 |
| 4 | ActionHandler registry | **未完全实现** | provider registry 已存在，但 `_operation_for`、`_SCOPE_ACTIONS` 和默认 action registry 构造仍在生产模块；实际允许 action 尚未由 `CompiledRunPlan` 的 authority 数据唯一推导。 |
| 5 | L2 默认实现插件化 | **已实现** | `DefaultReducer`、`ClosedSetTopology` 和 `DefaultStopRule` 已有 plugin 注册；相关 boot/runtime binding 测试通过。 |
| 6 | ArtifactClosure seam | **部分实现** | `ArtifactClosure` Protocol/provider 已存在，但 `DeclarativeRuntimeDriver` 仍直接调用 `synthesize_artifact_closure()`，未完全通过已绑定 seam 消费。 |
| 7 | GateChainComposer seam | **部分实现** | `GateChainComposer` provider 与注入路径已存在；旧 `build_workspace_agent_gate()` 兼容函数及默认回退仍保留。 |
| 8 | SimpleBrainFactory fallback | **部分实现** | 已使用 `ctx.inject_or_null("gate_chain_composer")` 和 `decision_classifier`，但缺失注入时仍回退到固定 gate builder、Null critic/synthesizer，未达到 ADR-0075 对隐式默认的完全禁止。 |
| 9 | RuntimePhaseCapabilities 类型安全 | **已实现** | `brain`、`body`、`memory`、`perceive_hub`、`stop_rule` 已使用对应 Protocol 类型。 |
| 10 | ReducerDeltaAdapter 类型安全 | **基本实现** | adapter 的 reducer、state、delta 已使用 Protocol/模型类型；但外围 handler 和解释器仍存在宽泛类型，整体类型门禁尚未通过。 |
| 11 | DeclarativeRuntimeDriver 类型安全 | **未完全实现** | Driver 的核心依赖已标注 Protocol，但 `run(state: Any)` 以及相邻声明式解释器/phase provider 仍有 `Any`，`check_no_any.py` 当前失败。 |

## 三、ADR-0076 当前落地状态

ADR-0076 的六平面 taxonomy、`team_seam`、`run_mode_registry` 和生产 binding validator 已进入代码，并且专门测试集通过 **80 项**。这证明 P0/W1 的结构性改动已经落地，但不能把静态 AST 门禁直接等同于完整替换性验收。

当前尚未完成的关键闭环包括：生产 runtime 不能依赖 registry 默认回退；`_SCOPE_ACTIONS` 必须迁入 compiled plan 的 authority 数据；Body/Perceive/Team Composer 必须只消费 compiled capability；run mode 需要真实 profile/plugin 替换 fixture；以及全量测试、显式 Protocol 继承和 `Any` 类型门禁必须恢复为绿色。

## 四、验证结果

| 验证命令 | 结果 | 说明 |
|---|---:|---|
| `uv run pytest --no-cov -q` | **2768 passed, 27 failed, 18 skipped, 16 deselected** | 全量未通过；失败分布在声明式运行结果、旧测试契约、spawn binding、协议继承、代码规范、HIL、trace 和 plugin alignment。 |
| ADR-0076 相关架构/替换/Composer/boot 测试 | **80 passed** | `test_six_plane_taxonomy`、`test_substitution_gates`、`test_run_mode_registry`、Composer 和 binding validator 通过。 |
| ADR-0066–0069/0074 核心测试 | **490 passed, 1 failed** | 唯一失败为声明式运行结果未将 stop rule 的 `COMPLETED/final_output` 传播到最终 `Result`。 |
| `tests/test_adr_acceptance.py` 及相关接受测试 | **67 passed, 1 failed** | 失败原因为验收规约引用了已删除的 `tests/layer2_runtime/test_control_runtime_execution.py`；本次已改为现存的 `tests/declarative/test_runtime_driver.py`，该运行时测试本身仍需修复。 |
| `uv run python scripts/check_adr_supervision.py` | **通过** | tracker 与 git commit 引用一致。 |
| `uv run python scripts/route_legacy_patterns.py --json` | **通过，total=0** | PR-0 历史迁移基线为 0。 |
| `./scripts/lca-ops status-adr-supervision` | **通过** | ADR supervision tracker consistent。 |
| `uv run python scripts/check_protocol_impl.py` | **失败，18 处** | provider 和 `DeclarativeRuntimeDriver` 虽具备 Protocol 方法集，但多个类没有显式继承对应 Protocol。 |
| `uv run python scripts/check_no_any.py` | **失败** | runtime、phase provider、mode/loop driver 等仍存在宽泛 `Any` 类型。 |

## 五、推送前应继续处理的任务

下一轮实现应按以下顺序收敛，而不是继续扩大 ADR 范围。第一，修复声明式 stop/final output 状态传播和与新架构不一致的旧测试；第二，消除 runtime、action catalog、artifact closure、gate chain 和 Composer 的隐式默认与兼容回退；第三，将 action authority、effect/delta handler 和 team/mode binding 完整纳入 compiled plan；第四，给所有 Protocol 实现补充显式继承并清理运行时 `Any`；第五，补齐真实替换 fixture、Recovery plugin 和全量回归测试，之后再重新计算 ADR-0075/0076 的 sign-off。

本次审计**没有把上述未完成项伪装成已实现，也没有删除旧测试来制造绿色结果**。仓库的 ADR supervision tracker 和历史迁移路由检查保持通过，但这两个门禁只能证明 tracker 一致，不能替代全量功能验收。

## References

[1]: docs/adr/0066-declarative-atomic-control-plugins.md "ADR-0066: Declarative Atomic Control Plugins"
[2]: docs/adr/0067-spacetime-runtime-and-governed-creation.md "ADR-0067: Spacetime Runtime and Governed Creation"
[3]: docs/adr/0068-compiled-plugin-kernel-and-unified-run-plan.md "ADR-0068: Compiled Plugin Kernel and Unified Run Plan"
[4]: docs/adr/0069-agent-primitive-system-and-declarative-grammar.md "ADR-0069: Agent Primitive System and Declarative Grammar"
[5]: docs/adr/0074-plugin-everything-trimmed-implementation.md "ADR-0074: Plugin-Everything Trimmed Implementation"
[6]: docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md "ADR-0075: Declarative Phase Graph and Minimal Trusted Kernel"
[7]: docs/adr/0076-six-plane-capability-layout-and-substitution-test.md "ADR-0076: Six-Plane Capability Layout and Substitution Test"
[8]: docs/plans/adr-0074-plugin-everything-tracker.md "ADR-0074 Plugin-Everything 实施追踪"
[9]: docs/plans/full-plugin-remediation.md "全面插件化整改计划"
