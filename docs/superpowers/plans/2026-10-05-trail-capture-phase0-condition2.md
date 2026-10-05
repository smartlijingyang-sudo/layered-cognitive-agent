# Phase 0 条件二实施计划：在线流水捕获与偏好维度归一

> 母体：[语义记忆在线单写者与离线对账归位](../../notes/proposed/seam/2026-10-04-semantic-memory-single-online-writer.md) §交付门禁 Phase 0 条件二
> 契约：[ADR-0287](../../adr/0287-semantic-memory-single-online-writer.md) §4 Phase 0、§D6、§6 Open question 5
> 姊妹计划：[dream 调度器 Phase 0 条件一](2026-10-04-dream-scheduler-phase0.md)（载体选型与 5 个调度任务，与本计划互不重叠）

## Goal

一个含无记忆动词偏好句（判据句「还是简洁一点好」）的 turn 之后，该偏好当轮可被 `memory_search` 命中，且在下一次 dream pass 提升为 `semantic.json` 中 `dedupe_key=preference:verbosity` 的活跃记录。

这是 Phase 0 条件二的两项交付物加上 D6 裁决附带的前提，共三项。

1. `TrailWriter` 的在线生产写入方（Open question 5 裁决归本提案）。
2. 拓宽 `_PREFERENCE` 与 `govern()` 之一的偏好判定，使判据句被捕获。
3. trail 追加后当轮增量索引，使 24 小时上界不触发 D6 的重评估条件。

## Architecture

走 trail 路线，不走 govern 路线。

`domain/trail.py:3` 把流水定义为 raw interaction evidence，`EpisodeBuffer` 存的是 `govern()` 闭合模板产出的结构化残差。把原始话轮写进 `episodes/` 需要 `govern()` 先命中，而闭合模板正是它的设计意图。`_trail_episode`（`dream.py:137-158`）已实现 authority 映射；govern 路线则要把 `govern.py:66` 硬编码的 `False` 翻成 `True`，改动的正是 `487a9fdff` 刚修过污染缺陷的那一族模板。trail 还已有两个等待中的消费者，`run_dream` 经 `parse_trail`，FTS 索引经 `_documents`；补写入方是激活两者，不是新增一个。

### 两个决定任务顺序的结构事实

**其一，trail 事实拿不到 recurrence 保护。** `_trail_episode` 的 `dedupe_key` 是 `preference:<内容摘要>`，`source_trace_id` 是 `<流水文件名>:<同一摘要>`。`_cluster`（`contracts/models/memory/episode.py:85-92`）按 `dedupe_key` 分组，`recurrence` 是组内不同 `source_trace_id` 的个数。同一句话跨两天复现能凑到 2，但「还是简洁一点好」与「回复请简短」是不同内容、不同摘要、不同 key，永远不聚在一组。于是 `_lifecycle`（`episode.py:74-82`）的 `recurrence >= 2` 分支对同一维度的不同措辞不可达，唯一的提升路径是 `explicit_user_authority=True`。

后果是 `_PREFERENCE` 命中一次即永久提升，没有复现兜底，因为 `_lifecycle` 的 authority 分支先于 `recurrence` 短路。这与 `487a9fdff` 修的缺陷同形，一条错的事实带 authority 提升后不再被审视。

顺序必须是先给稳定维度键（Task 2）再拓宽探测器（Task 5），但理由不是维度键能带来复现保护，它带不来，authority 仍然短路。真正的理由是拓宽会放大重复。Task 5 让更多流水行被判为偏好，若它们仍各自持有 `preference:<摘要>` 键，每一行都新开一个维度、各自提升一条语义记录，重复维度按拓宽幅度成倍增长。先落维度键，同一风格维度的新命中才会收敛成一条记录。authority 造成的误报暴露两个任务都不解决，留给 Task 5 的规则。

