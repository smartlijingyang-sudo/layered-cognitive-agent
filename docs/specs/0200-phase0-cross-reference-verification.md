# ADR-0200 Phase 0 — Cross-Reference Verification (0187/0189/0169/0197)

> **Status**: Completed (2026-09-08). Per [ADR-0200](../adr/0200-hermes-product-capabilities-absorption.md) §7 Phase 0 exit criteria.
> **Scope**: Verify cross-references to 0187 / 0189 / 0169 / 0197 and confirm 0200 does not preempt 0187 P0-P2.

---

## 0. Verification table

| ADR | Filesystem path | Status | Cross-reference in 0200 | Correctness |
|---|---|---|---|---|
| 0187 | `docs/adr/0187-assistant-agent.md` | Accepted (2026-09-04; PR-2..8 in progress) | §2.1, §2.2, §3.1, §3.2, §5.3, §7, §10 | ✅ Verified |
| 0189 | `docs/adr/adr-0190-extreme-plugin-organization.md` | local Keep (filesystem = 0190; self-labeled 0189) | §2.1, §5.3 | ✅ Verified (filesystem has 0190 filename; ADR-0200 uses 0189 label — documented in [semantic reference](hermes-lca-semantic-reference.md)) |
| 0169 | `docs/adr/0169-loop-cursor-control.md` | Accepted (2026-09-02; §D7 I-MV1 superseded by 0185; gate-as-phase revised by 0194) | §1.2, §2.1, §3.1, §3.2, §4.3 | ✅ Verified |
| 0197 | `docs/adr/0197-guard-stack-hermes-dsh-convergence.md` | Accepted (2026-09-06) | §2.1, §2.2, §3.1 | ✅ Verified |

---

## 1. 0187 PR plan alignment

ADR-0187 §7 lists PR-1 (ADR 合入) + PR-2…PR-8 as the implementation sequence. 0200 Phase 1+ PRs depend on:

| 0187 PR | Content | 0200 dependency |
|---|---|---|
| PR-2 | contracts: AssistantSpec / Catalog Protocol / capability keys / EP descriptors | Phase 1 (review-fork needs Home SSOT types) |
| PR-3 | `assistant.catalog` + Home layout + create/get/list | Phase 1 (fork writes to Home) |
| PR-4 | bootstrap injection + workspace binding + `web-assistant` profile | Phase 1 (isolation for experiment sessions) |
| PR-5 | gateway `/assistants` + session/run `assistant_id` | Phase 1 (session binding for fork audit) |
| PR-6 | skill_overlay + install from URL (0048 + 0067) | Phase 1 (SkillAcquirer proposal path needs overlay) |
| PR-7 | create-assistant skill + BOOTSTRAP flow | Phase 2+ (Curator needs skills indexed) |
| PR-8 | evolve (experiment only) + jobs register/manual fire (0093) | Phase 2 (Curator lifecycle), Phase 4 (MemoryProvider) |

0200 Phase mapping:
- **Phase 1** (0200.1 review-fork × SkillAcquirer × 0067): requires PR-2..PR-6
- **Phase 2** (0200.2 Curator lifecycle): requires PR-3 + PR-6
- **Phase 3** (0200.3 ContextEngine): requires PR-2 (for compression audit surface)
- **Phase 4** (0200.4 MemoryProvider): requires PR-2 (Home MEMORY/USER as file SSOT)
- **Phase 5** (0200.5 toolset + check_fn): requires Manifest stability (0189 Phase A)
- **Phase 6** (0200.6 no_agent Routine): requires 0093 stable + PR-8 jobs

**Verification**: As of 2026-09-08, 0187 PR-2..PR-8 are in progress (PR-1 accepted). 0200 Phase 1 is gated on 0187 completion. No 0200.x code PR has been started.

---

## 2. Non-preemption confirmation

Per ADR-0200 §7 Phase 0 exit criteria:
> 确认不与 0187 P0-P2 抢跑

