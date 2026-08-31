# Plugin 检查硬/软门禁单一矩阵（ADR-0110 D8）

## 用途

`lca plugin check` 在 plugin 元数据上跑的所有检查，按硬门禁（error）与软门禁（warning）单列。
`--strict` 切换：开启后所有「warning」也升级为 error。

## 矩阵

| # | 检查 | 默认 | `--strict` | 出处 |
|---|---|---|---|---|
| 1 | `@plugin(...)` 不声明 `contract=` 也未声明 `functional_group=` 与 `logic_address=` | warning | error | ADR-0069 §六、ADR-0109 |
| 2 | `contract=` 段定义在 PluginContract 9 段之外的字段 | error | error | ADR-0110 D10 |
| 3 | plugin 的 capability grant 在 `RuntimeClosure` 解析期不被运行时所需 | error | error | ADR-0066 |
| 4 | `observability.descriptors` 不在 `journal_catalog.EventDescriptor` 全集内 | warning | error | ADR-0069 §三、ADR-0065 |
| 5 | 同一 plugin 声明了多个互斥 tier / layer / kind 组合 | warning | error | ADR-0110 D4 |
| 6 | 子 Agent 的 capability grant ⊄ 父 Agent grant 违反 | error | error | ADR-0066、C5 |

## 入口

```
uv run lca plugin check [<profile>]
uv run lca plugin check --strict [<profile>]
```

输出按段报告，不再用旧的「LogicAddress 6 维 75 / 100」分制。

## 历史与权威

- ADR-0069 §二 LogicAddress 6 维评分（已被本矩阵覆盖）
- ADR-0074 「软 / 硬」分类散落在多处设计文档
- ADR-0109 D1「4 元素 100% 强制」为第 1 行的源头
- ADR-0110 D8「硬软门禁单一矩阵」是本文件的成因

## 维护

- 任何新增 plugin 检查（capability / lifecycle / observability 等）必须先填本表再实现 lint；
- 任何删去旧检查也必须先在本表移除对应行；
- 表格是 6 行不是 50 行——发现超过 6 行说明检查本身该收敛到 PluginContract 一段。
