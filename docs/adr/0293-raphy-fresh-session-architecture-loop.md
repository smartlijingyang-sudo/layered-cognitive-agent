# ADR-0293：raphy 新鲜会话架构优化循环

> **Status: Accepted**（2026-10-06 李超指令"做一个 raphy 机制"后起草；首轮实跑 RA-001/002 done、RA-003 有证据 dropped）
> 复用 `ralph/` 状态机骨架，新增"评估→优化"两阶段与 subagent 驱动。

## 1. Context（差距）

`ralph/`（2026-10-05 23:31 跑过一轮，`ralph/r2-arch-deepening`）已有可用骨架：

| 构件 | 作用 |
|---|---|
| `ralph/prd.json` | stories 状态机（`passes` 布尔） |
| `ralph/progress.txt` | 进度日志 + 顶部 `## Codebase Patterns` 跨迭代知识沉淀 |
| `ralph/prompts/ralph-agent.md` | 单 story 单 commit 指令 |
| `<promise>COMPLETE</promise>` | 停机信号，外部脚本监听 |

但有三个缺口：

1. **无评估阶段**：stories 靠人手写进 prd.json，没有"先评估出优化点"的机制。
2. **驱动脚本缺失**：prompt 里写"shell script watches stdout"，但 repo 内无驱动脚本（当时 ad-hoc 跑的）。
3. **Grok 特定**：prompt 是 "Grok Build Edition"，含 grok agent 才有的 skill 引用，Muse subagent 不能直接用。

同时 repo 自带 `skills/improve-codebase-architecture`（Ousterhout deep-module 词汇：module/interface/depth/seam/adapter/leverage/locality，deletion test），正是"评估出优化点"的现成方法论，但从未被接进循环。

## 2. 决定

建 `raphy/`（与 `ralph/` 并存，不改动 ralph）：

- **复用状态机格式**：`raphy/prd.json`（同 schema，story id 用 `RA-NNN`）、`raphy/progress.txt`（同格式，顶部 `## Codebase Patterns`）。
- **两阶段 prompt**（`raphy/prompts/`）：
  - `raphy-assess.md`：ASSESS ONLY。按 `skills/improve-codebase-architecture` 的 Explore→Present 流程（YAGNI 范围、git log hot spots、deletion test），把 Strong / Worth exploring 候选转成 stories 写入 prd.json，一次 commit，不碰 `raphy/` 之外任何代码。
  - `raphy-optimize.md`：一次认领最高优先级 `passes: false` 的 story，实现→测试→更新 prd.json/progress.txt→ONE commit→查剩余数；0 则输出 `<promise>COMPLETE</promise>`。允许有证据的 `dropped`（`passes` 保持 false，不造假）。
- **驱动 = subagent 链**：assess 跑一个全新上下文 subagent；之后每个 story 派一个全新上下文 subagent（driver 传 prompt 路径 + 状态文件位置，不传历史）。上下文永远干净，状态全在文件里。
- **分支**：每轮 `raphy/<topic>` 从 main 新建（如首轮 `raphy/arch-optimize`）。

## 3. 与 ralph 的关系

| | ralph/ | raphy/ |
|---|---|---|
| 状态机 | prd.json + progress.txt | 同格式复用 |
| story 来源 | 人手写 | skill 评估自动产出 |
| prompt | Grok Build Edition | Muse subagent 版，两阶段 |
| 驱动 | 缺失（ad-hoc） | subagent 链（本 ADR） |

ralph/ 保留不动（历史轮次可查）。未来若统一，只需把 ralph 的 prompt 换成 raphy 版。

## 4. 首轮实证（2026-10-06）

分支 `raphy/arch-optimize`，4 commits：

| commit | 内容 |
|---|---|
| `ed0047109` | assess：3 stories（RA-001/002/003） |
| `22fb55d10` | RA-001 done：9 个 `_emit_*` fallback 收敛为 `emit_assistant_ep_or_log` 接缝，237 测试过 |
| `401c7e22c` | RA-002 done：`delegate_tool.py` 双 `_fail` 收敛为模块级 helper，150 测试过 |
| `d8a5c00bd` | RA-003 dropped：三相 lifecycle emit 经逐行对比确需不同接缝，零代码改动 |

机制按设计工作：评估子 agent 甚至发现了比 story 预期更多的收敛点（RA-001 做了 9 个不是 7 个）；dropped 规则阻止了一次净亏可读性的"优化"。

## 5. 后果

- 新增架构优化循环的标准打法：assess → 一轮一 story → COMPLETE。
- `skills/improve-codebase-architecture` 从"人工调用"升级为"循环的评估引擎"。
- 代价：每轮一个 subagent 的上下文开销；assess 质量决定整轮上限（YAGNI + deletion test 是护栏）。
