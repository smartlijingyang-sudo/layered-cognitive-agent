# ADR-0268 — 上下文总线、四类异步执行体与 cron 即将到来投影

## 状态

**Proposed — 2026-10-02**

> **一句话**：模型只有一条总线，就是上下文里的文本。四类异步执行体都是发出后由 runtime 回注，模型不轮询。定时任务是其中独立的一种。右侧「即将到来」读服务端算好的下次触发，不在浏览器里推算。

**Extends**：

- [ADR-0255](0255-muse-production-runtime-full-reference.md) 是 Muse 工具与 cron 的参考清单。本 ADR 决定 LCA 采纳其中哪一段、以什么名字落地。
- [ADR-0256](0256-tool-namespace-taxonomy.md) 的 8 域继续有效。本 ADR 只增加 `lca` 与 `cron` 两个域，不把 `file` / `shell` / `memory` 改名。
- [ADR-0257](0257-delegation-context-inheritance-and-verification.md) 继续管团队委派信封。本 ADR 的 cron worker 与 subagent 都不是那条信封。
- [ADR-0263](0263-routine-scheduling-mutual-exclusion-and-self-healing.md) 的锁、stale 收割、失败隔离继续有效。本 ADR 只修订 C1 里「忙则 SKIP、不排队」对 `CronJob` 的适用，见 §8。0263 文件不改。
- [ADR-0264](0264-proactive-messaging-pipeline.md) 继续管预先写好的主动消息。它的 `SILENT` 是裁决函数的返回值。本 ADR 的静默是 handoff 轮上的工具调用，两者不合并。

**不 supersede**：ADR-0047 的工具回注、ADR-0093 的工作队列、ADR-0187 的助理任务字符串、ADR-0248 的例程预算闸。它们保持原职责。本 ADR 不把它们变成 cron。

---

## 0. 接任务前 7 问

1. **问题是什么？** 用户要在对话右侧看到一次性提醒，以及每周、每天、每小时的任务，能读下次触发时间，能改。用户在对话里提到提醒时，助理要能建任务。只答应一个时刻的，只跑那一次。到点要有人干活。干完的例行结果默认不打断用户。用户没看到气泡时，仍能确认任务跑过。
2. **受影响的事实或契约是什么？** 任务定义、下次触发、worker 能看见的上下文、handoff 文本、静默信号、投递回执、右侧列表的字段闭集。
3. **唯一真值在哪里？** 任务定义在 `CronJob` 存储。`next_run` 是纯函数，调用方传入 `now`。某次运行的结果是只追加的 run 记录，每条结束的 run 都有投递回执。卡片是这两份事实的投影。列表投影不带 schedule 原字段。
4. **改变哪个边界？** 工具命名空间增加 `lca` 与 `cron`。调度与执行与投递分成三个所有者。右侧栏增加一个只读投影加用户编辑入口。0263 的「不排队」对 `CronJob` 改为「运行中的留下，排队只留最新一次」。
5. **现有 Protocol / ADR 能否表达？** 不能。0255 是参考，不是 LCA 契约。0264 在工人报告出来之前就决定说不说。`RoutineSpec` 允许 cron 表达式和间隔同时存在或同时为空，调度器不读这两个字段。`JobSpec.schedule` 是不解析的字符串，HTTP 固定 501。三套记录都没有对客户端暴露的 `next_run`。
6. **失败、重试、恢复和幂等语义是什么？** 见 §7、§8、§9。runtime 失败和超时可按 `max_retries` 重试。worker 自己报告没做完，不重试。同一 id 的 `cron.add` 不覆盖。模型删任务或改周期时，写操作挂起，审批结果回注之后才落盘。未点选则存储不变。
7. **如何验证？** §14。

---

## 1. 上下文是唯一总线

模型没有供 runtime 写入的内存变量。用户消息、工具结果、handoff、记忆摘录、文件内容，都变成注入上下文的文本。模型的下一步只根据这些文本决定。

落盘文件是总线之外唯一扛过压缩的状态。`CronJob` 文件、`MEMORY.md`、run 记录在压缩后仍在。没写入这些存储的内容，压缩后不可恢复。

因此：

- 下次触发时间写在读取投影里，不写在对话里。
- worker 报告先落入 run 记录，再作为文本注入父轮。注入失败可以重放，不依赖父对话还留着原文。
- 记忆的写入是对 `MEMORY.md` 的文件编辑。本 ADR 不新增 `memory_write`。读记忆仍走 ADR-0256 的 `memory` 域与 ADR-0260 的写盘回执。

---

## 2. 工具调用是请求，然后回注

模型发出一次工具调用后，本轮停在这次调用上。runtime 执行，把结果作为新的工具消息注入，模型看到结果再决定下一步。模型不在同一次补全里假定执行已经完成。

这条规则覆盖同步工具，也覆盖 §3 的四类异步执行体。异步执行体的差别只有两处。谁触发。执行体是什么。回注的形态都是一条后到的消息。模型不轮询。

审批卡片是同步阻塞的一种回注。runtime 挂起这次调用，用户点选之后，点选结果作为工具结果注入。未点选之前，这次调用没有结果，存储也不变。删数据和改周期走这条路径，见 §9。

### 2.1 结构保证

下面五条在模型不遵守 prompt、或调用方按最省事的方式接线时仍然成立。只写进 prompt 的句子不算这些语义。

