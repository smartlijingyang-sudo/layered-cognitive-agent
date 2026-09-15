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

## 禁止依赖

`harness`、`plugins`、`runtime`、`agent`、`application`（见 pyproject package_contracts）

## Gate 正名

**六语义 phase 无独立 gate 节点**；Gate 链在 `brain/cognitive_pipeline.py` 的 Think 子步骤内。
