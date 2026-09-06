# ADR-0200 完整 PR 实施计划

> **状态：** Draft — **Blocked on [ADR-0187](../adr/0187-assistant-agent.md) P0→P2**（Home / isolation / progressive skills）
> **权威：** [ADR-0200](../adr/0200-hermes-product-capabilities-absorption.md)
> **平台机制：** 必须先完成 [0199-implementation-plan.md](0199-implementation-plan.md) P1（RuntimeFacade）

---

## 0. 启动条件（Gate）

| 条件 | 验证 |
|---|---|
| ADR-0199 P1 合并 | `pytest tests/architecture/test_0199_phase1_acceptance.py -q` exit 0 |
| 0187 PR-2…6 落地 | Home SSOT + skill progressive disclosure |
| 0187 P1 routines | 0093 register + manual fire |
| 无第二 Runtime | grep `HermesLikeAgent` / 平行 CognitiveRuntime → 0 |

**未满足前：** 只允许 0200 Phase 0 文档 PR；禁止 product Provider 代码。

---

## 1. 总览（0187 达标后展开）

| Phase | Follow-up | PR 数（估） | 主题 |
|---|---|---|---|
| P0 | — | 2 | 语义对照表 + 0187 对齐确认 |
| P1 | 0200.1 | 6 | review-fork × SkillAcquirer × 0067 |
| P2 | 0200.2 | 4 | Curator Provider 生命周期 |
| P3 | 0200.3 | 5 | ContextEngine → ProjectionHost 槽 |
| P4 | 0200.4 | 4 | MemoryProvider 旁路 |
| P5 | 0200.5 | 4 | toolset + check_fn 谓词 |
| P6 | 0200.6 | 4 | 0093 no_agent Routine |

**并行：** P2 与 P3 可并行（共享 Projection 纪律）；P4 依赖 P1；P6 依赖 0093 稳定。

---

## 2. Coding Agent 契约（继承 0199）

- 必读：[AGENTS.md](../../AGENTS.md)、[ADR-0200](../adr/0200-hermes-product-capabilities-absorption.md)、[0199-implementation-plan.md](0199-implementation-plan.md) §1
- **额外禁止：** review-fork 写主 Spine；ContextEngine 有损摘要回写事实；无闸 skill 落盘
- 每个 PR 必须证明 **One Spine / One Home / One Scheduler**（0200 §6 不变量）

---

## 3. Phase 1 预览 — 0200.1 review-fork（待 0187 后细化）

| PR-ID | 标题 | Read First | 交付 | 验证 |
|---|---|---|---|---|
| 0200-P1-01 | feat(contracts): ReviewForkSpec + ArtifactProposal | 0067 Artifact；0187 evolve | `contracts/assistant/review_fork.py` | unit |
| 0200-P1-02 | feat(cognition): fork 只读主 Spine 快照 | `session/fold`；0167 | fork reader port | integration |
| 0200-P1-03 | feat(application): experiment session 旁路 | 0187 isolation | worker spawn **不**写主 session | e2e |
| 0200-P1-04 | feat(assistant): SkillAcquirer 提案路径 | 0048；0067 gate | acquirer → 0067 | unit |
| 0200-P1-05 | test(arch): 主会话零写入 invariant | — | CI grep + replay | arch |
| 0200-P1-06 | docs(obs): fork 审计 EP | 0167 | event catalog | verify catalog |

> 完整 29 PR 清单在 0187 P0 验收后由 maintainer 补全本文件 §4–§9（格式同 0199 §4）。

---

## 4. 维护

- 本文件在 **0187 P0 完成** 后展开为与 [0199-implementation-plan.md](0199-implementation-plan.md) 同粒度
- 不得将 0200 PR 混入 0199 分支命名（branch 用 `adr0200/`）