**其二，索引检索路径没有隐私过滤。** `MemorySearchTool.execute`（`infrastructure/tools/assistant/memory_tools.py:118-126`）只在 `branch is not None` 的分支对 `_search_main` 结果套 `is_private_personal`，`_search_indexed` 与 else 分支的 `_search_main` 都不过滤。今天索引里只有经 `contains_secret` 写入的 curated 记录，所以缺口不可达。流水开始承载原始话轮后，未经过滤的用户原文会经索引进入 `memory_search` 结果，再进入模型上下文。写入方与这个过滤必须同一个 PR 落地。

## Files and owners

| 文件 | 动作 | 职责 |
|---|---|---|
| `lca/contracts/models/memory/episode.py` | modify | 风格偏好词表与维度映射的唯一 owner，供 cognition 与 infrastructure 共同消费 |
| `lca/cognition/memory/govern.py` | modify | 私有 `_VERBOSITY` 改为消费 contracts 词表 |
| `lca/infrastructure/memory/contextfiles/domain/trail.py` | modify | `_PREFERENCE` 拓宽；维度键经 contracts 映射解析 |
| `lca/infrastructure/memory/dream.py` | modify | `_trail_episode` 对风格偏好发稳定维度键 |
| `lca/cognition/memory/daytime.py` | modify | 新增 `record_turn_trail`，不受 `govern()` 门控 |
| `lca/nodes/perceive/observe/observe.py` | modify | 在 `record_task_episode` 旁调用 `record_turn_trail` |
| `lca/infrastructure/memory/contextfiles/ports/memory_index.py` | modify | `MemoryIndex` 增加单文档写入方法 |
| `lca/infrastructure/memory/contextfiles/adapters/fts.py` | modify | `SqliteFtsIndex` 实现该方法 |
| `lca/infrastructure/tools/assistant/memory_tools.py` | modify | `_search_indexed` 结果套 `is_private_personal` |

分层核验：`daytime.py` 在 cognition，`TrailWriter` 在 infrastructure，cognition → infrastructure 是向下依赖，合法，且 `daytime.py` 已经这么导入 `EpisodeBuffer`。`dream.py` 在 infrastructure，不得导入 cognition 的 `govern.py`，所以共享词表必须落在 contracts，这是本计划把词表放进 `episode.py` 的原因。

## Baseline and authority refs

- AGENTS.md §2.1 单向层、§4 禁止新增平行机制、§5 变更闭环（公共签名改动须同步全部实现与测试）、§6 验证矩阵
- ADR-0249（Accepted，昼夜双轨）§0.1 与 Fast Path / Night Consolidation 分工
- ADR-0260 C2 强制检索、C3-3 凭证红线、§6.3 承诺与残差的归属裁决、§D6 的 24 小时上界与增量索引前提
- ADR-0287 §4 Phase 0 条件二、§6 Open question 5 裁决
- `487a9fdff` 的捕获边界修复与其回归测试

## Compatibility boundary

- `TrailWriter.append` / `overwrite` / `trail_path` 签名不变，`test_trail_append_only.py` 的三条窄门断言必须继续通过。
- `MemoryIndex` 加方法是公共签名变更。它当前只有一个实现 `SqliteFtsIndex`，同 PR 内同步实现与全部消费者，不留 COMPAT 分支。
- `govern()` 签名与返回类型不变。`tests/reflect/test_web_assistant_episode_governor.py` 钉住的 `我是架构师` → `用户身份：架构师` 必须继续成立。
- `semantic.json` 的在线写者仍然只有 memory 工具。本计划不新增任何在线语义写入路径，写入方只产流水这一层原始证据。
- `profiles/*.yaml` 与 `bundles/*.yaml` 不改。条件一的载体任务才动它们，本计划不碰，因此不需要 `check_plan_lift.py`，也不触发内核重启。

## Change Necessity

纯文档与配置都不够。判据句当前在两条捕获路线上都返回空，`govern.py:59` 要求 `记住|以后` 合取，`trail.py:18` 的 `_PREFERENCE` 实测对「还是简洁一点好」「别那么啰嗦」「回复请简短」「我喜欢简洁的回复」全部不命中。而且流水根本没有生产写入方，`TrailWriter` 在 `lca/` 内除自身 `__all__` 外零引用，所有助理 home 的 `memory/20*.md` 计数为 0（2026-10-05 实测）。最小代码边界是上表九个文件，其中六个是既有 owner 的原地修改，不新增模块。