| 语义 | 代码结构 |
|---|---|
| `lca.nothing_to_do` 只在 handoff 轮可用 | 组装用户轮的 wire 时不放入该工具。模型发出调用也只得到错误回注。见 §4 |
| 下次触发由服务端计算 | `cron.list` 只给 `next_run_local` 字符串、`schedule_label` 字符串和 `due`。不给 `schedule`、`timezone`、`anchor_at`、`every_seconds`、`at`。见 §5、§10 |
| 改周期或模型删除要等批准 | 写发生在被挂起的那次工具调用里。审批结果回注之前写函数不被调用。未点选不是「模型记得先别写」。见 §9 |
| worker 看不见父聊天 | 组装 worker 上下文的函数不接收父 transcript。调用点没有这个参数可传。见 §3.4 |
| 到点必定起一个属于这次触发的 run | 调度路径不进 inflight 合并，或合并键带上会话。「同一段文字」不足以吞掉一次调度触发。见 §8.1 |

服务端不解析用户原话，也不在 `oneshot` 与周期 `kind` 之间互改。因此「这句话是在说每天还是在说明天」不是结构保证。模型若把「明天 9 点」写成 `daily`，存储会按 `daily` 保存。端到端「每天 9 点提醒我」仍是一次 `cron.add` 就出现卡片，不再要求第二次点选。已经落盘的 `oneshot` 要改成周期时，才由上表第三条挡住。

---

## 3. 四类异步执行体

四类都遵守 §2。上下文种子、失败和隔离各不相同。禁止用其中一类的实现去充当另一类。

| 执行体 | 触发 | 执行的东西 | 出生时看见什么 | 完成时回注什么 |
|---|---|---|---|---|
| exec 后台 | `background: true`，或超过 `yield_ms`（默认 10000 毫秒） | 该 agent 作用域内的一个 OS 进程 | 无模型上下文 | 退出码和完整 stdout/stderr |
| subagent | `subagent.spawn` | 独立 turn loop 的 agent | 出生时刻父上下文的冻结副本 | 该 agent 的最终回复 |
| browser task | `browser.spawn_task` | 浏览器操作 agent 加一台持久 Chromium | 任务书。不含父聊天记录 | 完成、卡住或待审批的 handoff |
| cron worker | 调度器到点 | 独立 turn loop 的 agent | 任务 `body` 加产品上下文。不含父聊天记录 | 见 §6。`space_action` 成功时不回注 |

### 3.1 exec 后台

立刻返回 `session_id`。stdout/stderr 由 runtime 缓冲。`process.log` 读这份缓冲。`process.write` 写 stdin。`process.send_keys` 只在 PTY 模式发送终端按键。`process.poll` 在 timeout 内等待新输出。`process.kill` 杀掉该会话的进程树。`process.clear` 丢弃已结束会话的缓冲。

会话按 agent 隔离。子 agent 看不见父的后台进程，父也看不见子的。VM 重启或替换后，这些进程不恢复。

远端机器上用 `setsid`、`nohup` 挂起的进程不属于本执行体。ssh 会话断开后的存活问题由那条远端命令自己处理。

定时任务禁止用常驻 exec 充当。时钟在 cron 服务里，不在一个 shell 循环里。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 exec 后台。现有 `shell` 域工具保持 ADR-0256 的职责。

### 3.2 subagent

`subagent.spawn` 立刻返回 agent id。runtime 复制父在出生时刻的完整上下文。之后父的新消息、新工具结果不进入子。子跑自己的 turn loop。

子的工具集与父相同，除三类禁令。不得启动 browser task。不得构建 artifact。`max_depth` 为 2。父是 0，子是 1，孙是 2。深度 2 再 spawn 被拒绝。

子的 exec 后台会话和记忆写入在子自己的作用域。子结束（完成、失败、`close`）时，runtime 把最终回复作为 handoff 注入父。

`subagent.send` 只表示已入队。子当前 turn 结束后才看得到。`interrupt: true` 先打断当前 turn，再投递。`subagent.list` 的状态闭集是 `running`、`done`、`interrupted`、`failed`。`running` 带已运行时长和上次活跃时间。

这条执行体不替代 ADR-0257。团队成员、peer、接力委派仍用 0257 的信封（standing 全量、父 turn 摘要、记忆投影），不复制完整父 transcript。`subagent.spawn` 若将来实现，是另一个入口，不改 `MemberInvoker`。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 `subagent.spawn`。

### 3.3 browser task

`browser.spawn_task` 接收一份自包含任务书，里面有目标站点、要做的事、成功标准。它不是通用子 agent。执行体是浏览器操作 agent，加上该用户 VM 里的一台真实 Chromium。profile 持久。cookie、登录态、tab 跨 task 保留。

决策循环是看截图和页面结构，再点击或填写，再看。遇到 CAPTCHA、登录墙或支付确认时暂停，handoff 给父。父用 `browser.steer_task` 继续。`browser_task_id` 与 subagent id 是两套标识。用错 id 拒绝。

支付、发消息和删除走审批卡片。用户可以观看并接管该浏览器窗口。

`browser.search` / `browser.open` 只读页面文本，不能点击、填写、登录。需要动手的操作必须走 `spawn_task`。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 browser task。

### 3.4 cron worker

调度器到点，用任务的 `body` 原文启动 worker。worker 与父隔离。它看不见父的聊天记录、工具结果和 birth 之后的新上下文。

