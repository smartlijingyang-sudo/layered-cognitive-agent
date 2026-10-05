# 流水索引改行粒度实施计划

> 母体：[语义记忆在线单写者与离线对账归位](../../notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md)
> 来源：[Phase 0 条件二实施计划](2026-10-05-trail-capture-phase0-condition2.md) Task 6 的「检索噪音，需另行裁决」，取候选三
> 前置：条件二六个任务已全部落地（`d272490a8` 至 `abd7b5780`）

## Goal

一次 `memory_search` 命中返回一行流水而不是一整天，且一条事实只返回一行。

实测的当前形状：一句偏好提升之后 `memory_search("简洁")` 返回 3 行，1 行 curated 语义记录加 2 行流水文档，每个流水文档的 `content` 是整天文件原文。`limit=10` 时最坏情况是 10 个整日原文进模型上下文。

生产上已经可观测。运行中的内核（pid 2696579，22:34:23 启动，`--profile profiles/web-assistant.yaml`）加载了条件二的 Task 3（`17496c65f`，22:02）与 Task 4（`4f2a295d1`，22:23），两者都在启动之前提交。`asst_ce7fecd65188` 的索引里目前只有一个文档。

```
search_memory_index(home, "cron")     -> [('trail-2026-10-05.md', 'trail', 623)]
search_memory_index(home, "handoff")  -> [('trail-2026-10-05.md', 'trail', 623)]
search_memory_index(home, "Lee")      -> [('trail-2026-10-05.md', 'trail', 623)]
search_memory_index(home, "简洁")      -> []
```

三个互不相关的查询返回同一个 623 字符的整日原文，因为它是一个文档。查用户姓名 Lee 命中，是因为 cron 文本里有「提醒 Lee：」。623 字符会随当天 cron 探针次数增长。这就是本计划要消灭的形状，且它不是假设。

## 先决发现：流水里已经有第二类内容

写这份计划前查了生产状态，`TrailWriter` 只有一个调用方 `record_turn_trail`，但生产助理 `asst_ce7fecd65188` 的 `memory/2026-10-05.md` 里全部条目都是 cron handoff 文本，没有一条是用户话轮。初次查看时 576 字节两条，第二条在 200 字符处被截断在「决定规则（ADR-0268 §」，即 Task 3 的单行上界生效。

来源是 `lca/domain/cron/handoff_dispatch.py:25` 的 `render_handoff_text`。它拼出的 developer message 成为被派发 run 的 `task`，`phase.perceive.observe` 无条件调 `record_turn_trail`，于是机器文本按用户话轮进了流水。

后果分三档，第一档与第二档已对该生产文件实测。

- 语义污染：暂无。把该文件原样喂给 `parse_trail` 得到 3 行，逐行过 `_trail_episode`，三行都是 `is_preference_statement=False`、`is_explicit_instruction=False`、`matched_style_token=None`，因此 `category=FACT`、`authority=False`、`recurrence` 恒为 1，停在 `ephemeral_fast`，不进 `semantic.json`。
- 检索污染：已有。三行都被索引，`memory_search` 会返回。
- 授权漏洞：未发生但可达。cron 文本若含指令标记加风格词，例如某个 job 的标题是「以后回复要简洁」，`_trail_episode` 会给它 `authority=True` 并首次即永久提升为一条**用户**偏好。`render_handoff_text` 把 `job.title` 与 `worker_message` 原样嵌进文本，所以这取决于用户给 job 起的标题与 worker 写了什么，两者都不受本仓控制。

该文件在本计划编写期间从 2 条长到 3 条，cron 探针在持续写入，所以体积按 job 频率增长，不按用户活跃度增长。

本计划不修这一项，因为它需要一个 run 来源标记，而 `AgentState` 上没有。判别方式只有两种，一种是等 run origin 载体落地（并发会话正在做，`758ce9702` 让 run record 携带 handoff ids），另一种是在 cognition 里嗅探 `[cron handoff]` 前缀，那是跨层耦合 domain 的文本格式，不可取。

因此本计划的范围是把行粒度做对，并把「流水里有机器文本」这件事显式记为待裁决项，不假装它不存在。行粒度不解决它，两类内容在行粒度下同样都被索引。

## Architecture

索引文档的粒度从「一天一个」改为「一行一个」，`doc_id` 为 `trail-<日期>-<内容摘要>`，摘要沿用 `_trail_episode` 已经在用的 `sha256_hex(content, length=12)`。

