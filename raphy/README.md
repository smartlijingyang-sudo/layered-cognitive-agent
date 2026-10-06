# raphy — 新鲜会话架构优化循环

复用 `ralph/` 的状态机骨架（prd.json + progress.txt + `<promise>COMPLETE</promise>`），
但 stories 来自 `skills/improve-codebase-architecture` 的评估，每轮一个全新上下文的 subagent。

## 文件

| 文件 | 作用 |
|---|---|
| `raphy/prd.json` | stories 状态机（`passes`/`dropped`） |
| `raphy/progress.txt` | 进度日志，顶部 `## Codebase Patterns` 跨迭代沉淀 |
| `raphy/prompts/raphy-assess.md` | 评估 agent 指令（ASSESS ONLY） |
| `raphy/prompts/raphy-optimize.md` | 优化 agent 指令（一轮一 story） |

## 跑一轮

**1. 评估**（一个 subagent，全新上下文）：
> 按 `raphy/prompts/raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`，
> 在 `~/layered-cognitive-agent` 做评估，把 Strong / Worth exploring 候选写成 stories
> 存入 `raphy/prd.json`（分支 `raphy/<topic>`），commit。

**2. 优化**（每个 story 一个 subagent，全新上下文）：
> 按 `raphy/prompts/raphy-optimize.md` 执行：读 prd.json + progress.txt（Codebase Patterns 先读），
> 认领最高优先级 `passes: false` 的 story，实现→测试→更新状态→ONE commit。
> 剩 0 个 open 则输出 `<promise>COMPLETE</promise>`。

**3. 收尾**：全 done 后按分支工作流合并（见 `.agent/skills/finishing-a-development-branch/`）。

## 规则

- 一次只做一个 story；diff 最小；测试全绿才 commit。
- 允许有证据的 `dropped`（`passes` 保持 false，不造假），写清原因。
- 状态全在文件里，subagent 不带历史——上下文永远干净。