组装函数的参数只有 `body` 和产品上下文。产品上下文是 `job_id`、`owner`、workspace 路径、timezone、`report`、`delivery_targets`、本次 `run_id`。参数列表里没有父 transcript、父工具结果或 birth 之后的父消息。测试钉住这个签名。函数原样传入存储里的 `body`，不把父对话附加进去。`cron.add` 时若调用方把聊天抄进 `body`，那段文字会随任务定义进入 worker。那是定义内容，组装函数仍然没有父轮可读。

`execution.kind = agent` 时，worker 跑完交出 `worker_message`。runtime 把它包成 §6 的 handoff，注入父的下一轮。父按 §6 决定说不说。

`execution.kind = space_action` 时，worker 只更新指定 artifact。成功不产生 handoff，不产生聊天气泡。runtime 失败或超时在重试耗尽后仍产生 handoff，否则刷新失败对父不可见。

---

## 4. 两个新命名空间

`lca` 是运行时控制，不是第二套文件或 shell 工具，也不是 `smart`。

| 工具 | 何时在 wire 上 | 参数 | 效果 |
|---|---|---|---|
| `lca.nothing_to_do` | 仅当本轮输入是 §6 的 handoff，且本轮没有更新的用户消息 | 无 | runtime 结束本轮，不写 assistant 可见气泡 |

用户消息触发的轮次上，这个工具不在 wire 上。模型若仍发出该调用，runtime 回注错误，本轮继续，不得把它当成静默。模型什么都不写，也不是静默。runtime 仍等待可见回复或这个工具。

`cron` 是调度服务，DEFERRED，经 `tool_search` 加载。VM 里没有 crontab。

| 工具 | 效果 |
|---|---|
| `cron.add` | 新建。id 已存在则返回现有记录，不修改 |
| `cron.view` | 按 id 返回全量定义和只追加的 run 记录。给模型工具，不给即将到来 tab |
| `cron.update` | 模型路径先 `cron.view` 再整份覆盖。卡片路径只提交用户改过的字段，由服务端合并。见 §9 |
| `cron.remove` | 删除定义与尚未注入的 handoff。不删除已结束的 run 记录。模型路径走 §9 挂起 |
| `cron.list` | 返回该 owner 的 §10 投影。含 `next_run_local` 与 `schedule_label`。不含 schedule 原字段 |

`file`、`shell`、`memory`、`skill` 的现有工具不改名，不在 `lca` 下再注册一份。

---

## 5. CronJob

一份定义，一种 schedule。禁止「cron 表达式和间隔可以同时有，也可以同时没有」。一次性提醒是第五种 schedule，不是每天的特例。

```python
class OneShotSchedule(BaseModel):
    kind: Literal["oneshot"]
    at: datetime  # aware。只在这一刻触发一次

class IntervalSchedule(BaseModel):
    kind: Literal["interval"]
    every_seconds: int  # > 0

class HourlySchedule(BaseModel):
    kind: Literal["hourly"]
    minute: int  # 0–59。每小时的这一分钟

class DailySchedule(BaseModel):
    kind: Literal["daily"]
    hour: int    # 0–23
    minute: int  # 0–59

class WeeklySchedule(BaseModel):
    kind: Literal["weekly"]
    weekday: int  # 0 = 周一 … 6 = 周日
    hour: int
    minute: int

class AgentExecution(BaseModel):
    kind: Literal["agent"]

class SpaceActionExecution(BaseModel):
    kind: Literal["space_action"]
    artifact_id: str

class ChatDelivery(BaseModel):
    chat_id: str

class CronJob(BaseModel):
    id: str
    title: str
    schedule: OneShotSchedule | IntervalSchedule | HourlySchedule | DailySchedule | WeeklySchedule
    timezone: str  # IANA。调用方没给时，服务端填入该用户的当前 timezone。用户没有 timezone 则拒绝，不用机器时区，也不写 Asia/Shanghai
    body: str
    execution: AgentExecution | SpaceActionExecution
    delivery_targets: tuple[ChatDelivery, ...]
    report: Literal["always", "anomalies_only"]  # 缺省 anomalies_only
    owner: str
    created_chat_id: str
    anchor_at: datetime  # aware。服务端在 cron.add 时写入。调用方不能传。间隔的相位从这里算
    enabled: bool
    max_retries: int  # >= 0。缺省 0
    timeout_seconds: int | None  # None 表示按 §7 推导
```

约束：

- `agent` 的 `delivery_targets` 至少一条。`space_action` 的 `delivery_targets` 必须为空。
- `created_chat_id` 是侧聊时，每条 `delivery_targets.chat_id` 必须等于 `created_chat_id`。否则 `cron.add` 和 `cron.update` 拒绝。侧聊任务不能投到主聊天，也不能在主聊天里创建。
- `owner` 被删除时，其下 `CronJob` 定义与未注入 handoff 一并删除。已结束的 run 记录保留。没有按 `run_id` 删除或改写回执的入口。
- `report` 写进 worker 的产品上下文和 handoff 的 `task_context`。runtime 不根据 `report` 丢弃 handoff。说不说由父在看到 `worker_message` 之后决定。
- 用户只给出一个时刻、没有给出重复规则时，调用方应传 `oneshot`。服务端不把 `oneshot` 展开成每天，也不把 `daily` 收成 `oneshot`。服务端不从中文判断种类，所以这一条对「新建时选错种类」还不是结构保证。已落盘的 `oneshot` 改成周期仍按 §9 挂起。
- `timezone` 缺省取该用户当前的 client timezone（与 developer timestamp 上的 `client_timezone` 同一来源）。取不到就拒绝这次 `cron.add`。`ZoneInfo` 不能加载的名字同样拒绝。ADR-0264 的 `ProactivePolicy.timezone` 仍可以有自己的缺省，本字段不借用它。

