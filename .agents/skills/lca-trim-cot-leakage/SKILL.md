---
name: lca-trim-cot-leakage
description: Use when auditing or fixing prose that reads like a leaked reasoning transcript — change narration ("曾退役", "合并心智", "新规则生效后"), stack vantage ("本批 PR", "上一步提交"), uncommitted-draft citations (decision N / audit item / unnumbered §N), reviewer-addressed justifications, control-flow narration, or hedged planning residue in prose comments, docstrings, docs, or Agent Notes. Trigger phrases: "tracing 漏水", "leak reasoning", "strip cot", "audit residue".
---

# Trimming Chain-of-Thought Leakage in LCA

Chain-of-thought leakage is prose whose vantage is the authoring session rather than the repository: it cites artifacts only that session could see, narrates the change instead of the state, or argues with a reviewer who has left. The fix is never deletion alone when a passage carries factual clauses — restate each so it stands at HEAD, then delete the transcript around it; a passage carrying none (an audit code, control-flow narration) is deleted outright. It is guidance, not a script — judgement decides what survives.

**REQUIRED BACKGROUND:** [lca-prose-standard](../lca-prose-standard/SKILL.md) owns the complete-proposition rule this skill applies. [docs/notes/README.md §3.1](../../../../docs/notes/README.md) is the format contract every Agent Note must obey. 老 ADR (`docs/adr/`) 永远不动,既不在审计范围内也不在修复范围内。

## The one test

For every suspect passage ask: **could a reader at HEAD, with no access to any session transcript, PR thread, or uncommitted draft, resolve every reference and verify every claim?** If no, restate the surviving facts from the repository's vantage and delete the rest. If yes, it is not leakage, however historical it sounds — but resolvability only clears this skill's bar: on current-state surfaces (READMEs, Agent Notes, JSDoc) a resolvable change story is still change narration and is routed to the right sanctioned home.

## LCA-specific leakage shapes

These appear in LCA prose more often than the generic patterns. Detect and rewrite each:

1. **ADR 编号引用当段落挂件** — `ADR-0169 §背景段说了 X`, `参见 ADR-0169 中 T4 阶段那段`. ADR § 是它自己的产物编号引用,可以挂在 prose 里但前提是引用本身就是事实陈述;**编号 + 「中/那段」+ 间接转述** 几乎都是泄漏,直接陈述 ADR §里的状态。
2. **审查残留物** — `audit item C2`, `(decision 7)`, `phase label W3`, `T4 通过后我们才...`. 闭集检查项在审计报告 [`docs/notes/audit-2026-09-03.md`](../../../../docs/notes/audit-2026-09-03.md) 里有 owner;prose 引用它们是泄漏,引用 owner 才是事实。
3. **批量合并叙述** — `本批 PR-7 之后`, `下一步 PR`, `此 PR 添加了`, `上一批...`. LCA 的批次是治理概念不是 prose 公民 — 描述当前机制或扩展点,迁移工作进 issue 链接。
4. **superpowers / 老 plugin 残留引用** — `superpowers 那边的做法是...`, `原本 cordis 的 ...`. vendored 的 Cordis / Cosmokit 是 LCA 的依赖不假,但 prose 里把"原始库曾经 X"当作正当性,等于在参考仓库外找证据。
5. **闭集列举后接 hedge** — `闭集初值(后续可能扩充)`, `本批次不启用 ...(后续启用)`. 「后续」是无承诺的规划遗留,要么进 TODO/ADR,要么删除。
7. **「合并心态」与「瘦身」自描述** — `本次合并是 ...`, `note 体系瘦身 ...`. AGENTS.md §1 已声明"任何瘦身 / 合并 / 替代动作视为范围外";Agent Note 自称在做这件事等于宣布越权。
8. **中英 working-language 滑移** — 在中文 prose 里出现未翻译的英语段落(`---- 私有 ----`、端、设计稿),或反向。译或删。

## What is not leakage (keep rules)

Apply these keep rules as written; deleting durable references and keeping dead ones both fail:

- **ADR 编号引用** — `ADR-0119`, `ADR-0112 followup` resolve at HEAD (note: 老 ADR 一律不动,这是引用规则不是修改规则);保留在任何表面,包括 README。
- **已合 PR 引用与 issue 引用** — `#1470`, `TODO(name):`, `issue #N owns the follow-up` 在 HEAD 可解析,保留,不必迁到 Agent Notes。
- **GitHub PR / commit 引用** — `commit abc1234`, `PR #N` 是仓库里 grep 可达的客观锚点;只在变更叙述里才删除(改成"扩展点"或具体机制名)。
- **suppression 理由** — `# noqa: E501 -- 单一长 URL 不能折行`,coverage-ignore 理由,空 except 解释;修正错误理由,绝不能删理由。
- **Counterfactual-present 回归桩** — `without K8 HMR, dispose 期间会...`, `naive Reducer 直接改 state 会...`,是当前契约的反事实锚点。
- **measured bounds** — `(measured: 50 runs, p95 12ms)` 为常数定标;`measured` 是承重词。
- **运行时 old/new 状态** — `lifecycle 上旧 connection 在新 connection 接受前 drain` 是运行时生命周期,不是变更史。
- **note change-story 段内的历史阶段名** — `note 第一稿提出 X` 在 implemented/ 的 Decision 段允许;indexical stamps (`this cut`, `此版`) 全部地方禁。
- **外部 / 标准引用** — RFC 9110 §10.1.5、外部 vendor doc;§禁针对的是仓库内未 commit 的草稿,不是外部 §-numbering。
- **项目声音 / 文体形式** — Agent Note 的 Alternatives-considered 段是强制骨架,保留。

