# Transport wire — DTO adapters

> ADR-0195 §2.4 Adapter pattern

## 1. 职责

Maps HTTP/CLI payloads ↔ `lca/contracts` types.

## 2. 不负责

No business rules, no routing, no Session/Journal access.

## 7. 副作用

无：只做 DTO ↔ DTO 转换与序列化，不写文件、不发事件、不改状态。wire DTO 的字段约束由 `lca/contracts` 一侧的 Pydantic 模型定义，本包不复制规则。

| Source (legacy) | Target |
|---|---|
| `handlers/runs/wire/` | `wire/runs/` (P3-11) |
| route request bodies | contract DTOs |

Skeleton only until P3-11 consolidation.
