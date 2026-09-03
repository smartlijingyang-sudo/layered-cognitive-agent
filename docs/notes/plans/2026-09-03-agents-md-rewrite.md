# Plan: LCA 根 AGENTS.md 重写(dsh 形式 + LCA 内容)

Status: proposed

## Problem

LCA 根 AGENTS.md 当前 **285 行**,与 dsh 根 AGENTS.md 的 **154 行** 相比膨胀 ~85%。审计 dsh 8 条核心思想后:**LCA 真做到 0 条、部分做到 3 条、缺失 5 条**。

用户拍板:**按 dsh 规范(形式 +章节风格),内容完全用 LCA 自己的** —— 不抄 dsh 文字、不抄 dsh 概念(如 `Pre-release stance` / `cordis` 等 monorepo 专属词 LCA 不需要)。

## 机制 / 第一性原理(为什么这么改)

**根 AGENTS.md 的定位** = agent 对话启动规则。每次任务 **第一个被注入** 的上下文。功能:让 agent **"知道 LCA 是什么、不能做什么、怎么找命令、错了看哪里"**,够 agent **做出第 0 步决策**,不用翻其他文件。

**装**(必留):① 一句话定位 + 立即指引 ② 仓库地图 ③ 架构不变量 + 名字 ④ 命令指针 ⑤ Conventions standing rules ⑥ Defensive patterns 链 home ⑦ Prose 纪律 链接 skill ⑨ Git 禁区。

**不装**:5 步 debug-run walkthrough / Team 策略细节 / 术语枚举 / 长表格 / 通用参数说明。

**约束机制** = 根里写指针,**agent 不知道就做不了第 0 步决策**。

## dsh 8 条核心思想审计

| # | dsh 核心思想 | LCA 现状 | 设计稿动作 |
|---|---|:---:|---|
| 1 | 一句话定位 + 立即指引 | ❌ | 加 **§1 Header**(2 行)|
| 2 | Pre-release stance / 时代定位 | ❌ | **不抄**,LCA 没有"Release 阶段",改用 "工程思维" 段(4 问 + 卫生清单)|
| 3 | Code-block repository layout | 🟡 | 改 §2 为 code-block 风格 |
| 4 | Commands = 命令清单,不含 5步 | ❌ | §6 重写:只留命令指针表 |
| 5 | Conventions 单点收口(100 行 bullet)| 🟡 分散 | 新加 §5 "Conventions" 一节,收口所有 standing rule |
| 6 | Defensive patterns 链 home | ❌ | 加 §6 子段"Before X,读 Y.md" |
| 7 | Type safety / prose 纪律 | 🟡 | 新加 §7 "Prose 纪律" 一段,链 `.agents/skills/lca-prose-standard` |
| 8 | Editing 元规则 | ❌ | 加 §9 "如何改本文件"(3 行) |

## 目标章节布局(dsh 标题哲学 + LCA 内容)

| 章节 | 目标行 | 内容 | 来源 |
|---|---:|---|---|
| §0 Header + 一句话锚点 + 立即指引 | 5 | "LCA 是分层的认知 Agent。改 `lca/` 前读 docs/architecture;文档看 docs/AGENTS.md" | **新增**,dsh 风格 |
| §1 动手前必须知道(总闸 4 问 + 卫生清单)| 50 | LCA 独有,**不抄 dsh** | **保留**当前 §1 全文 |
| §2 仓库地图(code-block 风格) | 28 | code-block 嵌套,职责一句话 | **重写**当前 §2 |
| §3 架构不变量 + 闭集 | 35 | 7 条 C1-C7 + 五层单向依赖表 | **保留**当前 §3 全文 |
| §4 结构化认知(指针化) | 8 | 1 段 + 链 `docs/specs/lca-structured-cognition-guide.md` | **指针化**,原 §4 |
| §5 Conventions (单点收口) | 25 | bullet 列表,所有 standing rule 集中:类型标注、命名、no-comment-reasons、AGENTS.md 全文 + JSDoc / doc 一致、双语、neighbor convention、测试规范等 | **新增**,从 §1/§5 收口 |
| §6 命令与验证(指针表) | 30 | 命令指针表 + "Before X,读 Y.md" 子段 | **重写**当前 §6 |
| §7 Prose 纪律 | 5 | 1 段链 `.agents/skills/lca-prose-standard/SKILL.md` + `.agents/skills/lca-trim-cot-leakage/SKILL.md` | **新增** |
| §8 Git 与禁止事项 | 15 | 当前 §7 全文 | **保留** |
| §9 如何改本文件 | 5 | "本文件只能装 standing rule;非 standing rule 移到 home;改前必须读 §1" | **新增** |
| **合计** | **~206** | | 从 285 → 206(-28%) |

