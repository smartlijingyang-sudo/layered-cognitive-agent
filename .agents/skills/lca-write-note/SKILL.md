---
name: lca-write-note
description: Use when writing, drafting, reviewing, or promoting a new Agent Note in docs/notes/; picks the right class (contract/primitive/seam/profile/runbook/postmortem) vs docs/adr/, applies the three-line header, fills the lifecycle-appropriate body skeleton, forces Alternatives considered, and rewrites proposed/ → implemented/ in the same PR. Trigger phrases: "写一条 note", "新 Agent Note", "提案落 docs/notes/", "升 implemented", "Promote this note".
---

# Writing an LCA Agent Note

A new LCA decision lands in `docs/notes/` only when it does not change other ADRs' boundaries; otherwise it goes to `docs/adr/` and follows the existing ADR workflow. This skill is guidance, not a checklist. Use the file-system to record the decision; use this skill to pick the right class, header, and body, then re-read the result against [docs/notes/README.md](../../../docs/notes/README.md), the active lifecycle [AGENTS.md](../../../docs/notes/proposed/AGENTS.md), and (after step 3 lands) `scripts/check_notes_tree.py`.

## Decide where the decision lives

The single discriminating question comes from [docs/notes/README.md §1](../../../docs/notes/README.md): **does the decision change other ADRs' boundaries?** Run the question against the four pillars — five-layer dependency direction, cognitive closed set, Journal catalog, Profile topology, env whitelist — before reading any code.

- **Yes** → write / extend an ADR under `docs/adr/` (existing workflow). Do not also file a Note.
- **No** → file a Note under `docs/notes/{lifecycle}/{class}/YYYY-MM-DD-<topic>.md`.

老 ADR (`docs/adr/` 内既有编号) 一律不动;Notes 体系只承接本 README 发布之后的新决策,任何"瘦身 / 合并 / 替代"动作视为范围外。

## Pick the class

`class` is a closed set; pick one that fits the smallest enclosing subject. The matrix in [docs/notes/README.md §2.2](../../../docs/notes/README.md) is authoritative; expand only with a new entry in both README and `scripts/check_notes_tree.py`.

| Class | Use when the decision pins one of these |
|---|---|
| `contract` | Protocol、枚举、ID、wire 字段(单点契约) |
| `primitive` | 认知 / Body / Phase 原语;非跨 ADR 但影响闭集 |
| `seam` | 一条 Seam(llm / tools / sandbox / state_store / memory ...)的边界 |
| `profile` | Profile YAML 的拓扑与启动契约 |
| `runbook` | 跨 seam / 跨 Profile 的运行模式决策(与 [`docs/debug/run-debug-guide.md`](../../../docs/debug/run-debug-guide.md) 互补) |
| `postmortem` | Incident 复盘;链接 `docs/design/` 中的事后分析,不复制内容 |

Anything that is purely an implementation detail, a temporary fix, or only swaps an implementation without touching a contract — stop, that goes to git commit + test, not Notes.

## Header three-line format

Hard-constraint per [docs/notes/README.md §3.1](../../../docs/notes/README.md):

```markdown
# Agent Note: <title>

Status: <proposed|implemented|rejected>
```

`Status:` value must equal the physical lifecycle directory. `rejected` may carry a one-line reason inline: `Status: rejected — <one-line reason>`. `archived/` is a path-level state, never a `Status:` value; archived notes get an extra `Archived: YYYY-MM-DD` line.

## Body skeleton by lifecycle

Every note opens with `## Problem` — motivation only, no implementation words ("we will add X" is forbidden in Problem; it lives in Proposal or Decision). Subsequent sections differ by lifecycle.

- **`proposed/`** — `## Proposal` (将来时) / `## Alternatives considered` / `## Acceptance criteria` (可观察的状态,不是 checklist) / `## Risks`
- **`implemented/`** — `## Decision` (现在时,描述真实状态) / `## Alternatives considered` / `## Consequences`(或保留 `## Verification` / `## Testing`,描述现状不写计划)
- **`rejected/`** — `## Proposal` / `## Alternatives considered`(verdict 已在 `Status:` 行)
- **`archived/`** — 沿冻结前格式,加一行 `Archived: YYYY-MM-DD`