## TDD Route

mode `auto`，decision `strict`。authority 是 AGENTS.md §5「每个 bugfix 至少一个回归测试」与本仓 Phase 0 姊妹计划的既有约定。test posture 命中 behavior、bugfix、persistence、producer/consumer、public contract 五个 strict 信号。verification 为每个任务先写失败测试并确认失败原因正确，再写实现。

## Ripple Signal Triage

信号命中：persistence（流水文件从无到有）、producer/consumer（一个写入方对着两个既有消费者）、public contract（`MemoryIndex` 签名）、source-of-truth（风格词表从 cognition 私有常量迁到 contracts）、duplicate owner（`govern._VERBOSITY` 与 `_PREFERENCE` 是同一语义的两份词表）。

canonical owner 判定：风格偏好词表归 `contracts/models/memory/episode.py`，它已经拥有 `canonical_dedupe_key` 与 `LifecycleState`，是这条语义在最低层的既有归属。`govern.py` 与 `trail.py` 都改为消费方，两份词表收敛为一份。

## Tasks

### Task 1：风格偏好词表与维度映射迁到 contracts

状态：已完成。

`episode.py` 增加 `STYLE_PREFERENCE_DIMENSION = "preference:verbosity"`、私有词表 `_STYLE_TOKENS`（内容取 `govern.py` 原有的 `("简洁", "啰嗦", "详细")`，本任务不拓宽）与纯函数 `matched_style_token(text) -> str | None`，返回命中的那个词，无命中返回 `None`。三者都进 `__all__`。

计划初稿写的是 `style_preference_dimension(text) -> str | None`，实施时改成 `matched_style_token` 加一个维度常量。原因是 `govern()` 的分支要拿命中的词去渲染 `用户偏好：{token}`，只返回维度键不够；而 Task 2 只需要维度键，用 `STYLE_PREFERENCE_DIMENSION` 直接取即可。一个函数加一个常量同时满足两个消费方，比返回二元组或新增一个类型都小。

`govern.py` 删掉私有 `_VERBOSITY`，改为导入这两个名字，`记住|以后` 合取门保持不变。顺带去掉了原分支对词表的两次扫描（先 `any(...)` 再 `for` 找命中项），现在只扫一次。

先写失败测试再写实现。`tests/contracts/memory/test_style_preference_vocabulary.py` 钉住词表命中、非风格文本不命中、多词命中时取词表顺序的第一个、以及 Task 1 不拓宽（`回复请简短` 仍返回 `None`，拓宽属 Task 5）。`tests/cognition/memory/test_govern_style_dimension.py` 是 `govern()` 风格分支的characterization 测试，该分支此前无覆盖，迁移前先确认它 4 条全绿，迁移后仍须全绿。

验证：`uv run pytest tests/contracts/memory tests/cognition/memory tests/reflect -q --no-cov`。`govern()` 既有行为不变。

### Task 2：`_trail_episode` 对风格偏好发稳定维度键

状态：已完成。

`dream.py:_trail_episode` 在 `is_preference_statement` 命中后先问 `matched_style_token(entry.content)`，命中就用 `STYLE_PREFERENCE_DIMENSION`，否则回落 `preference:<摘要>`。`source_trace_id` 保持 `<流水文件名>:<摘要>`。

实测修正了本任务的理由。改动前 `以后回复简洁一点` 与 `回复要简洁` 经 `consolidate` 产出两个 cluster，各 `recurrence=1`、各 `consolidated_slow`，提升为两条独立语义记录。改动后合成一个 `dedupe_key=preference:verbosity` 的 cluster。所以本任务买到的是维度身份，一个维度一条记录，`_already_active` 的 NOOP 也因此对风格偏好生效。