`next_run` 是纯函数。它不读时钟，也不读 `enabled`。调用方传入任务定义、`last_run` 和 aware 的 `now`。同一输入两次调用，结果相同。naive datetime 拒绝。timezone 非法或 `ZoneInfo` 不能加载时，返回类型化拒绝，不抛裸异常。

```python
class NextFire(BaseModel):
    upcoming: datetime | None  # 有值则严格晚于 now，且是该 timezone 的 aware datetime
    due: bool                  # 这一刻要触发。due 本身不是时间戳
```

`upcoming` 有值时必有 `upcoming > now`。函数不返回早于或等于 `now` 的 datetime。到点用 `due`，不把过去的 `at` 交给客户端。

- 一次性，已有 `last_run`。`upcoming` 为空，`due` 为假。
- 一次性，没跑过且 `at > now`。`upcoming` 等于 `at`，`due` 为假。
- 一次性，没跑过且 `at <= now`。`upcoming` 为空，`due` 为真。只补跑这一次，不改成周期。
- 小时、日、周。`upcoming` 是严格晚于 `now` 的下一档墙钟。`now` 正好落在触发点上时 `due` 为真，`upcoming` 取再下一档。早于 `now` 的档不补跑。
- 间隔。相位从 `anchor_at` 起。`last_run` 为空时，第一候选是 `anchor_at + every_seconds`。创建当时 `anchor_at` 等于传入的 `now`，所以第一候选晚于 `now` 一个间隔。`last_run` 有值时，第一候选是 `last_run + every_seconds`。候选早于 `now` 时按 `every_seconds` 前进，直到严格晚于 `now` 的一档作为 `upcoming`。某一档等于 `now` 时 `due` 为真，`upcoming` 再过一个 `every_seconds`。

墙钟缺口与歧义：

- 春令时缺口里不存在的本地时刻不作为结果。日、周任务跳过该日，取下一周期里真实存在的同一墙钟。小时任务取缺口之后的下一档真实分钟。
- 秋令时回拨造成的歧义时刻取 `fold=0`。
- 间隔按 `every_seconds` 的绝对时长前进。
- 调用方构造的 `at` 若落在缺口里，在进入 `next_run` 之前就类型化拒绝。

`upcoming` 有值时，`next_run_local` 为 `YYYY-MM-DD HH:MM`。`enabled = false` 不改变纯函数的结果。调度器看到 `enabled = false` 时不入队。投影仍给出 `next_run_local`，并把列表上的 `due` 写成假，同时标停用。已完成的一次性任务不进入即将到来。`due` 为真且 `upcoming` 为空的未跑一次性任务仍在列表里，带 `due: true`，不带 `next_run_local`。

存储只有一个写入者。路径是助理 home 下的 `cron/<job_id>.json`。定义用原子替换写入。run 记录追加在 `cron/<job_id>/runs/`。`ProactiveJob`、`RoutineSpec`、`JobSpec` 都不是这份存储。

`RoutineSpec.cron_expr` 与 `interval_seconds` 能否删除，由 §14 第 0 条决定。全仓确认除模型定义和测试夹具外没有读写，才在同一次实现里删掉这两个字段，不留双字段兼容。检索到生产读写，字段留在原地，这一条不实施。例程若仍需要 ADR-0248 的预算闸，引用 `CronJob.id`，不自带第二套钟。`GET/POST /v1/assistants/{id}/jobs` 在接到 `CronJob` 存储之前保持 501。接到之后，该路由读写 `CronJob`，不再接受未解析的 schedule 字符串。

---

## 6. Handoff 与说不说

`agent` 执行，以及 `space_action` 在重试耗尽后的 runtime 失败，产生一条 handoff。成功的 `space_action` 不产生。

```python
class ScheduledHandoff(BaseModel):
    job_id: str
    run_id: str
    task_context: CronJob  # 触发当时的定义副本
    worker_message: str
    delivery_targets: tuple[ChatDelivery, ...]
    outcome: Literal["completed", "runtime_failure", "timed_out"]
```

runtime 把这条记录作为 developer 消息注入父的下一轮。父不订阅、不轮询。注入前记录落在 run 日志里。父对话被压缩不影响重放。

父的决定：

| 条件 | 父必须做的 |
|---|---|
| `report = always`，或用户在 `body` / 当时对话里明确要求每次都收到 | 在回复里写出报告 |
| `worker_message` 里有新的失败、变化或需要人处理的事 | 写出报告 |
| 例行无异常，且 `report = anomalies_only` | 调用 `lca.nothing_to_do` |

写出报告时，正文进入 `delivery_targets` 里的 chat。多个目标各写一份。目标 chat 不存在则该目标失败，其他目标仍写，run 记录记下每个目标的结果。

```python
class TargetReceipt(BaseModel):  # extra="forbid"
    chat_id: str | None
    state: Literal["delivered", "failed", "silent", "not_sent"]

class CronRun(BaseModel):  # extra="forbid"
    run_id: str
    outcome: Literal["completed", "runtime_failure", "timed_out", "superseded"]
    receipts: tuple[TargetReceipt, ...]
    finished_at: datetime | None
```

`ScheduledHandoff` 同样 `extra="forbid"`。缺字段在契约测试里失败。

