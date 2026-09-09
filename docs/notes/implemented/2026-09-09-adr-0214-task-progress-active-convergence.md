# ADR-0214 PR-E 真实生产复测报告

**日期**: 2026-09-09
**触发 run**: `run_583e452ee58d`(对比基线 `run_c218d952c6f2`)
**任务**: 同一份 Q4 pptx 简报生成
**结论**: **部分成功** — 修复机制显著改善,但 PG-007 软收敛未完全闭环

## 一、量化对比(基线 → PR-E)

| 指标 | 基线 run_c218d952c6f2 | PR-E run_583e452ee58d | 变化 |
|---|---|---|---|
| read_skill_reference 失败 | 8 次 | 0 次 | ✅ **-100%**(PR-D 节流生效) |
| activate_skill 反复 | 4 次 | 2 次 | ✅ -50%(PR-D 节流生效) |
| **officecli create** | 0 次 | **12 次**(成功 + 失败混合) | ✅ **+∞**(PR-A 让模型走出循环) |
| **officecli add** | 0 次 | **76 次** | ✅ **+∞** |
| **officecli validate** | 0 次 | 61 次 | ✅ **+∞** |
| **office_works_sealer** | 0 次 | 32 次 | ✅ **+∞**(PR-E 收口生效) |
| run duration_ms | 45611 | 58665 | ⚠️ +29%(更深循环) |
| **PG-007 硬截止** | ✅ 触发 | ✅ **仍然触发** | ❌ **未解决** |
| terminal outcome | failed (zero_output_fallback) | failed (zero_output_fallback) | ❌ 未变 |

## 二、显著进步的根因

| 症状 | 旧机制卡死原因 | PR-A/B/D 修复后 |
|---|---|---|
| read_skill_reference 反复 8 次 | 单一工具熔断盲点 | PR-D 节流 + PR-B 多工具熔断 |
| activate_skill 反复 4 次 | 模型不知道已激活 | PR-D 注入 references 索引 + 文案 |
| officecli add = 0 | 模型从未走出 SKILL.md 子文档循环 | PR-D 节流 + PR-A task_progress 让模型走出 read 循环 |

**PR-B 真的生效了**:`test_run_c218d952c6f2_should_break_under_new_gates` 把基线事件喂给 MultiToolLoopBreakerGate,**断言在第 6 步前熔断**(通过 5/5 反例 fixture 测试)。

## 三、暴露的新问题(诚实记录)

### 3.1 officecli create 反复失败的子循环(新症状)

模型从"找 REFERENCE.md 死循环"换成了"officecli create 反复失败"子循环:
- 10 次 `rm -f && officecli create ...`(语法正确但文件已存在,缺 `--force`)
- 2 次 `officecli create --path ...`(错误语法变体)
- 2 次 `officecli --help`(每次失败后回退查 help)

**根因**: 模型的 reasoning 没学会 `officecli create --force` + `officecli help create` 的查-改-试循环。每轮 think 决策没携带 task_progress,PR-A 的默认值让测试通过但**生产路径的 cognition emit 方没填 task_progress**。

### 3.2 PG-007 软收敛未闭环

PR-C 三件套的 `terminal_predicate` 只在 PhaseNode 入口校验,**`on_terminal` 回调由 interpreter 集成**,而 interpreter 集成没在 PR-C 范围(交给 PR-E)。结果是:
- `terminal_predicate` 字段在 schema 上存在
- `traversal.advance()` 调用逻辑存在
- **interpreter 实际跑的时候没把这个回调接到 stop.main**

→ perceive.main 仍然走 PG-007 硬截止。

### 3.3 28+ Decision 构造点没同步改(PR-A subagent 已知偏差)

PR-A subagent 报告 §4 偏差 #3 列出:28+ Decision emit 方没显式传 `task_progress=...`,默认值 `TaskProgress()` 兜底。PR-A 测试覆盖"默认值不破坏既有构造点",但**生产路径的 cognition emit 方需要逐个改才能让 task_progress 进入 Session**。

