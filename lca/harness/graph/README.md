# lca/harness/graph — 最小可信图内核（MTK）

> **规格：** [declarative-phase-graph-spec.md](../../docs/specs/declarative-phase-graph-spec.md)  
> **决策：** ADR-0075 · ADR-0194 · ADR-0195

## 职责

声明式 **Phase Graph** 的编译、验证与解释机制（G0，不可插件化语义）。

| 组件 | 现状路径 | 目标 |
|---|---|---|
| Plan 编译 | `declarative/compile/` | 部分迁入 `composition/` |
| 图验证 | `declarative/graph/` | 迁入本包 |
| 解释器 | `declarative/execute/interpreter.py` | 与 `lca/loop/` 共管 |
| Phase 事务 | `declarative/lifecycle/phase_transaction.py` | → `lca/loop/transaction.py` |
| 控制治理 | `declarative/compile/phase_governance.py` | 本包 |
| Effect 分发 | `declarative/execute/dispatch.py` | 本包 |

## 不负责

- 具体 PhaseExecutor 实现（plugins/loop/phase）
- Brain/Body 算法（cognition）
- Session append（lca/session）
- HTTP（transport）

## MTK 不变量

- PG-001–PG-008（见 phase-graph spec）
- 不得硬编码 plugin id、工具名
- 不得 import `cognition`、`runtime`、`agent`

## 迁移

Wave P4：自 `harness/declarative/` 抽出 graph 子集至本目录；`declarative/` 保留至 shim 删除。