worker 结束时先追加 run，`outcome` 已定。`receipts` 在投递决定写下之前可以为空，`finished_at` 仍记下 worker 结束时间。空的 `receipts` 表示未决，读出来就是未决，不是成功，也不是缺键。handoff 轮结束时 `receipts` 必须非空，否则该轮不能标结束。`superseded` 和成功的 `space_action` 没有父轮，追加时就写上 `not_sent`。

| `state` | 何时写 |
|---|---|
| `silent` | 父调用 `lca.nothing_to_do` 成功。一条回执，`chat_id` 为空。未发气泡 |
| `delivered` | 该目标 chat 已写入报告。每个写成功的目标一条 |
| `failed` | 该目标应写但没写成。每个失败目标一条。其他目标仍按自己的结果写 |
| `not_sent` | 成功的 `space_action`，或 `outcome = superseded`。一条回执，没有父投递 |

卡片用最近一条 run。`silent` 必须带着 `finished_at`。只有 `outcome`、没有回执的最近一条，卡片显示未决，不显示成功。

### 6.1 回执的关闭

§6 要求 handoff 轮结束时 `receipts` 非空，§12 写着 run 记录只追加。两句同时成立的读法只有一种：一次到点追加一条记录，那条记录上有一个字段从未决变成已决，恰好一次。这是补完一条事实，不是修订一条事实。

**所有者。** 追加发生在 worker 结束时，写 `run_id`、`outcome`、`finished_at`，`receipts` 为空。关闭发生在 handoff 轮结束时，只写 `receipts`。`run_id`、`outcome`、`finished_at` 一经追加不再改变。除这两次写入之外没有第三种写。

**关闭之前先落 dispatch 身份。** `CronRun` 增加 `handoff_run_ids: tuple[str, ...]`，一个投递目标一个 id，在起 handoff run 之前写入。顺序是先写盘再起 run。反过来不成立：先起 run 再写盘，进程在两步之间死掉，重启后读到一条既未决又没派过 run 的记录，重新推导会再派一次，用户收到两条同样的提醒。写在前面的那个身份让重复投递在结构上不可能，而不是靠重试逻辑小心。

`handoff_run_ids` 缺省为空，读作「还没派」。既有记录全部落在这个读法上，不需要迁移脚本。

**恢复。** 未决且 `handoff_run_ids` 非空，含义是派过了还没关，恢复路径读那些 run 的结果补写 `receipts`，不再派新 run。未决且 `handoff_run_ids` 为空才是待派。§8.1 的等待位按这两个条件区分，不按时间。

**关闭幂等，但不随意。** 用同一组 `receipts` 再关一次是无操作，返回已有值。用不同的一组关第二次是拒绝，一次到点有两个投递决定是矛盾，不是更新。

**存储接口。** `CronStore` 增加一个方法：读记录、判空、原子替换写回。不新增记录类型，不新增文件，不新增第二份 run 事实。

**为什么不追加第二条记录来承载回执。** §6 的「卡片用最近一条 run」会出现两个候选，`last_delivery` 的投影要跨两条记录合并，`cron.view` 的只追加语义会让同一次到点出现两行。一个字段的单次补完比两条记录的合并规则便宜。

**为什么不在 worker 结束时就写回执。** 那时投递还没发生，写下的任何值都是猜的。§6 已经把空 `receipts` 定义为未决，猜一个值等于把未决伪装成已决。

---

## 7. 超时与重试

自然间隔 `gap_seconds`：

| schedule | gap_seconds |
|---|---|
| oneshot | 无。未声明 `timeout_seconds` 时，超时为 86400 |
| interval | `every_seconds` |
| hourly | 3600 |
| daily | 86400 |
| weekly | 604800 |

有自然间隔时，实际超时秒数是 `min(86400, max(timeout_seconds 或 gap_seconds, gap_seconds))`。未声明超时时，周任务的 worker 上限是 86400 秒，不是 7 天。一次性任务只用 `min(86400, timeout_seconds)`，没声明则是 86400。

超时杀掉 worker，记 `outcome = timed_out`。

`max_retries` 只对 `runtime_failure` 和 `timed_out` 生效。worker 完成并交来「没做完」的 `worker_message`，记 `completed`，不重试。已经落到 artifact 的 `space_action` 不因为同一次 run 再执行一遍。

重试使用同一个 `run_id` 的尝试序号。耗尽后注入一条 `outcome` 为最后一次失败的 handoff。

---

## 8. 同一任务重叠

修订 ADR-0263 C1 对 `CronJob` 的「未取得锁则 SKIP、不排队」。锁、心跳、stale 收割、单任务失败不杀 tick，仍按 0263。

同一 `job_id`：

- 已有运行中的 run 时，新的到点不杀掉它，也不平行再起一个 worker。
- 排队槽只有一个。新的到点写入这个槽。槽里更早的待跑项取消，记 `superseded`，回执为 `not_sent`。
- 运行中的 run 结束后，若槽里有待跑项，立刻起那一次。没有则等待下一次 `due` 或 `upcoming`。
- `superseded` 不产生 handoff，不重试。

### 8.1 与用户轮重叠

上面的排队槽按 `job_id` 互斥。同一个会话里还可能有用户自己发起的 run，那是另一个所有者，不进这个槽。规则按会话再收一次。