本任务没有买到误报防护。`_lifecycle` 先判 `explicit_user_authority` 且 category 属 IDENTITY 或 PREFERENCE，命中即 `consolidated_slow`，永远走不到 `recurrence >= 2`。流水偏好的 authority 恒为 `True`，所以单次提及仍然首次即永久提升。初稿写的「单次误命中不再直接永久提升」与「单条出现时 lifecycle 为 ephemeral_fast」都不成立，误报防护属 Task 5 的 authority 规则。

验证：`tests/infrastructure/memory/test_trail_style_dimension.py` 在 `run_dream` 真实入口上跑，不经私有函数。断言两种措辞只产一条 `preference:verbosity` 记录、非风格偏好保留摘要键、非偏好行不提升、单次提及仍提升（钉住上面这条反面事实）、第二次 dream 不新增。测试数据用 `以后回复简洁一点` 与 `回复要简洁`，两者都命中 `_PREFERENCE` 且都含风格词。初稿写的「还是简洁一点好」不命中 `_PREFERENCE`，「回复请简短」的 `简短` 不在 Task 1 的词表里，两者都要等 Task 5 才可用。

遗留观察，供 Task 5 使用。`source_trace_id` 是 `<流水文件名>:<内容摘要>`，所以 `recurrence` 数的是不同措辞而不是不同场合。同一句话在同一天的流水里出现两次得到相同 `source_trace_id`，`recurrence` 仍为 1；两种不同措辞在同一天出现则 `recurrence` 为 2。若 Task 5 收窄 authority、让 `recurrence` 成为唯一提升门，这个语义要先定清楚。

### Task 3：在线流水写入方，与索引检索的隐私过滤同 PR

状态：已完成。

`daytime.py` 新增 `record_turn_trail(runtime, state, *, now_ms=None) -> bool`，与 `record_task_episode` 同形，`episode_home(runtime)` 解析失败、`state` 为空、话轮为空都返回 `False`，任何异常吞掉返回 `False`。它不调用 `govern()`，因此不受闭合模板门控。`observe.py` 在 `record_task_episode` 旁调用它，两者互不门控。

写入侧只挡凭证。`contains_secret(text)` 命中即返回 `False` 且不落盘，这是 ADR-0260 C3-3 的红线，`run_56c3352cd22e` 的明文口令是先例。私人信息不在写入侧过滤，因为 `is_private_personal` 本身已经包含 `contains_secret`，两者是写侧红线与读侧过滤的分工，不是重复。单行上界 `_MAX_TRAIL_LINE_CHARS = 200`，测试钉住。

日期由 `now_ms` 派生的 UTC 日期得出，时间经参数注入不读墙钟，符合 C8。派生用的 `datetime.fromtimestamp(now_ms / 1000, tz=UTC).strftime("%Y-%m-%d")` 与 `dream.py` 和 `assistant_memory.py` 里的写法相同，现在是第三处。三处是抽取阈值，但抽取要动另外两层，不并进本任务，留作后续。

隐私过滤做成了所有路径之后的一次统一过滤，不是计划里写的两处分别套。这样 `_search_branch` 的结果也一并过滤，它原先没有过滤。范围比计划大一点，代价是多过滤一条本来就不该出现在检索结果里的私人内容，收益是以后新增检索路径不会漏掉这一层。

`TrailWriter.append` 是读改写，本身不原子。`DiskFileStore._refuse_trail_overwrite` 会把非严格追加的写入判为 `NarrowGateViolationError`，所以两个并发话轮相撞时结果是其中一行丢失并返回 `False`，而不是文件被写坏。这是接受的语义，`record_turn_trail` 的 docstring 写明了。要消除丢失需要给 trail 加锁，`EpisodeBuffer` 用一事实一文件规避了同一个问题，但那是另一种存储形状，不在本任务范围。

