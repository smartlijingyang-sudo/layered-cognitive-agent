# JournalRecord v2 Schema — ADR-0065 §三

## 信封字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `schema` | `"lca.journal/2"` | ✓ | L4 fail-fast 校验入口 |
| `event_id` | ULID | ✓ | L3 全局唯一稳定句柄 |
| `run_id` | ULID | ✓ | 所属 run 身份 |
| `run_seq` | int | ✓ | L1/L3 严格连续 |
| `occurred_at` | float (s) | ✓ | 事件源时钟 |
| `committed_at` | float (s) | ✓ | 账本接受时钟(L2 提交先于观察) |
| `scope` | RunScope | ✓ | 关联骨架 |
| `causation` | Causation | ✓ | 直接因果 + 非树形 links |
| `descriptor` | DescriptorRef | ✓ | L4 描述符引用 |
| `data` | dict | ✓ | 类型化 payload 规范化序列化 |
| `evidence` | tuple[EvidenceRef, ...] | ✓ | 受治理证据引用(L5 / §四) |

## 不变量

- `schema == "lca.journal/2"` 必填
- `event_id` 全局唯一(ULID 生成于 `lca/contracts/atoms/ids.py`)
- `(run_id, run_seq)` 严格连续 1..N;无重复无缺
- `occurred_at <= committed_at`(可能相等,允许本地延迟)
- `descriptor.version >= 1`;`payload_schema_version` 与登记匹配
- `evidence` 可空但 typed

## 迁移

`scripts/migrate_journal_v1_to_v2.py <input.jsonl> <output.jsonl> [--in-place]`

- v1 → v2:补 `schema` / `event_id` / `run_seq` / `occurred_at = committed_at = ts` / `causation` / `descriptor`
- v2 原样透传
- 未知 schema 警告并原样透传
- 退出码:0 成功 / 1 错误 / 2 已是 v2