**一个会话同时只有一个活 run。** 到点时先判会话是否空闲。判活分两段：`get_latest_for_topic(chat_id)` 取最近的 `run_id`，再问 run registry 该 run 的 `status` 是否仍在 `pending` 或 `running`。只读第一段会得出错的答案，因为 `lca_running_operations` 没有状态列，行也不删除，最近一行可能属于早已结束的 run。内核重启后 registry 为空，判活结果是空闲，这是对的，那个 run 随进程一起结束了。

会话忙时不起第二个 run，这次 handoff 进该会话的等待位。等待位每会话一个，语义与上面的排队槽一致：新的到点覆盖更早的待投递项，被覆盖的记 `superseded`，回执 `not_sent`，不产生 handoff，不重试。会话空闲后，等待位上的 handoff 起 run。

等待位是进程内的派生态，不是新存储。它的真值是 run 记录里 `receipts` 为空这一条，重启后由下一次 tick 重新导出。§6 已经规定空 `receipts` 读作未决，这里只是给它加一个消费者。

**为什么不允许两个 run 并行同一会话。** 浏览器按 `operationId` 归档消息，`operationId` 就是 `run_id`，而 `topicId` 只在 `agent_runtime_init` 上出现一次，前端没有这个事件的分支。断线重连走 `GET /v1/topics/{topic_id}/running-op`，它返回该 topic 最近一行。第二个 run 插入行之后，重连挂到它上面，用户自己那一轮的流在 UI 里就断了。

**等待有上限。** 上限取 §7 已经算出的那个超时值，即 `min(86400, max(timeout_seconds 或 gap_seconds, gap_seconds))`；`oneshot` 没有自然间隔，上限是 `min(86400, timeout_seconds)`。到期仍未投递的 handoff 记 `not_sent`，run 记录关闭，不再等待。不新增配置项。用户仍能用 `cron.view` 读到这条记录。

**调度触发的 run 不参与 inflight 合并。** 合并键由 `user_text`、`mode`、`attachment_ids`、`agent_id` 组成，不含会话。周期任务的 `user_text` 每次都相同，命中合并时不起新 run，handoff 就此消失，而 run 记录仍被追加成未决。一次调度触发是一条独立事实，带自己的回执，因此它要么绕过合并，要么合并键带上会话。见 §2.1。

本小节不新增 `CronRunOutcome` 成员，不新增事件词表条目，不新增存储。`superseded` 与 `not_sent` 沿用 §6 的定义。

0264 的 `ProactiveJob` 仍按自身的 tick 与裁决。它不进入这个排队槽，也不出现在「即将到来」。

---

## 9. 谁可以改任务

| 动作 | 谁 | 门槛 |
|---|---|---|
| `cron.add`，用户给了一个时刻，没给重复规则 | 模型 | 应传 `oneshot`。直接写入。卡片上立刻可见 |
| `cron.add`，用户给了重复规则（每小时、每天、每周、每隔） | 模型 | 应传对应的周期 schedule。直接写入。卡片上立刻可见。不再点一次审批 |
| `cron.add`，用户没给时刻也没给周期，模型要建周期任务 | 模型 | 审批卡片。未点则不建。服务端看不到中文原话，这一行靠调用方遵守，见 §2.1 |
| 把已有 `oneshot` 改成周期，或改周期档位、间隔、`timezone` | 模型 | 这次 `cron.update` 挂起。点选结果回注之后才调用写。点同意后服务端重写 `anchor_at` 并清掉 `last_run`。点拒绝则错误回注，定义不变 |
| 同上 | 卡片上的用户 | 用户的保存就是批准，不再弹卡片。请求里带的是用户新填的 schedule，不是从列表里读回的原字段 |
| 改 `title`、`body`、`report`、`enabled` | 模型或卡片上的用户 | 直接写入。卡片只提交改过的字段，服务端合并进存储的定义 |
| `cron.remove` | 模型 | 这次调用挂起。回注同意后才删定义与未注入 handoff。不删已结束的 run |
| `cron.remove` | 卡片上的用户 | 用户的删除就是批准 |

挂起期间定义不变。十分钟未点选，`cron.view` 仍是旧定义，写函数没有被调用。重复的审批请求以同一 `job_id` 加同一目标定义为幂等键，不叠多张卡片。

服务端按传入的 `kind` 原样保存，不在一次性与周期之间互改，也不从中文原话推断 `kind`。用户只答应一个时刻时，调用方应传 `oneshot`。用户说出重复规则时，调用方应传该周期，并一次写入。这两句对新建还不是结构保证。结构上能挡住的是已落盘定义的改周期和模型删除。

---

## 10. 即将到来

对话右侧有一个「即将到来」tab。它只请求 `cron.list` 的投影，不请求 `cron.view`。浏览器不计算下次触发。保存前不在本地预览下一次时间。请求失败时显示错误，不显示本地猜测的时间。注册点、补丁文件和组件名不属于本契约。

```python
class CronListItem(BaseModel):  # extra="forbid"
    id: str
    title: str
    schedule_label: str  # 给人读。契约不定义文法。客户端不用它计时
    next_run_local: str | None  # YYYY-MM-DD HH:MM。仅 upcoming 有值
    due: bool
    enabled: bool
    last_run_local: str | None  # 最近一条 run 的 finished_at。没有 run 则为空
    last_delivery: Literal["delivered", "failed", "silent", "not_sent"] | None
```

两个时间字段都为空，表示还没有 run，卡片显示尚未运行。`last_run_local` 有值且 `last_delivery` 为空，表示 worker 已结束、投递未决。多个目标的回执汇总成一个 `last_delivery`。有 `failed` 则为 `failed`，否则有 `delivered` 则为 `delivered`，否则取那一条 `silent` 或 `not_sent`。未决不汇总成这四态。

