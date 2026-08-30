# ADR-0097: Event Identity 派生策略 —— ULID（与 ADR-0065 注释一致）

> **Superseded by ADR-0099 / 2026-08-29**

## 状态

**Accepted — 2026-08-28**

## 背景

ADR-0096 MVA-2 要求 RunStore.append 闭环填 event_id，且派生函数不接 float ts。
ADR-0096 §6.3 提议 `sha256(run_id, seq, event_type)`；但 `lca/contracts/models/observability/journal.py:804`
注释声明 event_id 是 ULID。两条路径都满足 ADR-0096 §I3（不接 float ts）。

## 决策

`event_id` 用 **ULID**（26 字符 Crockford Base32）派生。ULID 自带 ms 级单调时间戳（不接调用方传入的 ts），与 `(run_id, seq, event_type)` 一并保证全局唯一 + 时间排序。

| 方案 | 否决原因 |
|---|---|
| `sha256(run_id, seq, event_type)`（与 ADR-0096 §6.3 一致） | 与既有注释不一致；失去时间排序能力；跨进程不可预计算 |
| `UUIDv4` | 无序；浪费排序能力 |
| `UUIDv7` | 与 ULID 等价但不如 ULID 紧凑（26 字符 vs 36 字符） |

## 后果

- 新增 `ulid-py` 依赖（`pyproject.toml`）。
- MVA-2 Task 3 实现 `StableUlidIdentity.derive(run_id, seq, event_type) -> str`，签名不接 `ts` / `occurred_at` 参数（I3 不变量）。
- 同 `(run_id, seq, event_type)` 跨进程/跨 replay 产同 ULID（ULID 的随机分量用 monotonic 替代运行期 ts）。
- 事件流按 ULID 排序天然有序，对审计/重建有利。

## 验证约束

- `lca/plugins/providers/event_identity/` 不得使用 `datetime.now()` / `time.time()` 等 float ts 派生函数。
- `RunStore.append` 构造 `StampedEvent` 时 `event_id` 必填非空。
- ULID 格式校验：`^[0-9A-HJKMNP-TV-Z]{26}$`。

## 关联

- 上游：ADR-0096 §I3（构造时闭环派生，不接 float ts）+ ADR-0065 §三（event_id 全局唯一）。
- 不重开 ADR-0096 §6.3 的 sha256 提案；本文是后续修订（MVA-2 启动时追加）。
- 后续：MVA-2 Task 3 实施 ULID provider；MVA-2 Task 4 改造 RunStore.append。