| Check | Status | Evidence |
|---|---|---|
| 0200 Phase 0 (docs only, no code) | ✅ DONE | git log shows only docs commits: `6898124a` (ADR-0200 Phase 0 + semantic reference) |
| 0200 Phase 1+ PRs NOT started | ✅ Confirmed | No commits matching `0200-P1` / `0200.1` / `review-fork` in git log; implementation plan §0 explicitly states "Blocked on ADR-0187 P0→P2" |
| 0200 PR naming uses `0200-Px-yy` namespace | ✅ Confirmed | Implementation plan §3 uses `0200-P1-01` .. `0200-P1-06` — no confusion with 0187 PR numbering |
| 0200 does NOT modify 0187 ADR or 0187 PR artifacts | ✅ Confirmed | 0200 only references 0187; no `git diff` changes to `docs/adr/0187-assistant-agent.md` |
| No `HermesLikeAgent` / parallel CognitiveRuntime | ✅ Confirmed | git log grep for `hermes` shows only ADR docs (0199/0200) + ADR-0197 guard-stack; no code implementing Hermes concepts |

---

## 3. Cross-reference integrity

Each 0200 reference to an ADR has been verified to:
1. Reference the correct filesystem path
2. Reference the correct section / invariant
3. Use the ADR's actual status (not an aspirational status)

### 3.1 ADR-0187 references

| 0200 § | Reference | 0187 actual content | Verified |
|---|---|---|---|
| §2 table row "Assistant 产品面" | "0187 Accepted: Home 盘 SSOT, AssistantSpec, 无新 loop" | Status=Accepted; D2=AssistantHome; D3=AssistantSpec; P2=不新开 loop | ✅ |
| §2.1 main 缝实况补丁 | "main = 0187 Accepted; 0178 作废号" | 0187 status=Accepted; 修订记录 confirms 0187 numbering after 0178 conflict | ✅ |
| §2.1 | "0187 PR-2…8 仍在路上" | §7 lists PR-2..PR-8 | ✅ |
| §2.1 | "0187 设计默认 write_approval off" | §D9 "默认写门关闭...默认不落盘到 skills/" | ✅ |
| §2.2 | "0187 D11 Skills progressive disclosure" | §D11 "技能渐进披露（先 name+description，匹配再 activate 全文）" | ✅ |
| §2.2 | "0187 Home" for HERMES_HOME isolation | §D2 AssistantHome directory | ✅ |
| §3.1 | "0187 Accepted: Home + AssistantSpec + 无新 loop" | Matches §D2/D3/P2 | ✅ |
| §7 Phase 0 | "0187/0189/0169/0197 交叉引用正确" | This document | ✅ |

### 3.2 ADR-0189/0190 references

| 0200 § | Reference | 0189/0190 actual content | Verified |
|---|---|---|---|
| §2 table row "包边界" | "0189: Def/Prov/Cons" | §0.1 Keep: "Definition / Provider / Consumer"; §3.1 逻辑单元 | ✅ |
| §2.1 | "0189: local Keep; Phase B=skill; 勿占 0187 号" | §0 header "0189 Proposed（0187=AssistantAgent 已占用）"; §6 "Phase B = skill" | ✅ |
| §2.2 | "0189 膨胀红线" | §0.1 "膨胀红线：单包出现第二 seam" | ✅ |
| §4.4 | "0189 ROLE 注解与 CI warn" | §3.2 Phase A "每个插件内标注角色边界（ROLE 注解）" | ✅ |
| §5.3 | "0189 Phase 对齐: Phase A/Phase B" | §3.2 Phase A (门禁) / Phase B (skill 竖切) | ✅ |

**0189/0190 filesystem discrepancy**: The document self-labels as ADR-0189 (`ADR-0189 Proposed（0187=AssistantAgent 已占用）`), but the filesystem filename is `adr-0190-extreme-plugin-organization.md`. ADR-0189 exists as a separate file (`0189-session-obs-dsh-parity-events.md`) covering session observability DSH parity. This discrepancy is documented in the [Hermes↔LCA semantic reference](hermes-lca-semantic-reference.md) line 37: `0190 (local 0189)` and line 83: `ADR-0190 Extreme plugin organization (local 0189; cited as "0189" by ADR-0200 §2.1)`. ADR-0200 consistently uses the label "0189" when referring to extreme plugin organization concepts, matching the document's own self-identification.