验证：`tests/cognition/memory/test_record_turn_trail.py` 11 条，覆盖判据句写入（含 `还是简洁一点好`、`别那么啰嗦`、`回复请简短` 三条 `govern()` 全部返回 `None` 的句子）、日期来自注入时钟、两次写入是追加不是覆盖、凭证被拒、私人信息照写（钉住写读两侧的分工）、超长截断、home 缺失、空话轮、`state` 为 `None`。`tests/infrastructure/tools/test_memory_search_filters_private.py` 3 条，覆盖索引路径与无索引回退路径都过滤，以及正常记录不被连带吃掉。既有 `tests/infrastructure/memory/test_trail_append_only.py` 三条窄门断言继续通过。

`tests/perceive/test_observe_records_task_episode.py` 另加一条接线锁，断言判据句在 `govern()` 不命中时仍写出流水、且不产 episode。上面那些测试都直接调 `record_turn_trail`，删掉 `observe.py` 里的调用它们全都不会红，这一条会。已实测：把调用换掉后该条失败，恢复后通过。

### Task 4：`MemoryIndex` 单文档写入与 trail 追加后的增量索引

状态：已完成，并修掉一个计划没预见的严重回归。

`ports/memory_index.py` 的 `MemoryIndex` 增加 `add(document)`，`adapters/fts.py` 的 `SqliteFtsIndex` 实现它，语义是按 `doc_id` upsert，FTS5 与 plain 两条分支都覆盖。`build_memory_index` 的全量 `rebuild` 路径不变，`run_dream` 继续用它。

**计划初稿说「只索引新增的那一行」，这是错的。** `_documents` 对整个流水文件产一个文档，`doc_id=trail-<文件名>`、`content` 是整份文件文本，粒度是文件不是行。按行索引会造出全量重建永不产生的 `doc_id`，下一次 `run_dream` 重建就把增量写进去的那个孤立掉。实际做法是追加后重索引当天整份文档，与重建同形。为保证两者不会漂移，`_documents` 的 trail 分支与新的 `index_trail_file` 共用一个 `_trail_document(name, text, layout=)` helper。

`index_trail_file` 的失败 contained，返回 `False` 并记日志，捕获 `sqlite3.Error` 与 `OSError`。`record_turn_trail` 在 append 成功之后、`try` 之外调用它，所以索引失败不会把已经落盘的流水报成失败。

**回归：索引一旦存在就会藏起实时语义记录。** `MemorySearchTool.execute` 原先是二选一，`indexed if indexed is not None else self._search_main(...)`。`search_memory_index` 只在 db 文件不存在时返回 `None`，所以增量索引一建出 db，`_search_main` 就再也不会被调用。实测确认：种一条语义记录时 `memory_search("简洁")` 返回它，建一个只含流水的索引之后同一次查询只返回流水行，语义记录消失。Task 3 之后每个助理每轮都写流水，这个洞普遍可达，而且会打在 Phase 1 之后唯一的在线语义写者上。

修法是合并两个来源，`_search_merged` 取索引命中与 `_search_main` 命中的并集，按 `record_id` 去重后截到 `limit`。两者都不完整：索引是投影，只有 `run_dream` 做全量重建，所以它装着实时存储看不到的流水行，也缺上一次重建之后写入的语义记录。二选一的前提是索引永远完整，而这个前提从来不成立。branch 分支不参与合并，它本来就不走索引。

验证：`tests/infrastructure/memory/test_trail_index_incremental.py` 5 条，覆盖同 `doc_id` 二次写入不产生重复行、增量文档与全量重建的 `doc_id`/`kind`/`path` 逐字段相同、二次追加替换同一文档、文件缺失返回 `False`、空文件返回 `False` 且不建 db。`tests/infrastructure/tools/test_memory_search_merges_sources.py` 4 条，其中回归锁断言只含流水的索引不藏实时语义记录。`tests/scenario/memory/test_trail_same_turn_reachable.py` 是 D6 前提的跨层场景锁，一轮 `record_turn_trail` 之后当轮 `memory_search` 能命中该行、且既有语义记录仍可命中。三条既有 `test_retrieval_index.py` 与三条 `test_trail_append_only.py` 继续通过。后两条锁都做过拔牙实测，把 `index_trail_file` 调用换成 `pass` 后各自失败。

