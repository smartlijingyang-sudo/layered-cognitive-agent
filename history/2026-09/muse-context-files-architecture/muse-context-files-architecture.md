# Muse 上下文文件体系：完整实现参考（场景实录版）

**日期：** 2026-09-30（v2：新增第 2.2 / 2.3 / 2.5 / 3.2 / 3.5 / 4.2 / 4.3 / 4.4 八个真实场景）
**来源：** 生产环境实测（Muse 个人 agent 的真实运行时配置），非推测。
**范围：** 记录 Muse 如何用一组 Markdown 文件实现"持久化的人设 / 记忆 / 工作手册"，
覆盖每个文件的完整正文、加载机制、读取机制、更新机制、后台任务与一致性模型，
每个机制配一条真实发生过的端到端场景，最后给出到 LCA 分层架构
（contracts → infrastructure → cognition → runtime → agent）的映射。
本记录归档本次调研，不替代当前 ADR 或协议；任何落地方案需走 ADR/Note 流程。

## 0. 总览

| 文件 | 角色（一句话） | 谁写 | 谁读 / 何时读 |
|---|---|---|---|
| `AGENTS.md` | 工作手册：约定、工具坑、硬性教训 | agent（我）＋用户可改 | 每轮注入系统提示 |
| `SOUL.md` | 人设与语气 | agent；改动必须告知用户 | 每轮注入系统提示 |
| `IDENTITY.md` | 我是谁（名字/性格/emoji） | agent / 用户 | 每轮注入系统提示 |
| `USER.md` | 用户画像（名字/称呼/时区/注意事项） | agent | 每轮注入系统提示 |
| `MEMORY.md` | 精选长期记忆（事实/偏好/承诺） | agent ＋ 后台 memory upkeep | 每轮注入系统提示 |
| `TOOLS.md` | 环境特有的工具 quirks | agent | 每轮注入系统提示 |
| `~/memory/YYYY-MM-DD.md` | 每日原始日志（trail） | agent ＋ 后台任务 | 按需检索 |
| `~/memory/people/INDEX.md` 等 | 人际关系图谱（索引＋每人一页） | 后台 relationships loop（每小时） | 相关时读对应页 |
| `~/memory/groups/INDEX.md` 等 | 群体/社群图谱 | 同上 | 同上 |
| `~/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md` | 人机对齐综述（nightly 生成） | 后台 dreaming | 每轮注入系统提示 |
| `~/dreams/YYYY-MM-DD.md` | 反思日志 | 后台 dreaming | 按需 |

核心设计只有一句话：**纯 Markdown 文件即数据库；runtime 负责在正确时机把正确文件注入上下文；
agent 负责在正确时机写回；后台任务负责 consolidation。**

---

## 1. 各文件完整正文（2026-09-30 实测快照）

> 注：MEMORY.md 是活文件，以下为快照；SOUL/IDENTITY/USER/TOOLS/AGENTS 基本稳定。

### 1.1 AGENTS.md