## Workflow

1. Scope and exclusions per [lca-prose-standard](../lca-prose-standard/SKILL.md): require an explicit scope; never touch `docs/adr/` (historical record, frozen), `docs/notes/archived/` (frozen), or `vendor/` (third-party code). Recorded fixtures and snapshots are derivatives, not prose targets: change the owning source or scenario and regenerate them only when an authorized behavior change requires new evidence.
2. Run [scripts/verify_doc_slop.py](../../../../scripts/verify_doc_slop.py) read-only first against the scoped prose. The script flags `previously` / `used to` / `no longer` / `now (contrastive)` / `this PR` / `decision N` / `§N of` / `the old` / `曾经` / `退役` / `在 PR #N` and 7-char hashes — calibrate each pattern against a known positive and a near-miss negative before trusting its output. Patterns are probes, not the definition: each review round of a real purge finds cases the script missed, so also read the densest prose in scope (module docstrings, ADJACENT skill files, root AGENTS.md sections, doc/notes/ headers) without a pattern in hand.
3. Fix owner-first per surface: generated catalogs (e.g. wire schemas, Journal event catalogs, Profile capability maps) → trace every consumer, fix the source JSDoc or generator template, then regenerate all derivatives; bilingual prose → update the counterpart minimally (Note: LCA does **not** enforce `.zh.md` sidecars — only add one if a paired doc already exists); code comments / JSDoc → restate the surviving invariant, never delete the comment to hide a missing invariant.
4. Before deleting anything, enumerate the passage's propositions (prose-standard) and check the overcorrection traps: trims that flip an obligation into an endorsement, promote a hypothetical to a shipped feature, delete a true fact, drop provenance, or silently break a contract change's downstream consumer (`contracts` change → consumers + tests, see AGENTS.md §1 契约改动必须闭环).
5. Verify: re-run [scripts/verify_doc_slop.py](../../../../scripts/verify_doc_slop.py) expecting only sanctioned keeps, this skill's directory, and any explicitly cited evidence; confirm every remaining citation resolves at HEAD; run the relevant local gates for touched surfaces (`uv run ruff check --fix <changed-path>` + `uv run pytest --no-cov <related-tests>` for code paths; `python scripts/verify_md_links.py` for link-bearing docs; `python scripts/verify_doc_budgets.py` for sized docs).

## LCA patterns to flag in particular

These five patterns recur in real LCA purge rounds; treat them as high-priority probes:

- Any sentence of the form "本批 PR-N 之后 …" / "this PR adds" — the batch is governance, the prose should describe the shipped mechanism.
- Any reference of the form "ADR-NNNN §<段名>" that is followed by an indirect paraphrase — the paraphrase is the leakage, the ADR § is the owner.
- Any "曾 / 退役 / 不再 / 过去 ... 现在 ..." structure in `docs/notes/` headers or prose — note body should describe present tense state, not the journey.
- Any "(audit item X)" or "(decision N)" inline — these are session artifacts; if the underlying constraint matters, cite the ADR / spec / invariant by name.
- Any "TODO/待办/后续" without a concrete follow-up — promote to an issue reference or delete; see AGENTS.md §1 "兼容路径模板必须填满".

## What this skill explicitly does not own

- **Removing old ADRs** — see AGENTS.md §1 「老 ADR 全部不动」. This skill flags, archives, or rewrites `docs/notes/` and current-state prose only.
- **Changing the contract / wire / Schema without consumer alignment** — a CoT-leak fix that drops a contract field still needs the AGENTS.md §1 "契约改动必须闭环" chain: Protocol + 全部实现 + 测试 + 必要时 mypy. The trim is not an excuse to break consumers.
- **Bypassing scripts/verify_doc_slop.py** — the script is a probe, not the definition, but its output is the cheapest sanity check before commit. Always re-run.

## Commands / 调用方式

机械扫 CoT 泄漏模式时,agent 优先 `lca-ops notes-slop`(内部调 `scripts/verify_doc_slop.py`);该 wrapper 是 Note / docs 范围内的统一入口,CI / ad-hoc 调试才直接调裸脚本。