### Task 5：拓宽偏好捕获，收窄偏好授权

状态：已完成。裁决（2026-10-05，李超）取收窄 authority 那一条。

落地的规则比裁决字面更严一格，理由见下。捕获与授权拆成两个独立谓词，`domain/trail.py` 各出一个。

- `is_explicit_instruction(content)` 就是原来的 `_PREFERENCE` 匹配（`偏好|以后|不要|必须|记住|严禁|回复要|请记`），改名以说明它现在只承担一件事：判定用户是否下了指令。它是授权的**唯一**依据。
- `is_preference_statement(content)` 拓宽为「显式指令 **或** 命中风格维度」。判据句「还是简洁一点好」「别那么啰嗦」「回复请简短」「我喜欢简洁的回复」经这一条被捕获，Phase 0 条件二的判据由此达成。

风格词表只加了 `简短` 一个词，没有往 `_PREFERENCE` 里塞 `别`/`请`/`喜欢` 这类通用祈使词。原因是通用祈使词的误报面太大，「别删那个文件」会被判成偏好。拓宽走闭合的风格词表，边界是有界的。

`_trail_episode` 的授权改为 `explicit and style is not None`，即**既是显式指令又能映射到稳定维度**才给 `authority=True`。裁决的字面是「收窄到能映射出稳定维度的行」，只按维度判会把「这段代码很简洁」这类提到风格词但不是指令的句子也永久提升，形状与 `487a9fdff` 修的缺陷相同。与显式性取交集之后这一格被堵住，且它严格窄于裁决要求，不放宽任何已裁决的东西。

四格矩阵。

| 显式指令 | 风格维度 | category | dedupe_key | authority |
|---|---|---|---|---|
| 有 | 有 | PREFERENCE | `preference:verbosity` | True，首次即提升 |
| 有 | 无 | PREFERENCE | `preference:<摘要>` | False，需跨天复现 |
| 无 | 有 | PREFERENCE | `preference:verbosity` | False，需跨天复现 |
| 无 | 无 | FACT | `trail:<摘要>` | False |

#### 实测误报证据

语料是 24 个含 `semantic.json` 的助理 home（136 条记录）与 19 个 `conversations/*.jsonl` 的用户话轮，合计 213 行，2026-10-05 实测。语料小，下面是不存在性证明，不是比率。

- `is_preference_statement` 命中 72 行（34%）。
- 其中会拿到授权的 9 行（4.2%）。9 行全部是真实的回复风格偏好，例如「用户偏好：回复简洁，不啰嗦」「回复偏好：简洁扼要，优先给代码示例与架构图」。
- 9 行里有 1 行是误报，「用户架构偏好：简洁代码优先」讲的是代码风格不是回复风格。它被收进 `preference:verbosity` 维度，因此下一条真正的回复风格偏好会以同 `dedupe_key` 走 `upsert` 把它退役，是可自愈的，与 `487a9fdff` 那种带授权且不再被审视的形状不同。
- 收窄挡掉的是真实存在的误报。语料里「请用一句话告诉我现在几点，不要调用任何工具」「请用一句话回答：1加1等于几？不要调用工具」是单次请求指令，旧规则给它们 `authority=True`，会永久固化成一条偏好。
- 收窄的代价也在语料里可见，63 行失去首次即提升，例如「用户偏好：不要客套话」「技术栈偏好：Rust 和 Go」，这类要跨天复现才提升。这是裁决接受的代价。

#### 后续观察，不在本任务

`preference:verbosity` 这个维度名假定风格词都指回复风格。「简洁代码优先」说明该假定不总成立。要根治需要给维度加一个回复语境限定词，或者把代码风格另立维度。当前由 upsert 退役兜住，先不动。