卡片展示 `title`、`schedule_label`、时间。时间只渲染 `next_run_local`。`due` 为真且没有 `next_run_local` 时，展示服务端给出的到点标记，不展示过去的时刻。`enabled = false` 时列表上的 `due` 为假，仍展示 `next_run_local` 并标停用。最近一条回执按 §6 展示。`silent` 显示跑过的时间，并标明没有气泡。

用户可以改 §9 允许卡片改的字段。改 schedule 时提交用户新填的值。服务端合并后在响应里返回新的 `next_run_local`。卡片不从响应以外的数据重算这个字符串。

已完成的一次性任务不在这张表里。run 记录只追加。卡片显示最近一条。更早的记录留在 `cron/<job_id>/runs/`，`cron.view` 能读到。压缩父对话不删除这些记录。没有气泡不等于没有跑。

---

## 11. 明确不采纳

- 命名空间 `smart`。它不说明调用进了哪一个 runtime。
- 把 ADR-0255 的 15 个 `muse.*` 工具整包复制为 `lca.*`。文件、shell、记忆已经有域。
- 用 `ProactiveJob.content` 充当 worker 指令。那份字符串是投递给用户的正文。
- 在浏览器里用 cron 表达式、`schedule_label` 或本地钟推下次触发。
- 把「明天这个时刻提醒我」写成每天同一时刻。
- 把 `next_run` 的到点结果做成一个早于 `now` 的时间戳。
- 间隔任务在创建后的下一秒就跑。第一次在 `anchor_at` 之后的一个间隔。
- 用 prompt 代替 §2.1 的四条结构。包括「用户提问时别调用静默」「改周期前记得等」「worker 别看父聊天」。
- 用 exec 死循环代替调度器。
- 让 cron worker 复制父聊天。那是 §3.2 的 subagent，而且本 ADR 不在本轮实现它。
- 用 ADR-0264 的 `decide` 在 worker 报告生成之前判定静默。
- 让调度触发的 run 与用户 run 并行同一会话。浏览器按 `operationId` 归档消息，重连只认该 topic 最近一行，第二个 run 会把用户那一轮的流挤掉。见 §8.1

---

## 12. 所有权与外部后果

| 事实 | 所有者 | 外部可见后果 |
|---|---|---|
| `CronJob` 定义 | cron 存储 | `cron.view` 与 worker 的 `body`。列表只有 §10 的投影 |
| `NextFire` | `next_run` 纯函数 | `upcoming` 变成 `next_run_local`。`due` 变成列表上的到点标记 |
| `schedule_label` | cron 存储在读时生成 | 卡片上的人话。不参与客户端计时 |
| run 记录与回执 | cron 存储。一次到点追加一条；`handoff_run_ids` 与 `receipts` 在该条上各补写一次，见 §6.1 | 卡片上的最近一次。更早的仍可 `cron.view`。压缩父对话不删除 |
| handoff 文本 | runtime 注入父的下一轮 | 父能决定说或不说 |
| 可见气泡 | 父的回复 | 出现在 `delivery_targets` 的 chat。回执 `delivered` 或 `failed` |
| 无气泡 | `lca.nothing_to_do`，或 `not_sent` | 该 chat 没有新气泡。`silent` 仍有完成时间 |
| 审批点选 | 用户 | 回注前写函数不调用，定义不变 |

---

## 13. 失败语义汇总

| 事件 | 结果 |
|---|---|
| 未知 timezone、用户没有 timezone 且调用方没传、非法 schedule、`at` 落在时区缺口、侧聊跨 chat 投递 | `cron.add` / `cron.update` 类型化拒绝，存储不变。不抛裸异常 |
| 调用方传入 `oneshot` 或某个周期 `kind` | 原样保存，不互改。服务端不从中文判断该不该是周期 |
| 模型把已有 `oneshot` 改成周期，或改周期、间隔、timezone，或 `cron.remove` | 写挂起。未点选或点拒绝，定义不变 |
| 重复 id 的 `cron.add` | 返回现有记录，不修改 |
| worker 超时 | 杀进程，按 §7 重试或 handoff |
| worker 报告未完成 | `completed`，不重试，handoff |
| 排队槽被更新的到点替换 | 旧排队项 `superseded`，回执 `not_sent`，无 handoff |
| 到点时目标会话有活 run | 不起第二个 run。handoff 进该会话的等待位，空闲后起 run。见 §8.1 |
| 会话等待位被更新的到点覆盖 | 旧 handoff `superseded`，回执 `not_sent`，无 handoff 轮 |
| 会话一直忙到 §7 的超时上限 | handoff 记 `not_sent`，run 记录关闭，等待位清空 |
| handoff 轮结束时 `receipts` 仍为空 | 该轮不能标结束。读出来是未决，不是成功 |
| 持锁进程崩溃 | 按 ADR-0263 stale 收割后，槽里的待跑项可以启动 |
| `nothing_to_do` 出现在用户提问轮 | 工具错误回注，不静默 |
| 父既不回复也不调用 `nothing_to_do` | 本轮不结束为静默。runtime 继续等待 |
| 列表接口失败 | 卡片区显示错误，不显示推算时间 |

---

## 14. 验收

还原靠结构和测试。第 1 条到第 4 条按顺序落地，前一条没绿不做下一条。第 0 条只门控 `RoutineSpec` 两个字段的删除，不挡住第 1 条。