**注意:总行数没缩到 180**,原因 = LCA 必备内容(总闸 4 问 + 卫生清单 + 7 不变量 + Git 禁区)合计约 105 行,**这是 LCA 不能让度的硬底**。dsh 154 行是因为它**没这些内容**(Cordis monorepo 不需要认知闭集)。LCA 根 AGENTS.md ≈ 200 行是**真实机制下限**,再压就丢 LCA 必装。

## 保留(LCA 优点)

- 总闸 4 问全文 + 离开前卫生清单全文
- 7 条架构不变量(C1-C7)名字 + 一句解释 +五层依赖表
- 命令指针表(含本次加的 notes-* 3 行)
- Git 禁区全文
- 工程思维("动手前 · 总闸 4 问(必答,不答不写)")

## 拆出 / 收口(降膨胀 + 集中)

| 原位置 | 内容 | 去向 |
|---|---|---|
| §4 | "结构化认知与数据所有权"完整定义 (~30 行)| **指针** → `docs/specs/lca-structured-cognition-guide.md` |
| §5 | "Team 领域语言 + 编码规范"完整列表 (~25 行)| **收口到 §5 Conventions**(bullet 形式)|
| §6 | "5 步 debug-run" + 口语映射 + "通用参数" (~80 行)| **指针** → `docs/debug/README.md` 顶部 + `lca-ops --help` |

## 吸取 dsh 形式

- **每章节 1-3 段 + 链 home**(dsh 通篇风格)
- **Conventions 用 bullet 列表**(dsh §5 风格,LCA §1/§5 散落 bullet 合并到 §5)
- **"Before X,读 Y.md" 指引**(dsh §6 "Defensive patterns" 风格)
- **"Editing these instructions" 段**(dsh §8 风格)
- **一句话锚点 + 立即指引**(dsh 第 3 行风格)
- **不用 dsh 概念**:Pre-release stance / cordis / pnpm / packages/ monorepo / etc.**LCA 不抄**

## 风险评估

- **中**:动到 AGENTS.md 的实质内容(不是加1 行,是减 ~80 行 + 重排章节)
- **缓解**:
  - 保留**所有** home 链的原句(只换为指针),确保从根到 home 仍可达
  - 不删任何文本到 git 之外 —— 拆出内容用 git 注释或 commit message 说明去向
  - dsh 那 8 条审计结果与设计稿映射作为 review checklist

## 验收(7 条 grep + 1 行数)

1. `wc -l AGENTS.md` ≤ 220 行
2. `grep -c '总闸 4 问' AGENTS.md` ≥ 1
3. `grep -c 'C1 \|C2 \|C3 \|C4 \|C5 \|C6 \|C7 ' AGENTS.md` ≥ 7
4. `grep -c 'notes-check\|notes-audit\|notes-slop' AGENTS.md` ≥ 3
5. `grep -c 'docs/debug/' AGENTS.md` ≥ 1(指针到 debug home)
6. `grep -c 'lca-structured-cognition-guide' AGENTS.md` ≥ 1(指针到 cognition home)
7. `grep -c '## Conventions' AGENTS.md` = 1(新加 §5)
8. `grep -c '如何改本文件\|Editing these' AGENTS.md` ≥ 1(新加 §9)

## 不做

- 不删任何 home 文件
- 不重写 `docs/specs/lca-structured-cognition-guide.md` / `docs/debug/run-debug-guide.md`
- 不动 `docs/notes/`(老 ADR 不动)
- 不改 `scripts/lca-ops` 或 CLI 注册
- 不动本次会话已加的 12 个 skill
- **不抄 dsh 的任何一段文字或概念**

## 顺序

1. 写设计稿(本文件,已就绪)
2. **等用户 review**
3. 动手重写 AGENTS.md
4. 把"5 步 debug-run" + 口语映射移到 `docs/debug/README.md` 顶部
5. 在 docs/specs/lca-structured-cognition-guide.md 末尾追加一行"详见根 AGENTS.md §4"反向链
6. 跑验收命令(7 条 grep + wc)
7. 跑 ruff + pytest test_run_manifest.py(确认未破坏 CLI)