验证：`tests/infrastructure/memory/test_preference_detector.py` 15 条，覆盖四条判据句被捕获、风格话题单独出现不算显式指令、显式风格指令两轴都命中、既有显式非风格指令语义不变、「别删那个文件」「李雷说项目下周发布」两轴都不命中。`tests/infrastructure/memory/test_trail_authority_narrowing.py` 5 条走 `run_dream` 真实入口，逐格钉住上面的矩阵，含判据句跨天复现才提升、非风格显式偏好跨天复现才提升、两种措辞落进同一维度只产一条记录。Task 1 钉住「不拓宽」的那条测试按本任务改写为钉住拓宽后的边界，Task 2 的非风格偏好测试改为跨天复现。

### Task 6：Phase 0 条件二端到端验收

状态：已完成。

`tests/scenario/memory/test_phase0_condition2_trail_capture.py` 走 `phase.perceive.observe` 真实节点，不手写流水。断言分五段：判据句落进当天流水且 `episodes/` 为空（`govern()` 对它返回 `None`，路线 b 成立）、`is_preference_statement` 命中、当轮 `memory_search` 能命中（D6 前提）、单次提及经 `run_dream` 不提升、跨天复现后提升为唯一一条 `preference:verbosity` 且第三次 dream 的行数与退役行数不变。

计划初稿写的是「跑 `run_dream` 就断言出现 `preference:verbosity`」，那是 Task 5 收窄授权之前的语义。收窄之后单次提及停在 `ephemeral_fast`，验收必须走两天，否则测试会与授权矩阵自相矛盾。

日期不写死。`observe` 调 `record_turn_trail` 不传 `now_ms`，流水文件名取自墙钟，所以当天文件按 glob 找，第二天用一个保证不同的固定日期，跨午夜不会让本测试变红。已连跑 5 次随机顺序并与整目录同跑，均稳定。

#### 检索噪音，需另行裁决

端到端跑出来的实测形状：一句偏好提升之后 `memory_search("简洁")` 返回 3 行，1 行 curated 语义记录加 2 行流水文档，而每个流水文档的 `content` 是**整天**的文件原文。原因是 `_documents` 按整个流水文件产一个文档，`doc_id=trail-<文件名>`。

Task 3 之前流水不存在，这个形状不可达；Task 3 加 Task 4 之后它成为常态，并随天数与当天话轮数增长。`limit=10` 时最坏情况是 10 个整日文件进模型上下文。

`test_trail_documents_are_whole_day_files` 把当前形状钉住，粒度或排序要改时该测试变红，改动必须显式。

三条候选，都不在本计划范围。一是接受，流水本来就是证据，ADR-0254 设计索引覆盖它。二是合并结果里把 curated 记录排在流水之前并给流水行数设上限，保证投影不会把记录挤出 `limit`。三是流水索引改按行粒度，`doc_id` 变为 `trail-<文件名>-<行摘要>`，一次命中只返回一行，代价是 `build_memory_index` 与 `index_trail_file` 的文档形状都要改，Task 4 建立的一致性约束要重新对齐。

倾向三。它同时解决噪音与上下文膨胀，且与 Task 2 的稳定维度键同一思路，粒度对齐语义单元。但它改的是 `_documents` 的既有形状，属新的独立任务，已开 [流水索引改行粒度实施计划](2026-10-05-trail-index-line-granularity.md)，其 Task 1 至 4 已落地。

## Verification

按 AGENTS.md §6，本计划跨 contracts / cognition / infrastructure / tools 四层，属「Protocol/公共签名」与「分层/import」两档。

- 每任务：`uv run ruff check` + `uv run ruff format --check` + 该任务的 pytest
- 汇总：`uv run pytest tests/contracts tests/cognition/memory tests/reflect tests/remember tests/infrastructure/memory tests/scenario/memory -q --no-cov`
- 公共签名：`uv run mypy` 对改动文件，报告须区分本次引入与 56 条既有基线
- 分层：`lint-imports` 基线 exit 1，原因是两条 `No matches for ignored import` 的陈旧忽略项；`check_package_contracts.py` 基线 `FAIL: 60 issues across 82 packages`。两者都用 stash 对照确认差值为 0，不能只看退出码。取退出码时不要在管道后读 `$?`，那是管道末命令的状态，不是门禁的。
- 插件形状不受影响，本计划不新增 plugin；若 Task 4 触及 plugin 则加 `./scripts/lca-ops audit-plugin-shape`
- 文档门禁：`verify_md_links.py`、`notes-check`、`verify_doc_budgets.py`、`check_doc_layering.py --strict`，五个门禁当前全部 exit 1 属既有失败，只要求改动文件未被点名