这意味着 PR-B 的 `MultiToolLoopBreakerGate` 在生产 run 中**读到的是空 task_progress_history**(没数据 fold 进来),**只能依赖 trigger 3 (fingerprint_static)**,而 trigger 3 又依赖 recent control_turns 已有数据 — 这条路在生产中也没生效。

## 四、为什么 office_works_sealer 触发了 32 次但 run 仍失败

`office_works_sealer` 的职责是"close/run-end 一次性收口"。PR-A 让模型走出 REFERENCE 循环后,模型疯狂调 officecli create,每次 create 都在 outputs 目录写文件,**每次都触发 sealer 收口**(因为 sealer 监听 outputs 目录变化)。

但 sealer 本身**不熔断**(它是 observe 面 fold,不是 control 面 Gate)。所以 sealer 触发 32 次是**观察信号**,不是控制信号 — 模型不知道 sealer 触发了多少次,继续调。

## 五、PR-E 验收判定

按 ADR §8.2 标准:

| 验收项 | 标准 | 实际 | 判定 |
|---|---|---|---|
| officecli add ≥ 1 | 必须 | **76 次** | ✅ |
| officecli validate ≥ 1 | 必须 | 61 次 | ✅ |
| office_works_sealer 触发 | 必须 | 32 次 | ✅ |
| run 进入 terminal outcome | 必须 completed | failed | ❌ |
| PG-007 不再触发 | 必须 | 仍然触发 | ❌ |
| 没有 officecli 死循环(旧症状) | 必须 | 0 次 read_skill_reference | ✅ |

**3 / 6 通过,3 / 6 未通过。**

## 六、留给后续 PR 的明确路径

### PR-F(立即跟进,推荐独立 PR)

1. **interpreter 集成 PR-C on_terminal 回调**
   - 文件: `lca/harness/graph/execute/interpreter.py`
   - 改动: 调 `traversal.advance(...on_terminal=lambda: self._force_to_stop(node))`
   - 测试: `tests/harness/test_interpreter_terminal_predicate.py`

2. **28+ Decision emit 方补 task_progress=... 显式传值**
   - 文件: `lca/cognition/brain/decision_gates/...` + `lca/plugins/gate/...` + `lca/plugins/lab/think/...`
   - 改动: 每个 Decision 构造点加 `task_progress=parse_task_progress_from_llm_output(...)`
   - 测试: integration 测试断言 production run 中 Session 含 `task_progress.commit.v1`

3. **prompt_assembler 注入 task_progress_resumed 字段**
   - 文件: `lca/cognition/brain/prompts/*`
   - 改动: 头部加 `<task_progress_resumed>: {completed, remaining, confidence, last_reflection}`
   - 测试: prompt snapshot

### PR-G(后续,可选)

1. **`apply_task_progress` 在 cognition emit 路径强制 fsync**
   - 验证: `tests/integration/test_session_append_fsync.py` 已经覆盖 unit 级,但 production 路径需要新增测试

2. **MultiToolLoopBreakerGate 的 trigger 3 (fingerprint_static) 在 production 路径上的 wiring**
   - 验证: control_turns 的 fold 时机是否在 think gate enforce 前完成

## 七、本次复测作为后续 PR 的 fixture

`run_583e452ee58d` 自身成为新的反例 fixture:
- "officecli add 76 次 + sealer 32 次 + 仍 PG-007" 锁定**子循环 + 软收敛**这两个独立问题
- `tests/integration/test_run_583e452ee58d_regression.py` 应在 PR-F 中补
- `tests/integration/test_no_officecli_create_loop.py` 应在 PR-F 中补(锁定 create 反复失败的新症状)

## 八、ADR-0214 状态调整

PR-A/B/D 实质落地,145 个新测试全过,旧基线 `run_c218d952c6f2` 反例 fixture 通过。

**状态**: **Proposed → Partially Implemented** — 5 个 PR 中 3 个落地 + PR-E 部分验收 + PR-F/G 必要

下次合入 PR-F 后:
- 把 ADR-0214 状态升 "Proposed → Implemented"
- 把 PR-G 列为 "Post-merge follow-up"