带日期是为了确定性。摘要不带日期时，同一句话在两天出现会争用同一个 `doc_id`，全量重建按 `list_dir` 顺序遍历会把 `path` 写成最后一天，而增量写入会写成当天，两条路径对同一 `doc_id` 产出不同 `path`，破坏 [条件二计划](2026-10-05-trail-capture-phase0-condition2.md) Task 4 建立的一致性约束。`DiskFileStore.list_dir` 返回 `sorted(...)`，加日期后两条路径逐字段相同。

行抽取不新写一个。`domain/trail.py` 抽出 `trail_lines(text) -> tuple[str, ...]`，`parse_trail` 改为在它之上构造 `TrailEntry`。`_documents` 与增量写入都调 `trail_lines`，「什么算一行流水」只有一个定义。直接复用 `parse_trail` 不行，它要求 `observed_at_ms`，索引不需要时间，传 0 是为了绕签名而撒谎。

增量写入随之变简单。追加一行之后要索引的就是那一行，调用方已经持有日期与内容，不需要回读整个文件，也不需要 `FileStore`。Task 4 的 `index_trail_file(home, store, date)` 退役，换成 `index_trail_line(home, date, content)`。

合并侧同时修排序与去重。`_search_merged` 当前索引命中在前，改为实时存储在前、索引独有的行在后，并按 `content` 追加一层去重。理由是提升后的语义记录内容就是流水原文（`_trail_episode` 设 `content=entry.content`），两者文本相同，按 `record_id` 去重抓不到，结果是一条事实返回两行。实时记录应当赢，因为它有真实的 `record_id` 与 category。

## Files and owners

| 文件 | 动作 | 职责 |
|---|---|---|
| `lca/infrastructure/memory/contextfiles/domain/trail.py` | modify | 抽出 `trail_lines`，成为「什么算一行」的唯一 owner |
| `lca/infrastructure/memory/contextfiles/service/indexing.py` | modify | `_documents` 的 trail 分支改行粒度；`index_trail_file` 换成 `index_trail_line` |
| `lca/cognition/memory/daytime.py` | modify | 调用点改为 `index_trail_line`，传它已经持有的日期与内容 |
| `lca/infrastructure/tools/assistant/memory_tools.py` | modify | `_search_merged` 改排序并加 content 去重 |
| `tests/infrastructure/memory/test_trail_index_incremental.py` | modify | 钉住整日文档的断言改为钉住行文档，含与全量重建的一致性 |
| `tests/scenario/memory/test_phase0_condition2_trail_capture.py` | modify | 噪音形状测试改为断言一条事实一行 |

`adapters/fts.py` 与 `ports/memory_index.py` 不动。`MemoryIndex.add` 的 upsert 语义与粒度无关，Task 4 加的接口正好够用。

## Baseline and authority refs

- AGENTS.md §2.1 单向层、§4 禁止新增平行机制、§5 变更闭环与不留 COMPAT、§6 验证矩阵、C8 确定性
- ADR-0254（索引覆盖 curated records 与 trail files 的设计来源）
- ADR-0287 §D6（24 小时上界与其读路径前提）、§4 Phase 0 验收
- [条件二计划](2026-10-05-trail-capture-phase0-condition2.md) Task 4 的一致性约束与 Task 6 的噪音实测
- `abd7b5780` 的 `test_trail_documents_are_whole_day_files`，本计划刻意让它变红

## Compatibility boundary

- 索引是可重建投影，不是真值。`doc_id` 形状变更不需要数据迁移，下一次 `run_dream` 全量重建即收敛。
- 生产目前有 1 个索引 db（`asst_ce7fecd65188/memory/index/fts.sqlite3`）。旧的 `trail-<文件名>` 文档会与新行文档并存，直到该助理下一次 dream 重建。`run_dream` 在生产从未运行过，所以这个中间态会一直存在，除非条件一的调度先落地。计划把「重建一次现有索引」列为 Task 4 的显式步骤，不依赖调度。
- `IndexedDocument` 的字段不变，`MemoryIndex` 的签名不变，`_search_indexed` 的行映射不变。
- `search_memory_index` 与 `build_memory_index` 的对外签名不变，各自的唯一调用方是 `memory_tools.py:181` 与 `dream.py:276`。
- 不改 bundle、profile，不需要 `check_plan_lift.py`，不触发内核重启。

## Change Necessity

配置与文档都不够。噪音来自 `_documents` 的文档粒度，那是代码里的一个构造决定。最小边界是上表六个文件，其中五个是既有 owner 的原地修改，只有 `trail_lines` 是新增函数，且它是从 `parse_trail` 里抽出来的，不是新语义。

## TDD Route