## Risks

- **语料太小，误报率测不准。** 实测语料 213 行（24 个含 `semantic.json` 的 home 共 136 条记录，加 19 个对话日志的用户话轮），不足以给出统计意义上的误报率，Task 5 记录的是不存在性证明。缓解不是探测器精度，而是授权收窄到「显式指令且命中维度」，加上 Task 2 的稳定维度键让误报会被下一条同维度 upsert 退役。若上线后发现 `preference:verbosity` 被误提升，回退点是 Task 5 的词表与授权交集，不是 Task 2 的键形状。
- **检索噪音与上下文膨胀。** `_documents` 按整天产一个流水文档，所以一次命中会把当天全部话轮原文带进模型上下文，且同一事实会同时以 curated 记录与多个流水文档出现。实测形状与三条候选见 Task 6 的「检索噪音，需另行裁决」。这是 Task 3 加 Task 4 之后才可达的，此前流水无生产方。
- **流水体积。** 每个话轮一行，长期无上限。`run_dream` 把每行都映射成 EpisodeFact，非偏好行落 `trail:<摘要>` 且 `authority=False`、`recurrence` 恒为 1，因此停在 `ephemeral_fast`，不进 `semantic.json`，但会持续增大 episode 集合与索引。本计划只做单行长度上界（200 字符），不做保留期。保留期属 ADR-0249 Night Consolidation 的 decay 职责，不在条件二范围，需要时另立。
- **隐私过滤已落地为读侧行为。** Task 3 把过滤统一成所有检索路径之后的一次，`_search_branch` 的结果也开始被过滤，某些既有查询会少返回结果。这是修正而不是回归，但会让检索结果数量下降，需要与「检索能力下降」区分。
- **`MemoryIndex` 只有一个实现。** Task 4 给它加了 `add`，符合 §5 的闭环要求，但也说明这个 Protocol 目前是单实现抽象。本计划不借机扩实现，也不删这个 seam，删除属 `lca-find-simplifications` 的范围。
- **撤回条件。** Task 2 的稳定维度键若与 ADR-0277 待拍板⑦（`SemanticClaim` 与 `MemoryRecord` 的关系）的裁决冲突，Task 2 与 Task 5 需按裁决重做，Task 1/3/4/6 不受影响，因为它们的归属与键形状无关。

## Retirement

- `govern.py` 的私有 `_VERBOSITY` 常量在 Task 1 删除，不留别名，不留 COMPAT 分支。同一 PR 内 `govern.py` 改为消费 contracts 词表。
- `_trail_episode` 里 `preference:<摘要>` 的键形状保留，作为无维度映射时的回落，不退役。它是非风格类偏好的正确形状。
- `build_memory_index` 的全量重建路径保留，`run_dream` 仍是它的调用方。Task 4 增加的是增量路径，不替代全量路径。
- 本计划不产生新的 COMPAT shim，因此无 delete-when 条目。

## Out of scope

- dream 调度载体与周期配置，属[条件一计划](2026-10-04-dream-scheduler-phase0.md)。
- `semantic.json` 在线单写者、认领权改派生读、对账收敛，属 Phase 1 至 Phase 3，分别受 ADR-0260 C1 与 ADR-0277 ⑥/⑦ 裁决阻塞。
- `govern()` 三个闭合模板的整体拓宽。本计划只把风格词表迁到 contracts 并让两条路线共用，不增加模板。
- 存量污染记录 `asst_5166b058964f/memory/episodes/ep_dc6df2f81fd6d9e3.json` 的清理。属助理数据、不在本仓范围，需单独授权。
