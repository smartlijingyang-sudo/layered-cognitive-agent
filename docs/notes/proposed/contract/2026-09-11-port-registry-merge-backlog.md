# Agent Note: PortRegistry.merge 命名 + 语义 backlog

Status: proposed
Refs: ADR-0219 §5.2 + §11 delete-when row 13

## Backlog item

`lca/harness/graph/execute/v2/_port_context.py::PortRegistry` 与 ADR-0219 §5.2 描述三方不一致:

| 项 | 现状 | ADR §5.2 描述 |
|---|---|---|
| 方法名 | `merge_output(port_values)` (setdefault) | `merge(port_values)` (last-write-wins) |
| 行为 | `setdefault`: 后到的 key 不覆盖已有 key (outer input wins) | `merge`: 后到的 key 覆盖已有 key (last-write-wins) |
| `set_outer_input` | `dict.update` = last-write-wins | 未提及,但行为符合 `merge` 描述 |

## 影响面

- 唯一 caller: `lca/framework/subgraph/plugins/node_graph_driver.py:111, 378` 两处 `port_context.merge_output(out.port_values)`
- production e2e 跑过两轮 (baseline + after commit 51510a6b), 行为稳定
- `tests/integration/think/` 间接覆盖,但无单测 pin 现状

## 重要性评分

| 维度 | 评分 |
|---|---|
| production bug 风险 | 0 (现状行为稳定) |
| ADR gate 阻塞 | 中 (ADR §11 行 13 "PortRegistry.merge 含 last-write-wins 单测" 未落,ADR 不能升 Accepted) |
| 改动成本 | 中 (单测 + ADR 措辞修订 + 可选 API rename) |
| 当前会话状态 | 已收口, 不阻塞 |

## 决策

**本次会话不补**。理由:
- AGENTS.md §1 优先序列中, "可删的兼容尾段" 排在靠后位置
- ADR-0219 主体还在 Proposed, gate 触发 = ADR 升级时
- 真根因是三方不一致, 需单独 PR 解决 (test + doc + 可选 rename), 不应塞进 close-out SSOT 收敛 PR

## 接手者行动清单

1. 读 ADR-0219 §5.2 + §11 行 13
2. 决定 rename `merge_output` → `merge` + 改 last-write-wins 行为, 还是保留 setdefault 行为 + ADR 措辞修订
3. 补 `tests/contracts/test_port_registry_typing.py` 单测 pin 决策后的语义
4. 同步 ADR-0219 §11 行 13
5. 若 rename, 同步 `node_graph_driver.py:111, 378` + 所有 grep / 文档

## Delete-when(本 note 落地后)

- `tests/contracts/test_port_registry_typing.py` 存在且 pin `PortRegistry` 现状语义
- ADR-0219 §11 行 13 措辞与代码现状一致 (要么测试通过要么 ADR 修订完成)
- `node_graph_driver.py` 使用方法名与 ADR §5.2 一致