mode `auto`，decision `strict`。authority 是 AGENTS.md §5 与本仓 Phase 0 两份计划的既有约定。test posture 命中 behavior、persistence、producer/consumer、meaningful regression 四个信号，且本计划刻意让一条既有测试变红，必须有新测试接手它钉住的性质。

## Ripple Signal Triage

信号命中：persistence（索引 db 的文档形状）、producer/consumer（`_documents` 与 `index_trail_line` 两个生产方对着 `search_memory_index` 一个消费方）、duplicate owner（行抽取逻辑若不收敛会有两份）、export/readback（`doc_id` 是被读回来的键）。

canonical owner：行抽取归 `domain/trail.py`，文档形状归 `service/indexing.py` 的一个共享 helper，两者都不许在调用侧重复。Task 4 已经用 `_trail_document` 建过这个模式，本计划沿用并把它从文件粒度改为行粒度。

## Tasks

### Task 1：抽出 `trail_lines`，`parse_trail` 改为消费它

`domain/trail.py` 增加 `trail_lines(text) -> tuple[str, ...]`，承接现在 `parse_trail` 里的 `_BULLET` 匹配、空行跳过与 `<!--` 注释跳过。`parse_trail` 改为遍历它构造 `TrailEntry`，签名与返回不变。

先写失败测试：`trail_lines` 对含标题、空行、注释与两条 bullet 的文本返回恰好两条内容，且与 `parse_trail` 的 `content` 序列逐项相同。后者是收敛证明，两个函数不会对同一份文本给出不同的行集合。

验证：既有 `tests/infrastructure/memory/test_trail_append_only.py` 与 `test_dream_pipeline.py` 不变而全绿，说明 `parse_trail` 行为未动。

### Task 2：`_documents` 的 trail 分支改行粒度

`service/indexing.py` 的 `_trail_document` 从「一天一个文档」改为「一行一个文档」，`doc_id=f"trail-{date}-{digest}"`，`digest` 用 `sha256_hex(line, length=12)`，与 `_trail_episode` 的 `fact_id` 同源。`path` 保持当天的相对路径。`_documents` 的 trail 分支改为遍历 `trail_lines(text)` 逐行产文档。

摘要函数不新写。`dream.py` 已经从 `lca.contracts.mechanisms.content.addressable` 导入 `sha256_hex`，`indexing.py` 用同一个。

验证：改写 `test_trail_index_incremental.py` 中钉住 `doc_id == f"trail-{_DATE}.md"` 的那条，改为断言两行文本产出两个文档、`doc_id` 各含日期与摘要、`content` 各为单行。全量重建与增量写入的一致性断言保留，逐字段比较 `doc_id`/`kind`/`path`。

### Task 3：增量写入改为单行，退役 `index_trail_file`

`index_trail_file(home, store, date)` 删除，换成 `index_trail_line(home, date, content) -> bool`。它不回读文件、不需要 `FileStore`，直接用传入的日期与内容构造文档并 `add`。失败语义与 Task 4 相同，捕获 `sqlite3.Error` 与 `OSError`，记日志返回 `False`，不上抛。

`daytime.py` 的调用点改为传它已经持有的 `date` 与截断后的内容。截断后的值必须与写进流水的值逐字相同，否则增量文档与重建文档的摘要会不一致，这一条要有测试。

空行不索引，与 `trail_lines` 跳过空行的行为对齐。

验证：`test_trail_index_incremental.py` 里针对 `index_trail_file` 的缺失文件与空文件两条改为针对 `index_trail_line` 的空内容一条，缺失文件那条随回读一起消失。`test_record_turn_trail.py` 全绿。新增一条断言增量文档与全量重建对同一行产出同一 `doc_id`。

### Task 4：合并侧改排序与 content 去重，并重建现存索引

`memory_tools.py` 的 `_search_merged` 改为实时存储命中在前、索引独有命中在后，去重键在 `record_id` 之外加 `content`。语义记录与其对应的流水行文本相同，只按 `record_id` 去重抓不到，curated 记录应当赢。

同时把生产那一个索引 db 重建一次。`run_dream` 在生产从未运行，旧的整日文档不会自己消失。重建方式是在本任务里跑一次 `lca-ops memory dream`，或者由条件一的调度首次触发时完成，二选一，但不能两者都不做。

验证：改写 `test_phase0_condition2_trail_capture.py` 的 `test_trail_documents_are_whole_day_files`，它现在钉的是整日形状，本计划刻意让它变红。新断言是一条事实一行，即 `memory_search` 对判据句返回恰好 1 行 semantic，流水行因 content 相同被去重掉。`test_promoted_record_survives_the_full_index_rebuild` 保持绿。