### 3.3 ADR-0169 references

| 0200 § | Reference | 0169 actual content | Verified |
|---|---|---|---|
| §1.2 runtime skeleton | "0169 Accepted 五缝; 0194 收敛" | Status=Accepted; D8=五缝架构图 (LoopCursor/ProjectionHost/PersistenceCoordinator/ModelVisibleCapture/CloseBarrier) | ✅ |
| §2.1 | "0169 Accepted（五缝）; 0194 认知循环收敛" | D1-D8 五缝; gate-as-phase revised by 0194 | ✅ |
| §2 table row "循环与投影" | "0169 Accepted (LoopCursor·ProjectionHost·Persistence·Capture·CloseBarrier); 0194 收敛" | D8 五缝架构图 exactly matches | ✅ |
| §3.2 | "0167/0169; 可回放" for message-list compression | 0169 D10 `writable.matrix.default.storage` single-writer; replay via `CursorSnapshot` | ✅ |
| §4.3 | ProjectionHost / ContextAssembly Provider | D8 ProjectionHost as seam for derivers | ✅ |

### 3.4 ADR-0197 references

| 0200 § | Reference | 0197 actual content | Verified |
|---|---|---|---|
| §2.1 | "0197 Accepted: Hermes ladder + DSH act guards 已编入 GateService/ToolGuard/LoopGuard/Convergence — 禁止平行 Guard 框架" | Status=Accepted; §0 table: GateService(slot=loop), ConvergencePolicy, ToolGuardService; §2 capability table | ✅ |
| §2.2 | "Footprint Ladder → 0189 膨胀红线" | Not 0197 (0189 reference here); correct — Footprint Ladder maps to 0189 expansion red-line | ✅ |
| §3.1 | "已在 0197 Accepted — 复用 GateService/ToolGuard/LoopGuard; 禁止再造平行 Guard 栈" | §0 decision table + §2 capability table match exactly | ✅ |
| §3.3 Reject #7 | "平行 Guard / ToolSafety 框架（0197 已吸收 Hermes+DSH）" | §0 title "Guard Stack：Hermes 分层收敛 + DSH Guard 插件化融合" | ✅ |

---

## 4. File existence verification

| ADR | Expected path | Exists | `ls` result |
|---|---|---|---|
| 0187 | `docs/adr/0187-assistant-agent.md` | ✅ | Confirmed |
| 0189/0190 | `docs/adr/adr-0190-extreme-plugin-organization.md` | ✅ | Confirmed (filename discrepancy documented in §3.2) |
| 0169 | `docs/adr/0169-loop-cursor-control.md` | ✅ | Confirmed |
| 0197 | `docs/adr/0197-guard-stack-hermes-dsh-convergence.md` | ✅ | Confirmed |

---

## 5. Next steps

When 0187 PR-2..PR-6 complete:
1. Update §1 "0187 PR plan alignment" with completion status
2. Mark "0187 completion" as DONE in §2
3. Begin 0200 Phase 1 PRs (0200-P1-01 first: `ReviewForkSpec + ArtifactProposal`)

---

## 6. Cross-references

- [ADR-0200](../adr/0200-hermes-product-capabilities-absorption.md) §7 Phase 0
- [ADR-0187](../adr/0187-assistant-agent.md) §7 PR plan
- [ADR-0190](../adr/adr-0190-extreme-plugin-organization.md) — filesystem 0189 label
- [ADR-0169](../adr/0169-loop-cursor-control.md) — five seams
- [ADR-0197](../adr/0197-guard-stack-hermes-dsh-convergence.md) — Guard stack
- [0200 implementation plan](0200-implementation-plan.md) — Phase 0..6 PR plan
- [Hermes↔LCA semantic reference](hermes-lca-semantic-reference.md) — Keep/Transform/Reject matrix
