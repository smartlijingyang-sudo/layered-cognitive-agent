# lca/cognition — 纯认知原语（R2）

> v3 概念群 · [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)

## 职责

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

## 不负责

- `Session.append` / Journal / spine reflector（→ `lca/loop/fact_gateway`）
- Phase 图遍历（→ `harness/graph`）
- HTTP（→ transport）

## 禁止依赖

`harness`、`plugins`、`runtime`、`agent`、`application`（见 pyproject package_contracts）

## Gate 正名

**六语义 phase 无独立 gate 节点**；Gate 链在 `brain/cognitive_pipeline.py` 的 Think 子步骤内。