Cross-note references use relative markdown links (`[xxx](../../../implemented/contract/...)`), never bare numbers. Filename date is the earliest proposing commit, estimated by `git log --diff-filter=A --follow --format='%ai' -- docs/adr/<类似 ADR>` per the local [`AGENTS.md`](../../../docs/notes/proposed/AGENTS.md); fall back to the working day in the PR.

## Alternatives considered — the load-bearing section

`## Alternatives considered` is mandatory. A note without it has not recorded "why not Y", which is an open invitation for the next reader to re-propose Y. Each rejected option gets either a bold-led paragraph or a `### Why not <X>?` sub-section; the rejection is one factual clause per option:

- the alternative named in one sentence;
- why it loses against the chosen option (one or two sentences, factual);
- the cost it would have imposed (one sentence), so a future reader can tell if the trade still applies.

A good Alternatives section names 2–4 options, including the "do nothing" baseline; it does not list strawmen, does not editorialize, and does not duplicate the Decision body.

## Promoting proposed → implemented

Implementation is the rewrite. In the **same PR** as the code change ([`AGENTS.md` §升到 implemented](../../../docs/notes/proposed/AGENTS.md)):

1. Move `proposed/<class>/...md` → `implemented/<class>/...md` (preserve the date slug).
2. Change `Status: proposed` → `Status: implemented`.
3. Rewrite `## Proposal` (将来时) into `## Decision` (现在时,描述真实状态);drop planning checklist residue per the prose standard.
4. Fold `## Acceptance criteria` / `## Risks` into `## Consequences` or keep them as `## Verification` / `## Testing` (present tense, evidence-based).
5. Move or add the `.zh.md` sidecar if the pair exists; do not pre-generate one that the project does not need.
6. Run the local sanity check (step 3 will wire `scripts/check_notes_tree.py` into `verify-all`; until then it is manual).

No "lift-and-edit" — the rewrite is the point. A reader who lands on the implemented note must see the shipped reality, not the proposal frozen in time.

## Worked example (one paragraph each, not full notes)

**`contract`** (`implemented/`). A new enum value on `ActionType` adds `ASK_HUMAN` so the Body can request human input. Decision: register the value in `lca/contracts/protocols/action_type.py`, extend the wire serializer in `wire/`, and bump the schema minor version. Alternatives considered: (a) overload `DELEGATE` with a sub-kind — rejected because C7 separates Command / Approval / Policy and ASK_HUMAN has different ownership. (b) introduce a parallel `HumanAction` enum — rejected, double vocabulary invites drift. Consequences: every Profile that uses `ActionType` must regenerate the wire map; Journal now records `action.ask_human` and downstream Reasoner needs a one-line consumer update.

**`primitive`** (`proposed/`). A new phase primitive `phase.recover.checkpoint` lets the Interpreter verify a Checkpoint before resuming, preventing stale Reducer snapshots from poisoning the next loop. Problem: today the loop resumes from `PhaseRunCursor` directly, with no contract that the checkpoint's Reducer snapshot matches the cursor's. Proposal: insert a one-step gate phase that runs `Checkpoint.snapshot_match(cursor)` before the next phase fires; on mismatch, raise `CheckpointMismatch` and the Interpreter halts with a Reducer-applied failure event. Acceptance criteria: a unit test replays a tampered checkpoint and asserts the Interpreter halts; a runbook note links the recovery path. Risks: extra phase means one more event per resume — acceptable, the check is cheap and the alternative (silent resume) is worse.

**`runbook`** (`implemented/`). Decision: when a Brain returns `ActionType.STOP` with a non-empty `Reason`, the Kernel emits `journal.brain.stop_intent` and a `Reducer` clears `AgentState.active_loop` in the same transaction; downstream Body code reads the cleared state and refuses to fire tools. Alternatives considered: (a) let Body check the intent directly — rejected, breaks C4 (Body reads State via Reducer). (b) emit two separate events and let downstream subscribe — rejected, race window where a Body fires between the intent and the clear. Verification: integration test drives the Brain into `STOP` with `Reason="tool_budget_exceeded"` and asserts the Journal shows intent + clear in the same tick.

## Commands / 调用方式

Promote 至 `implemented/` 后,用 `lca-ops notes-check` 复跑一遍(内部调 `scripts/check_notes_tree.py`),确认 `Status:` ↔ 路径、`class` 闭集、archived 冻结规则都没被这次迁移打断。Agent 优先走 wrapper,CI / ad-hoc 调试才直接调裸脚本。