### Task 5：验收与噪音实测

复跑 Task 6 的端到端场景，实测并记录 `memory_search` 对判据句返回的行数与总字符数，与 `abd7b5780` 记录的 3 行对照。把数字写进本计划，不留「应该变好了」。

再对生产那一个助理的索引做一次实测，确认 cron handoff 文本在行粒度下返回多少行、多少字符。这个数字是「先决发现」那一节后续裁决的输入。

## Verification

- 每任务：`uv run ruff check` + `uv run ruff format --check` + 该任务 pytest
- 汇总：`uv run pytest tests/infrastructure/memory tests/infrastructure/tools tests/scenario/memory tests/cognition/memory tests/perceive tests/reflect tests/remember tests/contracts/memory -q --no-cov`
- 公共签名：`uv run mypy` 对改动文件，报告区分本次引入与既有基线，根级 `tests/` 目前有 62 条既有错误，其中 `NodeContext(budget=None)` 一类是 23 个文件的既有约定
- 分层：`lint-imports` 基线 exit 1 且零 broken contract，`check_package_contracts.py` 基线 60 issues，两者都用 stash 对照取差值
- 文档：`verify_md_links.py`、`notes-check`、`verify_doc_budgets.py`、`check_doc_layering.py --strict`，只要求改动文件未被点名

## Risks

- **两条路径的 `doc_id` 漂移。** 全量重建与增量写入各自构造文档，摘要输入必须逐字相同。Task 3 里 `record_turn_trail` 传给索引的内容与写进流水的内容若有一处先截断一处后截断，摘要就分叉，结果是同一行有两个文档。缓解是共享 `_trail_document` helper 加一条直接断言两者相等的测试。
- **content 去重会吃掉合法的多条结果。** 两条不同记录恰好内容相同时只剩一条。语义记录与流水行相同是本计划要去的那个重，其余情况罕见，但去重键选 `content` 而不是 `(content, category)` 是有意的，选后者就抓不到这个重。
- **旧索引 db 的中间态。** 若 Task 4 的重建步骤被跳过，生产那个 db 会同时含整日文档与行文档，噪音比改之前更大。这一步不能省。
- **机器文本仍在流水里。** 行粒度不改变这一点，只是改变它被返回的形状。授权漏洞那一档仍然存在，等 run origin 载体。
- **运行中的内核早于授权收窄。** pid 2696579 于 22:34:23 启动，Task 3（22:02）与 Task 4（22:23）在启动前提交因而已加载，Task 5（`9f6a89c66`，22:58）与 Task 6（`abd7b5780`，23:24）在启动后提交，未加载。所以该内核跑的是收窄前的 `_trail_episode`，任何 `is_preference_statement` 命中都给 `authority=True`。目前不发作，因为 `run_dream` 在生产从未运行。但条件一的调度一旦在这个内核上落地，就会拿旧授权规则去处理一个装满 cron 文本的流水。条件一上线前必须重启内核，或确认调度进程加载的是 Task 5 之后的代码。这一条对[条件一计划](2026-10-04-dream-scheduler-phase0.md)是硬约束。
- **撤回条件。** 若 run origin 裁决先落地并决定 cron handoff 不进流水，本计划的 Task 5 实测数字需要重跑，Task 1 至 4 不受影响。

## Retirement

- `_trail_document` 的整日文档形状退役，无 COMPAT，同一 PR 内改为行粒度。
- `index_trail_file` 删除，不留别名，调用方只有 `daytime.py` 一处。
- `abd7b5780` 的 `test_trail_documents_are_whole_day_files` 按 Task 4 改写，它钉的形状是本计划要消灭的。
- 索引 db 里旧的 `trail-<文件名>` 文档由一次全量重建清除，不做逐条删除。
- 本计划不产生新的 COMPAT shim，无 delete-when 条目。

## Out of scope

- cron handoff 文本是否该进流水，以及 `record_turn_trail` 如何判别 run 来源。需要 run origin 标记，依赖并发会话的在飞工作，单独裁决。
- 流水保留期与体积上界，属 ADR-0249 Night Consolidation 的 decay 职责。
- `preference:verbosity` 维度名假定风格词都指回复风格，「简洁代码优先」那类误报由 upsert 退役兜住，见条件二计划 Task 5 的后续观察。
- Phase 0 条件一的 dream 调度载体与周期配置，属[条件一计划](2026-10-04-dream-scheduler-phase0.md)。
- Phase 1 至 Phase 3，分别受 ADR-0260 C1 与 ADR-0277 ⑥/⑦ 裁决阻塞。