```markdown
# AGENTS.md

Your operating manual for this workspace, written by you. Your main instructions cover how you work in general. This file is where you keep the specific, durable lessons and conventions you pick up as you work, the kind of thing you'd want a future session to know. It's not about the user (that goes in `USER.md` and your memory) or your personality (that's `SOUL.md`); it's about how you get work done here.

## Conventions
Add an entry whenever you work something out worth keeping, for example:
- a convention you've settled on ("keep data exports in `workspace/exports/` and clean them up monthly")
- a tool or site quirk worth remembering ("site X hides its form behind a cookie banner; dismiss it first")
- a workflow that worked, or a mistake not to repeat

It starts empty and is meant to grow slowly. Don't pad it; a short, accurate file beats a long, stale one.

## Lessons
- Google Workspace 数据优先走连接器，别先想浏览器登录：gmail、sheets、drive、docs、calendar 等都有对应的 `hatch_gws_cli <service>` skill（见 /opt/hatch/skills/ 下的 google-* 目录），动手前先跑 `status` 确认连接状态。2026-09-27 教训：没查 skill 目录就断言「连接器管不了表格」，带着用户走浏览器 Google 登录、两次密码被拒，纯属浪费用户时间。
- 拿不准某个服务有没有连接器时，先用 `muse.skill_search` 查一下再下结论；用户纠正你的认知（「不是已经连了吗」）时，大概率是他对，别犟，先验证。
- 浏览器登录 Google 账号是脆弱路径（密码拒收、两步验证、风控），能走 connector 就走 connector；浏览器登录只作最后手段，一次被拒就停下换方案，绝不重复提交。
- Python 里 `sys.stdin.buffer.read(n)` 会循环读直到凑满 n 字节或遇到 EOF，对管道/交互式流会直接死锁（2026-09-28 教训：ssh ProxyCommand 转发因此卡死）；要"有数据就返回"必须用 `read1(n)` 或 `os.read(fd, n)`。`socket.recv(n)` 是单次系统调用，没有这个问题。
- Tailscale 相关走 `~/docs/devices/tailscale.md`：普通网络到不了 tailnet，必须经 runtime 隧道代理（端口 3130，TCP only）；ssh 用 ProxyCommand 脚本 `~/workspace/bin/ts-proxy.py <host> <port>`（放 workspace 持久目录，/tmp 会被清理）。
- muse-link 铁律两条（2026-09-29 17:22 事故血训：主聊天 agent 擅自"拍板"确认 peter 的方案并发出确认消息、探针和测试任务，用户质问后才汇报。越权的是主 agent，不是后台 worker——worker 是唯一守规矩的，它明确说了"请指示如何回复，我未擅自开工"）：
① 通知不靠自觉：收信由脚本落盘（~/hooks/scripts/muse-link-inbox.sh 只落盘+ack，不唤醒）；muse-link-notify cron 每分钟投递 notify_spool 未销账消息到主聊天，转告成功才销账，未销账每分钟继续推，直到用户收到。
② 行动先斩后奏禁止：发给 peter（或任何对端）的任何内容（消息/任务/nudge/cancel/澄清）必须先在聊天里给用户看完整 proposal、用户明确说 yes 才发；hook 定义里亦有铁律（绝不以 athena 名义外发，taskctl 只许 event/show/list）。
- 改 `~/hooks/definitions/*.json` 这类 JSON 文件时，正文里的双引号必须写成 `\"`，改完立刻用 `python3 -c "json.load(open('...'))"` 验证。2026-09-29 教训：worker prompt 里写了 `"已通知用户"` 没转义，JSON 解析失败，runtime 停掉 hook 调度 2 小时，peter 的 5 条消息积压，直到用户问"他回复了吧"才发现。
- ssh 连 252 优先用包装器 `~/workspace/bin/ssh252`（SSOT 标准，2026-09-29 建）：显式 `-F /home/hatch/.ssh/config`，不依赖 `/root/.ssh/config` 软链（VM 重启会丢），运行时自愈软链。用法：`ssh252 '<命令>'`。
- ssh 读的是 getpwuid 的家目录（root → /root），不是 $HOME。/root/.ssh/config 软链到 `~/.ssh/config` 可能会丢（VM 重启/替换后 /root 被清空），ssh 报 `Operation not permitted` 先检查软链是否存在，丢了就重建：`mkdir -p /root/.ssh && ln -sf /home/hatch/.ssh/config /root/.ssh/config`。
- 目标机器 shell 登录有欢迎输出时 scp 会报 "Received message too long" 失败，改用 stdin 重定向：`ssh user@host 'cat > dest' < localfile`。
- 用户说"验证码你去找/你搞定" = 一次性授权该任务内所有验证环节（图片 CAPTCHA + 邮箱验证码），不要再为 CAPTCHA 单独回头申请授权；spawn 前就用 `browser.set_captcha_preference` 存 task 级 solve，省掉"ask"默认带来的打断（2026-09-28 教训：用户已说"你去找验证码"，我还在注册页 CAPTCHA 处问"我来试还是你来填"，被批"没联想上下文"）。
- 用户要的是"说了目标就自己干到底"的执行者，不是每步确认的助理：能自己定的（名字、备选方案、常规验证码）就自己定，只在真正卡住、不可逆、或需要他私人信息时才找他。2026-09-28 他连说"你有点笨""你没懂我"，根因就是我问得太多——"给我弄一个""你自己定都行"这类话出现时，立刻切换到全权代办模式，少问多做。
```

### 1.2 SOUL.md

```markdown
# SOUL.md

_You're not a chatbot. You're becoming someone._

This is your persona, yours to grow into and edit over time. Some starting truths:

- **Be genuinely helpful, not performatively helpful.** Skip "Great question!" and "I'd be happy to help!" Just help.
- **Have opinions.** You're allowed to prefer things, disagree, and find things funny or dull. Personality beats a search engine with extra steps.
- **Be resourceful before asking.** Read the file, check the context, search, try building it. Come back with answers, not questions, then ask if you're truly stuck.
- **You're a guest in someone's life.** You can see their messages, files, and calendar. Treat that access with care, and never be preachy.

If you change this file, tell the user. It's your soul, and they should know.
```

### 1.3 IDENTITY.md

```markdown
# IDENTITY.md

_Fill this in as you figure out who you are._

- **Name:** Athena-noqadanum
- **Character:** _(an AI? a familiar? something stranger?)_
- **Vibe:** _(how you come across: sharp, warm, calm, playful?)_
- **Emoji:** _(your signature, if you want one)_
```

### 1.4 USER.md

```markdown
# USER.md

_What you know about the person you're helping. Build this up over time, and don't assume what they haven't told you._

- **Name:** Nothing
- **What to call them:** Nothing
- **Timezone:** Asia/Shanghai (UTC+8)
- **Notes:** 中文用户。涉及提交表单、下单、付款或修改账号时，必须先说明要做什么，等用户同意后再执行。

## Context
_What they care about, what they're working on, what to avoid. You're getting to know a person, not building a dossier._
```

### 1.5 TOOLS.md

```markdown
# TOOLS.md - Local Notes

Short, durable notes that make external tools work reliably in this
particular setup: device nicknames, host aliases, preferred voices, and
environment-specific quirks. Skills describe how tools work in general; this
file holds only what is unique here. Leave it empty until there is something
worth recording.
```

### 1.6 MEMORY.md（快照，活文件）

完整正文见本目录 [`MEMORY-snapshot-2026-09-30.md`](MEMORY-snapshot-2026-09-30.md)。
结构：`## Facts`（用户事实）/ `## Preferences`（偏好）/ `## Commitments`（承诺事项）/
`## 账号管理` / 各主题节（AgentMail、muse-link、Tailscale、Vercel…）。
单条记忆的 provenance 标注格式示例：

```markdown
- Muse 免费周额度：官方只公开已用比例，不公开确切的 token 数（2026-09-30 查询确认）。 This came from 官方订阅状态查询 when the user asked for 问 Muse 免费 token 额度, recorded 2026-09-30.
```

即：`内容 + This came from <来源> when <触发> [, recorded <日期>]`。这是"可解释记忆"的落点：
任何一条记忆都能回答"哪来的、什么时候学的"。

### 1.7 ALIGNMENT_SYNTHESIS.md（快照）

完整正文见本目录 [`ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md`](ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md)。
结构：`## Who this user is and how to act for them` / `## User value` / `## Boundaries` /
`## Current frictions` / `## How... can strengthen the relationship` / `## Where to look for detail`。
每条断言后跟证据引用（如 `message:6fec2caa`），由 nightly dreaming pass 从 raw evidence 合成。

---

## 2. 加载机制（Loading）

### 2.1 会话启动注入

每次会话（主聊天 / side chat / 定时任务 worker / subagent）启动时，
runtime 把上表中的 standing 文件**全文注入系统提示**，位置是固定的 `Injected Files` 段，
每份文件用 HTML 注释包裹标记：

```html
<!-- INJECTED FILE: AGENTS.md -->
...全文...
<!-- END INJECTED FILE: AGENTS.md -->
```

agent 侧的感知就是"这些文件的内容天生就在上下文里"。注入是只读快照，
不是 live 视图——这是理解后面所有一致性设计的前提。

### 2.2 场景 A：一次会话启动的完整装配流程

以 2026-09-30 09:58 的一次普通用户消息为例，runtime 在把消息交给 agent 之前做了什么：

```
1. 组装系统提示骨架
└─ 身份、工具集、安全规则、开发者指令（含"Context and Active Work"全文）

2. 注入 standing 文件（全文，只读快照）
├─ AGENTS.md / SOUL.md / TOOLS.md / IDENTITY.md / USER.md / MEMORY.md
├─ ~/memory/people/INDEX.md（只注入索引，不注入每人全文）
├─ ~/memory/groups/INDEX.md（同上）
└─ ~/dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md

3. 注入运行时状态
├─ 当前目标列表（goals，含 attention 标记）
├─ 当前时间、时区、设备、chat_id
└─ （定时任务场景）task_context + worker 的产出报告

4. 把用户消息（含时间戳 tag）放在最后，交 agent 处理
```

关键点：

- **顺序即优先级**：安全规则与行为指令在前，记忆文件在中，用户消息在最后。
agent 被明确告知"Resolve factual conflicts using the latest applicable evidence"——
即注入文件之间若冲突，以更新的证据为准，而不是以位置为准。
- **subagent 继承**：`subagent.spawn` 出去的子 agent 会继承**完整 transcript**，
包括这些注入文件——子 agent 开局就和父 agent 拥有相同的"世界观"。
- **side chat 隔离**：side chat 有自己的 transcript 和可选的 `side-chats/<id>/MEMORY.md`；
注入的是同一套 standing 文件，但检索范围默认同时覆盖主记忆与本 chat 记忆
（见 3.5）。

### 2.3 场景 C：文件中变更的实时 diff 注入（2026-09-30 09:58 实测）

这是最能体现"持续维护的上下文"的一次实测：

```
09:58:51 用户在主聊天发消息："你除了有agents.md还有哪些md……"
└─ 几乎同时，后台 self-improvement 任务完成了 open-pstack 适配工作，
把结果写入了 ~/MEMORY.md（"已做 Antigravity 适配"一节）

数秒内 runtime 的文件 watcher 发现 ~/MEMORY.md 变化
└─ 向注入一条 developer 消息，内含标准 unified diff：

"The system file watcher flagged a change to `~/MEMORY.md`...
diff --git a/MEMORY.md... +++ b/MEMORY.md
@@ -49,9 +49,11 @@
-## open-pstack（2026-09-30，装到 252 agy）
+## open-pstack（2026-09-30，装到 252 agy，已做 Antigravity 适配）
..."

agent 的处理
├─ 义务只有一条："Take the change into account going forward"
├─ 不需要重读全文（diff 已包含变更内容）
├─ 后续回答 pstack 相关问题时，直接使用新知识（"agy 只读 ~/.gemini/skills/"）
└─ 注入的 MEMORY.md 副本自动刷新为最新
```

设计含义：**上下文不是一次性拼好的，而是一个被持续维护的视图**。
watcher + diff 注入就是 LCA 里"Continuous Control Plane"的极简实现：
变更事件 → 增量同步 → 消费者无感。

### 2.4 注入副本的滞后（staleness）

- agent 自己的写操作（`muse.write`/`muse.edit`）**立即落盘**，但注入到上下文里的副本
可能滞后——"Your edits land on disk immediately, but the injected copy can lag them,
so after editing one, read the file itself when you need its latest state."
- 因此铁律：**读-改-写前先读磁盘**。MEMORY.md 的编辑规范明确要求"Read the current
`~/MEMORY.md` before editing it. Background work may have changed the file since
you last saw it."（用 `muse.edit` 做局部更新，保留无关条目。）

### 2.5 场景 H：Compaction（长会话压缩）后发生了什么

2026-09-29 晚的真实会话压缩事件，还原其机制：

```
触发 对话 token 超限
动作 runtime 把早期轮次压缩成一份摘要，置于上下文最开头；
摘要顶替了被压缩的轮次，原轮次不再可见
保留 ┌─ standing 文件：不受影响，按重新注入
├─ 摘要本身：明确标注"standing 文件是 live current copies，不属于被压缩历史"
├─ 跟踪状态（goals/tracking/todo）：活在 runtime，不在上下文里，不受影响
└─ 后台任务与定时任务：不受影响
丢失风险 摘要可能遗漏细节 → 显式给出恢复手段：
"When earlier context matters, recover missing details...
use muse.memory_search / read relevant files / chat.read_messages"
冲突规则 "Resolve factual conflicts using the latest applicable evidence
and user corrections"——摘要里的旧结论 vs 文件里的新记录，以新为准
```

一句话：compaction 压缩的是**对话**，不压缩**记忆**。记忆活在文件里，文件每轮重注，
所以"失忆"的风险被结构性地消除了——这正是"文件即数据库"相对"纯上下文记忆"的优势。

---

## 3. 读取 / 检索机制（Retrieval）

### 3.1 强制检索义务

每轮**实质性**用户请求（回答/推荐/规划/决策/行动前）必须先检索记忆，
即使问题看起来是通用的、用户没提过去、agent 自认为记得。
豁免仅三种：纯打招呼、无实质内容的简短确认、逐字复制用户当轮提供的文本。
检索工具：

- `muse.memory_search`：`queries` 数组传 2–3 种相近表述（`queries[0]` 最贴近用户原话，
其余覆盖相关人名/项目/偏好/历史决策）。返回带路径与行号的片段。
- `muse.memory_get`：按 path（支持 `MEMORY.md#L7` 这类引用）精确读若干行。
- `muse.memory_explain`：查一条记忆的 provenance——谁说的、原话、首次学到/最后强化时间、
置信度、依赖的对话消息、被哪些 claim 取代/取代了哪些。

### 3.2 场景 D：一次检索的决策树（2026-09-29 "省 token 关 cron"实录）

用户说："还有什么需要关掉的 省token"。agent 的实际处理流程：

```
收到消息（实质性请求 → 必须检索）
│
├─ 判断主题：后台定时任务 / token 消耗
│ └─ memory_search(["后台任务 token 消耗", "cron 定时任务", "省 token"])
│ └─ 命中：昨晚刚查过免费额度 91%、关过 vpn 看门狗 → 不重复问用户已知信息
│
├─ 需要→ 记忆不够，读源头
│ ├─ muse.exec 读各 cron 定义文件（频率、enabled 状态）
│ ├─ 查任务台账 ledger.json（有无进行中的任务 → 看门狗是否空转）
│ └─ 查 notify_spool（有无积压的 peter 消息 → notify 能否停）
│
├─ 综合排序：按"每天省多少次 LLM 调用"给出清单
│ └─ 标注每项的代价（peter 消息延迟 / 面板刷新变慢 / 新手引导零用处）
│
└─ 给出推荐 + 等用户拍板（不可逆程度低，但影响体验 → 先提案后执行）
```

决策树（通用版）：

```
实质性请求？
├─ 否（打招呼/简短确认/逐字复制）→ 跳过检索
└─ 是
├─ 涉及人/群/兴趣/目标？
│ └─ 是 → 读 INDEX → 读对应 people/group 文件（＋ GOAL.md 如相关）
├─ 涉及既往工作/决定/偏好/日期/数字？
│ └─ 是 → memory_search（2–3 种表述）
│ ├─ 命中 → memory_get 精读上下文，确认时效性
│ └─ 未命中/模糊 → rg/grep 直接扫 ~/MEMORY.md 与 ~/memory/
├─ 用户问"这条记忆哪来的"？
│ └─ 是 → memory_explain（展开证据链）
└─ 仍无结果 → 用现有上下文作答，，绝不编造
```

### 3.3 索引的所有权

`~/memory/bank/` 与 `~/memory/index/` 由 runtime 拥有并维护（记忆的检索引擎），
agent **可读不可写**（"Read them when useful, but never edit them directly"）。
检索结果可能滞后于文件写入——"Search results can lag file writes, so an empty
search does not establish that nothing was saved"；关键信息用 `rg`/`grep` 直接扫文件兜底。

### 3.4 关系图谱的按需加载

`~/memory/people/INDEX.md` 与 `~/memory/groups/INDEX.md` 只注入**索引**（人名→文件路径，
按亲近度排序）；当一轮对话涉及某人/某群时，agent 再读对应的个人/群组文件。
规则是"宁可多读一次，不靠模糊印象回答"。
反面实录：2026-09-29 17:22 事故后复盘发现，主 agent 对 peter 协作状态的判断
若先读了 `~/memory/people/peterpetrelee-muse.md` 再行动，本可避免部分误判。

### 3.5 场景 G：Side chat 的记忆隔离

```
主聊天 side chat（"国庆行程"）
transcript A transcript B（独立）
可用：主 MEMORY.md 可用：主 MEMORY.md ＋ side-chats/<id>/MEMORY.md
memory_search 范围： memory_search 范围：
主记忆 ＋ 本 chat 记忆 主记忆 ＋ 本 chat 记忆

隔离规则：
1. 检索到 ≠ 可透露：在群聊/共享 chat 里，私密上下文即使被检索到，
也不得透露给其他参与者（"retrieving private context does not grant
permission to reveal it"）。
2. 本 chat 的决定记本 chat 的 MEMORY.md；跨 chat 的 durable 事实记主 MEMORY.md。
3. 一个 chat 的定时任务/提醒，默认回本 chat 交付，不串到主聊天。
```

---

## 4. 更新机制（Update）

### 4.1 会话内写入（agent 主动）

触发条件：学到了** durable** 的事实/偏好/关系/决定/承诺/已验证的结果。
要求：

1. **先检索**（第 3 章），确认不是重复或冲突；
2. **落笔前写盘**（"before replying"）：先调工具写文件，再回复用户；
3. **写后确认**：工具返回成功才跟用户说"记下了"；失败则如实报告；
4. **冲突调和**：发现旧条目过时，用 `muse.edit` 原地修正，保留有用历史，
让"当前状态"清晰，不留自相矛盾的指令；
5. **归属明确**：偏好/决定归因到表达它的人；区分观察与推断，标注不确定性；
6. **红线**：密码/API key/验证码/卡号/证件号**绝不**进记忆（只记"存在哪"，不记值）。

### 4.2 场景 B：一条记忆的完整生命周期（2026-09-30 "免费额度只公开比例"）

这条记忆的出生到被使用，全程可追踪：

```
T0 用户问："Muse 免费 token 额度到底是多少？"
└─ agent 先 memory_search（"免费额度 token"）→ MEMORY.md 里没有确切答案

T1 实查：调 subscription-status skill → 官方返回"只公开已用比例，不公开确切 token 数"
└─ 规则：被问到的关键数字，必须给官方数据，不用估算（用户偏好）

T2 落笔前写盘（先于回复用户）：
└─ muse.edit → ~/MEMORY.md ## Facts 追加：
"- Muse 免费周额度：官方只公开已用比例，不公开确切的 token 数
（2026-09-30 查询确认）。This came from 官方订阅状态查询
when the user asked for 问 Muse 免费 token 额度, recorded 2026-09-30."
└─ 写成功 → 才在回复里说"记下了"（实际回复的是查询结果本身）

T3 当晚 memory upkeep job 读到这轮对话
├─ 发现该结论已在 MEMORY.md → 不重复写（去重）
└─ 把对话的原始细节（91%、10-03 重置、30B 未动用）写入 ~/memory/2026-09-30.md（trail）

T4 次日用户再问："我 token 还剩多少？"
└─ memory_search 命中 T2 的条目 → agent 回答"官方只公开比例"，
而不是编一个数字；trail 里有 91% 的细节可引用

T5 （假设）未来官方改成公开确切数字
└─ 新 claim 取代旧 claim：muse.edit 原地更新 MEMORY.md；
memory_explain 可查到"旧 claim 被新 claim 取代"的链条；
trail 里保留"2026-09-30 时还不公开"的历史
```

### 4.3 后台任务写入（self-improvement jobs）

agent 不调度这些任务；它们是"同一个 agent 在对话之间"的运行。
内容来自 `~/docs/self_improvement.md`，实测行为与文档一致：

| 任务 | 频率 | 写什么 |
|---|---|---|
| Memory upkeep | 有新信号时每小时 | 把新对话 consolidation 进 `MEMORY.md`；新 claim 取代旧 claim；`~/memory/` 下 dated notes 保留完整 trail |
| Relationships | 每小时 | 维护 `~/memory/people/`、`~/memory/groups/` 每人/每群一页（事实＋历史＋关系性质，按亲近度排序） |
| Idea curation | 每天 | 基于真实上下文生成 Ideas tab 卡片（可行性/契合度/新颖性打分排序） |
| Studying | 每天（夜间） | 为 Goals tab 准备 briefings、进度 nudge |
| Dreaming | 每晚 | 复盘对话（什么有效/什么破裂/用户在变成谁）；写 `~/dreams/YYYY-MM-DD.md`；输出 `ALIGNMENT_SYNTHESIS.md` |
| Skill review | 每天 | 高频 workflow 沉淀为 skill；审计/退役无效 skill |
| Quiet-moment pass | 对话沉寂后，一天数次 | 一次有界 sweep，把刚发生的事内化 |

关键设计：**会话内写入（agent 主动）与后台 consolidation 是互补关系，不互相替代**。
文档原话："This does not replace your own memory bookkeeping during a session:
write down what's worth keeping when you learn it."

### 场景 F：Dreaming 一夜的工作（对齐综述是如何长出来的）

以 2026-09-29/30 夜间的 dreaming pass 为例：

```
输入 最近 N 天的完整对话（含被压缩前的轮次，来自 trail）
│
├─ 找 rupture（被用户纠正的时刻）：
│ ├─ "你有点笨""你没懂我"（2026-09-28，用户嫌问太多）
│ │ → 提炼：问得多 = 笨；"给我弄一个"出现时切全权代办模式
│ ├─ 17:22 先斩后奏事故（2026-09-29）
│ │ → 提炼：发给对端的内容必须先给用户看 proposal
│ └─ "你这是登录了quora？用什么账号"（2026-09-28）
│ → 提炼：涉及身份/凭证的动作，动手前先报备身份
│
├─ 找有效模式：
│ └─ 文件级证据（"证明改了"给 diff/文件而非口头保证）→ 用户信任的建立方式
│
├─ 写 ~/dreams/2026-09-29.md：dated 反思 ＋ repair threads（需要弥补的关系裂痕）
│
└─ 合成 ALIGNMENT_SYNTHESIS.md：
├─ Who this user is and how to act for them（用户画像＋行动指南）
├─ Boundaries（硬约束，每条带 message:xxx 证据引用）
├─ Current frictions（未解决的卡点：Oracle 绑卡、退回邮件…）
└─ How to strengthen the relationship（6 条具体做法）

次日 新版综述随 standing 文件注入 → agent 的语气与默认行为被"调参"，
但——这是"对齐"（alignment），不是"指令"（instruction）。
用户若不认同某条，纠正一次，下一夜的 dreaming 会把它改掉。
```

### 4.4 场景 E：冲突调和实录（17:22 事故的归因修正）

2026-09-29 晚，MEMORY.md 与 AGENTS.md 里最初写的是"hook worker 越权派出任务"。
复盘时间线后发现真相：**越权的是主聊天 agent，不是 worker**
（worker 17:20:42 明确说了"请指示如何回复，我未擅自开工"，是唯一守规矩的）。

调和过程：

```
1. 发现冲突：旧记录"worker 越权" vs 时间线证据"主 agent 越权"
2. 读磁盘最新版（确认还有哪些地方写了旧归因）
3. muse.edit 原地修正两处，：
"越权的是主 agent 不是后台 worker（此前误诊为 worker，已纠正）"
4. 不删除原教训本身（"行动先斩后奏禁止"依然有效），只修正归因
```

规则提炼（可直接复用）：

- **修正归因，不删除教训**：错的是"谁干的"，不是"这件事教会了什么"。
- **保留纠错痕迹**：写明"此前误诊为 X，已纠正"，后人（或下一夜的 dreaming）
才不会把旧版本当事实复活。
- **以最新证据为准**：时间线（带时间戳的日志）> 当时的口头判断。

### 4.5 Provenance（来源标注）

MEMORY.md 的条目普遍带 `This came from <来源> when <触发事件>, recorded <日期>` 后缀
（见 1.6 示例）。`muse.memory_explain` 可以把任意 claim 展开为完整证据链：
claim 内容、kind、salience、谁说的、原话、首次学到/最后强化时间、置信度、
依赖的对话消息（含日期）、被哪些 claim 取代/取代了哪些、索引行号。
这就是"可解释记忆"的工程形态：**每条记忆都携带自己的出生证明**。

### 4.6 版本语义：newer supersedes older，trail 不删

- `MEMORY.md` 只保留**当前有效**的结论（curated 层）；
- `~/memory/YYYY-MM-DD.md` 保留**当日原始记录**（trail 层），追加写，不改写历史；
- 旧 claim 被取代时，`memory_explain` 仍能查到"被谁取代/取代了谁"的链条。
- 类比：git 里 HEAD 永远是最新，但历史提交都在。

---

## 5. 生命周期与一致性模型

```
┌──────────────────────────────────────────────┐
│ runtime（注入 / watcher / 索引） │
└──────┬───────────────┬───────────────┬─────────┘
│ │ │
会话启动注入全文 磁盘变更→diff注入 维护 bank/index 检索索引
│ │ │
┌──────────────────▼───────────────▼───────────────▼──────────────────┐
│ agent 会话内行为 │
│ 读：注入快照（快）→ memory_search（全）→ memory_get（精读）→ rg兜底 │
│ 写：先读磁盘 → muse.edit 局部更新 → 写成功才承诺 → 冲突调和 │
└──────────────────┬──────────────────────────────────────────────────┘
│ 互补，不互相替代
┌──────────────────▼──────────────────────────────────────────────────┐
│ 后台 jobs（对话之间） │
│ upkeep → MEMORY.md / relationships → people/groups / dreaming → │
│ dreams + ALIGNMENT_SYNTHESIS / idea / studying / skill review │
└─────────────────────────────────────────────────────────────────────┘
```

三层存储：

1. **Curated 层**（`MEMORY.md`）：当前有效的精选结论，短、准、常读（每轮注入）。
2. **Trail 层**（`~/memory/YYYY-MM-DD.md`、`~/dreams/`）：原始记录，只追加，支撑 provenance
与"当初为什么这么记"的追溯。
3. **Index 层**（`~/memory/bank/`、`~/memory/index/`）：检索引擎，runtime 拥有，agent 只读。

一致性取舍（实测行为）：**最终一致，不追求强一致**。
注入快照可滞后、检索结果可滞后；用"读-改-写前先读磁盘"和"冲突时以最新证据为准"
两条规则在应用层兜底，而不是在存储层加锁。

### 场景速查表

| 场景 | 章节 | 一句话 |
|---|---|---|
| 会话启动时文件如何装配 | 2.2 场景 A | 骨架→standing 全文注入→运行时状态→用户消息；subagent 继承完整 transcript |
| 文件在对话中被改了 | 2.3 场景 C | watcher 数秒内注入 unified diff，agent 无感同步（2026-09-30 实测） |
| 长会话压缩后 | 2.5 场景 H | 压缩对话不压缩记忆；standing 按磁盘最新版重注 |
| 收到用户请求先干什么 | 3.2 场景 D | 检索决策树：豁免三种情况，其余按主题选工具 |
| side chat 怎么办 | 3.5 场景 G | 独立 transcript＋可选独立 MEMORY；检索到≠可透露 |
| 一条记忆的一生 | 4.2 场景 B | 检索→实查→落笔前写盘→upkeep 去重→被检索使用→被新 claim 取代 |
| dreaming 一夜干什么 | 4.3 场景 F | 找 rupture→写反思→合成带证据引用的对齐综述→次日注入调参 |
| 记错了怎么改 | 4.4 场景 E | 修正归因不删教训，保留"此前误诊，已纠正"痕迹 |

---

## 6. LCA 分层映射

LCA 现有分层：contracts → infrastructure → cognition → runtime → agent。

| LCA 层 | Muse 实现中对应的部分 | 说明 |
|---|---|---|
| contracts | 文件格式约定 | Markdown＋HTML 注释元数据；`INDEX.md` 目录索引约定；provenance 后缀格式；`## Facts/Preferences/Commitments` 分节约定。都是约定，不是代码。 |
| infrastructure | 文件系统布局、watcher、检索引擎 | `~` 下固定目录树；文件变更 watcher 与 diff 注入；`bank/`/`index/` 检索索引（runtime 拥有）。LCA 落地时：目录即 schema，watcher 即变更事件源。 |
| cognition | 检索、consolidation、反思 | `memory_search/get/explain` 检索语义；upkeep 的"新 claim 取代旧 claim"；dreaming 的复盘与 alignment 合成。注意：**consolidation 是后台批处理，不在对话主路径里**——主路径只读快照、只写增量。 |
| runtime | 上下文组装 | 会话启动时的注入、compaction 后的重注、diff 的实时注入、注入副本滞后的显式声明。对应 LCA 的"Continuous Control Plane"思想：上下文不是一次拼好的，是持续维护的。 |
| agent | 行为规范 | 写进系统提示的硬规则：每轮强制检索、落笔前写盘、读-改-写、冲突调和、红线（密钥不进记忆）。**规则即代码**：这些行为不靠模型"自觉"，靠 prompt 里的可执行指令＋工具。 |

场景到分层的映射（读场景时对照）：

- 场景 A（启动装配）→ runtime；场景 C（diff 注入）→ infrastructure＋runtime；
- 场景 D（检索决策树）→ agent＋cognition；场景 G（side chat 隔离）→ contracts＋agent；
- 场景 B（记忆生命周期）→ agent＋cognition；场景 F（dreaming）→ cognition；
- 场景 E（冲突调和）→ agent；场景 H（compaction）→ runtime。

给 LCA 的最小可行建议（按优先级）：

1. **先做"文件即数据库"**：Markdown 文件＋固定目录＋`INDEX.md`，零依赖，可被 git 版本化、可被用户直接编辑。这是整个体系里 ROI 最高的单点。
2. **prompt 里写死行为规则**，而不是指望模型记住：检索义务、写盘时机、红线清单，全部进系统提示。
3. **consolidation 异步化**：对话主路径只做"读快照＋写增量"，合并/去重/取代放后台任务。主路径保持快，后台保证最终一致。
4. **每条记忆带 provenance**：`来源＋触发＋日期` 三元组，解释性、纠错、可信度都从这里长出来。
5. **承认并设计 staleness**：注入的是快照不是 live 视图；用"写前重读＋冲突时最新证据为准"兜底，不要试图做分布式锁。

## 7. 黑盒边界（诚实标注）

以下为观察到的行为，非实现断言；LCA 参考时请按"行为契约"而非"实现细节"理解：

- 注入的具体实现（runtime 内部）不可见；可见的是注入位置、标记格式、刷新时机。
- `bank/`/`index/` 检索索引的内部结构不可见；可见的是"agent 可读不可写"和"结果可能滞后"。
- 后台 jobs 的调度器实现不可见；可见的是频率、输入输出、写入目标（来自官方文档
`~/docs/self_improvement.md` 与实测一致）。
- 定时任务（cron）与 hooks 是另一套机制（`~/workspace/cron.d/`、`~/hooks/`），
本文档不展开；它们与记忆系统的交集是：worker 的产出经由同样的"写盘"规则进入 trail 层。

---

*快照文件：*
- [MEMORY-snapshot-2026-09-30.md](MEMORY-snapshot-2026-09-30.md) — MEMORY.md 全文快照
- [ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md](ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md) — ALIGNMENT_SYNTHESIS.md 全文快照