0. 全仓检索 `cron_expr` 与 `RoutineSpec` 的 `interval_seconds`。除 `lca/contracts/models/routine/models.py` 的字段定义和直接构造该模型的测试外，没有生产读写，才允许删除这两个字段。检索到其他生产读写，停止删除，字段保持原样。`ProactiveJob.interval_seconds` 不在这次检索的删除范围内。
1. 五条结构先在代码里成立。测试钉住的是结构。
   - 用户轮的 wire schema 里没有 `lca.nothing_to_do`。
   - `next_run` 无 I/O。时钟由调用方传入。
   - 模型发起的改 schedule、改 timezone、`cron.remove`，审批回注前不调用写函数。
   - 组装 worker 初始上下文的函数参数里没有父 transcript。签名测试拒绝新增这类参数。组装结果等于存储里的 `body` 加上产品上下文，不附加父轮。
   - 调度触发的 run 不被 inflight 合并吞掉。存在相同 `user_text` 的活 run 时，到点仍产生一个新的 `run_id`，且 run 记录与之一一对应。
2. 属性测试与契约测试。
   - 任意合法 schedule、任意 aware `now`，`upcoming` 要么为空，要么严格晚于 `now`。同一输入两次结果相同。非法 timezone、用户没有 timezone、naive datetime、落在缺口里的 `at`，都得到类型化拒绝。
   - 春令时缺口日不返回不存在的本地时刻。日任务与周任务取下一周期里真实存在的同一墙钟。秋令时歧义取 `fold=0`。
   - 一次性且 `at > now` 时，`upcoming` 等于 `at`。一次性且 `at <= now`、没跑过时，`due` 为真且 `upcoming` 为空，`kind` 仍是 `oneshot`。已有 `last_run` 则不在即将到来里。间隔在 `last_run` 为空且 `anchor_at == now` 时，`upcoming == anchor_at + every_seconds`。
   - `ScheduledHandoff` 缺任一字段，契约测试失败。
   - `CronRun` 缺 `handoff_run_ids`，或它不是字符串元组，契约测试失败。缺省是空元组，既有记录不迁移也能读。
   - 关闭回执用同一组值重复调用，返回已有值，记录字节不变。用不同的一组调用，拒绝，记录字节不变。
   - `CronListItem` 缺字段、多字段，或出现 `schedule`、`timezone`、`anchor_at`、`every_seconds`、`at`，契约测试失败。`next_run_local` 与 `upcoming` 的墙钟一致。停用的周期任务仍带 `next_run_local`，列表上的 `due` 为假，并标停用。
   - 用户轮发出 `lca.nothing_to_do`，回注是错误。
   - `CronJob` 拒绝双 schedule、侧聊跨 chat、`space_action` 带投递目标。
3. 故障注入。每增加一种重试或审批语义，就增加对应的注入。
   - worker 跑到一半被杀。按 `max_retries` 重试。耗尽后 handoff 的 `outcome = timed_out`。父结束该轮时 `receipts` 非空。
   - handoff run 已起，进程在关闭回执之前死掉。重启后该记录未决且 `handoff_run_ids` 非空，恢复读那些 run 的结果补写回执，不派新 run，目标 chat 只收到一条。
   - `handoff_run_ids` 写盘失败。不起 run。记录停在未决且身份为空，下一次 tick 重新派。
   - worker 交出「没做完」。不重试。`outcome = completed`。
   - 审批卡片 10 分钟没有点选。定义文件的字节不变。再次 `cron.view` 仍是旧定义。
   - 两个到点同时撞上运行中的 run。旧排队项 `outcome = superseded` 且回执 `not_sent`。无 handoff。运行中的 worker 不被杀。
   - 到点时目标会话有一个 `running` 的用户 run。不起第二个 run。等待位里有这次 handoff。用户 run 的重连仍指向它自己的 `run_id`。用户 run 结束后 handoff 起 run。
   - 同一会话两次到点撞上同一个活 run。等待位只留最新一次，旧的记 `superseded` 且回执 `not_sent`。
   - 会话忙到 §7 的上限。handoff 记 `not_sent`，run 记录关闭，等待位清空。
   - 周期任务的 `user_text` 与某个活 run 完全相同。到点仍产生一个新 `run_id`，run 记录与之一一对应。
   - `cron.list` 失败。前端显示错误，不显示本地猜测的时间，也不用 `schedule_label` 补一个时间。
4. 端到端黑盒，周级探针，不作为每次提交的门槛。用户说「每天9点提醒我」。卡片出现，中间没有第二次点选。mock 时钟到 9 点。worker 跑完。handoff 回到父。无异常。父调用 `lca.nothing_to_do`。卡片显示 `silent` 和这次运行时间。

同一次实现还要满足这些不变量。模型 `cron.add` 与卡片读到的是同一份 `CronJob` 文件。卡片改标题保存后，再次 `cron.list` 读到新标题。右侧 tab 只渲染 `CronListItem`。

§3.1、§3.2、§3.3 的实现不在这四条里。它们的契约以本 ADR 为准，另有实现时不得改种子和回注的形状。

---

## 15. 与现有记录的边界

今天生产路径上没有 tick 调用 `ProactiveScheduler` 或 `RoutineSchedulerService`。助理 jobs 路由返回 501。本 ADR 不把这三套未接线的行为宣称为即将到来的数据源。

即将到来的数据源从本 ADR 被实现的那一次提交开始，只是 `CronJob` 投影。
