# ADR-0074 Plugin-Everything 实施追踪

## ADR 监督范围：5 个 ADR × 所有条款

| ADR | 关系 | 整体状态 | 落地入口（PR 序列） |
|---|---|:-:|---|
| **ADR-0066** | Refined | ⛔ | PR-1 |
| **ADR-0074** | 自身 | ⏳ | PR-0..PR-12 |

### 实施矩阵（ADR § × clause → 交付 PR）

| ADR § | clause 描述 | 状态 | 交付 PR | 备注 |
|:-:|---|:-:|:-:|---|
| **0066 §二** | 9 Control Slot 枚举 | ⛔ | PR-1 | — |
| **0074 实施序列** | PR-0..PR-12 | ⏳ | 详见 §1 | — |

## 1. 状态总览

| Phase | PR | 标题 | 状态 | Commit | 完成日 | 阻塞 |
|:-:|:-:|---|:-:|---|:-:|---|
| **0** | A | v3.1 patch | ✅ Done | `f980ace0` | 2026-08-21 | — |
| **1** | 0 | audit | ✅ Done | `8f8469eb` | 2026-08-21 | — |
| **1** | 1 | next | ⛔ Blocked | — | — | PR-0 |

**Next Action**：PR-1（next PR to work on）.

## 7. 已知陷阱

当前 tracker 只记录 ADR-0074 的基线监督条目；Hermes 能力的独立实现进度由 `docs/plans/hermes-progress.md` 维护，并通过独立提交与测试验证。
