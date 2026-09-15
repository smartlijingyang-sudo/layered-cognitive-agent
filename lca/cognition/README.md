# lca/cognition — 纯认知原语（R2）

> v3 概念群 · [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)

## 1. 职责

**算法与编排，零 I/O、零事实写入。** 插件（`plugins/cognitive/`）注册本层实现。

| 子包 | 概念群 | 内容 |
|---|---|---|
| `brain/` | Think + **Gate** | Reasoner、Pipeline、`decision_gates/`（Gate ⊂ Think） |
| `body/` | Act | SafeExecutor、tool dispatch |
| `memory/` | Memory | propose/commit 实现 |
| `perceive/` | Perceive | hub、service |
| `wire/` | 认知 transport 适配 | envelope、registry_factory |
| `brain/gate_service.py` | Think 内 Gate 服务 | Gate ⊂ Think |
| `sensors/` | Perceive | 传感器实现 |
| `collaboration/` | Collaboration | Team 认知辅助 |

## 2. 不负责

- Journal / spine reflector 与 EP 投递（→ `lca/loop/fact_gateway`）；Body 执行路径需要落事实时，只经注入的 `RunSessionWriter` 接缝（见 §7）
- Phase 图遍历（→ `harness/graph`）
- HTTP（→ transport）

## 7. 副作用

认知面默认**无副作用**：Reasoner / Gate / Critic / Memory 算法返回
`Decision` / `Observation` / `Reflection` 等值，由 runtime 决定如何落事实。

两处例外，都在执行边界上，且都只经接缝、不直接写后端：

| 位置 | 后果 |
|---|---|
| `body/executor/simple_body.py` | 经注入的 `RunSessionWriter.append_assistant_message` / `append_tool_result` 追加事实；写失败时返回带原因的 `Observation`（`session_persistence_failed`），不伪造成功 |
| `brain/llm_turn/executor.py` | 经 `lca.infrastructure.session.bindings` 读绑定 Session、在模型请求边界触发 durability checkpoint |

`simple_body.py` 与 `llm_turn/executor.py` 引用的 `RunSessionWriter` 在前者是
`TYPE_CHECKING` 类型标注、在者是运行时注入对象的类型；两者都不 import runtime 的
实现类，装配由 `application` 完成。

## 3. 输入

`AgentState`、`Decision` / `Observation` / `Reflection`、`Budget`、`RoleProfile` /
`TeamAwareness`、`MemoryRecord` 等 `lca.contracts` 类型；执行路径额外接受注入的
`RunSessionWriter`、`ToolRegistry`、`SkillPackageStore` 等接缝对象。

## 4. 输出

`__all__` 汇总约 178 个符号，按家族分：`brain/`（Reasoner、Critic、Gate 链、
prompt 组装）、`body/`（`SimpleBody`、`SafeExecutor`、ActionRegistry）、
`memory/`（null / layered / team / simple / semantic / temporal / policy）、
`perceive/`、`sensors/`、`collaboration/`（Blackboard、AgentExecutor）、
`team/`、`wire/`。认知产出是**值**：Decision / Observation / Reflection /
`ReasonerTurnPlan`，由 runtime 决定如何落事实。

## 5. 允许依赖

`lca.contracts`（类型与 Protocol）。现状还包含 `lca.infrastructure`（工具与凭据
适配器）、`lca.loop`（事实接缝）、以及 Body/LLM-turn 执行边界注入用到的
`lca.runtime.session.run_session_writer` 类型；这些是迁移中的例外，见 §6。

## 6. 禁止依赖

`harness`、`plugins`、`runtime`、`agent`、`application`（`pyproject.toml` 的
package contracts 与 `lint-imports` 强制；新增反向边会使该门禁失败）。

## 8. 失败语义

抛类型集中在执行与协议边界（按源码 `raise` 频次）：`ToolExecutionError` 19、
`ValueError` 15、`TypeError` 12、`RuntimeError` 7、`KeyError` 4、
`MissingPromptSectionError` 3、`RegistryKeyError` 2、`UnregisteredActionError` 1。
确定性错误（`ValueError` / `TypeError`）不重试；瞬时错误由执行窄门按分类处理
（AGENTS.md §3 错误分类、C10）。

## 9. 公共入口

`lca.cognition.brain`（Think 管线与 Gate 链）、`lca.cognition.body`（Body 与
SafeExecutor）、`lca.cognition.memory`（记忆系统实现）。调用方是 runtime /
plugins，不是另一个认知组件内部。


## Gate 正名

**六语义 phase 无独立 gate 节点**；Gate 链在 `brain/cognitive_pipeline.py` 的 Think 子步骤内。
