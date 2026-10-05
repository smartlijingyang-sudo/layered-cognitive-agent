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

后果是 `_PREFERENCE` 命中一次即永久提升，没有复现兜底。这与 `487a9fdff` 修的缺陷同形，一条错的事实带 authority 提升后不再被审视。所以必须先给流水偏好一个稳定维度键，再拓宽探测器。顺序反过来会把缺陷放大。

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

`dream.py:_trail_episode` 在 `is_preference_statement` 命中后，先问 `matched_style_token(entry.content)`；命中就用 `STYLE_PREFERENCE_DIMENSION`，否则回落 `preference:<摘要>`。`source_trace_id` 保持 `<流水文件名>:<摘要>`，因为同一维度跨天复现要靠不同的 trace 才能把 `recurrence` 累到 2。

这一步让同一维度的不同措辞聚进一个 cluster，`_lifecycle` 的 `recurrence >= 2` 分支对流水偏好重新可达，单次误命中不再直接永久提升。

验证：新增测试断言「还是简洁一点好」与「回复请简短」两条不同措辞的流水行经 `consolidate` 落进同一个 `dedupe_key=preference:verbosity` 的 cluster，且单条出现时 `lifecycle` 为 `ephemeral_fast`、跨两个 source 复现时为 `consolidated_slow`。

### Task 3：在线流水写入方，与索引检索的隐私过滤同 PR

`daytime.py` 新增 `record_turn_trail(runtime, state, *, now_ms=None) -> bool`，与 `record_task_episode` 同形：`episode_home(runtime)` 解析失败、`state` 为空、话轮为空都返回 `False`，任何异常吞掉返回 `False`，不向上传播。它不调用 `govern()`，因此不受闭合模板门控。

写入前两道处理，顺序固定。先 `contains_secret(content)`（`contextfiles/domain/curated.py`），命中则不写并返回 `False`，这是 ADR-0260 C3-3 凭证红线，`run_56c3352cd22e` 的明文口令是先例。再按字符数截断到上界，上界取常量并写测试钉住，避免一条超长话轮把整日流水撑大。

日期取 `now_ms` 派生的 UTC 日期，与 `trail_date` / `_TRAIL_FILE` 的 `memory/YYYY-MM-DD.md` 形状一致。时间来源经参数注入，不读时钟，符合 C8 确定性。

`observe.py:67` 在 `record_task_episode(runtime, state)` 旁调用它。两者互不门控，`govern()` 返回 `None` 时流水照写。

同 PR 必须包含 `memory_tools.py` 的过滤修复：`_search_indexed` 的返回值与 else 分支的 `_search_main` 返回值都套 `is_private_personal`，与 `branch is not None` 分支现有的过滤对齐。漏掉这一半等于把未过滤的用户原文送进模型上下文。

验证：新增 `tests/cognition/memory/test_record_turn_trail.py`，覆盖判据句写入、`govern()` 不命中时仍写入、含口令话轮不写入、超长话轮被截断、home 缺失返回 `False`。新增 `tests/infrastructure/tools/test_memory_search_filters_private.py`，覆盖索引命中含私人信息时不出现在结果里。既有 `tests/infrastructure/memory/test_trail_append_only.py` 三条必须继续通过。

### Task 4：`MemoryIndex` 单文档写入与 trail 追加后的增量索引

`ports/memory_index.py` 的 `MemoryIndex` 增加一个单文档写入方法，`adapters/fts.py` 的 `SqliteFtsIndex` 实现它，语义是 upsert 同一 `doc_id`。`build_memory_index` 的全量 `rebuild` 路径保持不变，`run_dream` 继续用它。

调用点在 Task 3 的写入方成功追加之后，只索引新增的那一行，文档形状与 `_documents` 为 trail 产出的形状一致，否则全量重建会与增量写入产出不一致的 `doc_id`。

索引写失败必须 contained，不能让流水已经落盘而 turn 失败。失败时记日志并返回，dream 的全量重建是它的兜底。

验证：新增测试覆盖同 `doc_id` 二次写入不产生重复行、写入后 `search` 当轮可命中、索引异常不冒泡到 `record_turn_trail` 的返回值之外。`uv run python scripts/check_package_contracts.py` 与 `lint-imports` 跑一遍，区分本次引入与既有失败。

### Task 5：拓宽 `_PREFERENCE`，带误报证据

`trail.py:18` 的 `_PREFERENCE` 增加无记忆动词的风格偏好形状，目标覆盖判据句「还是简洁一点好」「别那么啰嗦」「回复请简短」「我喜欢简洁的回复」。

拓宽必须与 authority 规则同时定，不能只改词表。`_trail_episode` 今天对任何 `is_preference_statement` 命中都给 `authority=True`，而 `preference:<摘要>` 的键形状让 `recurrence` 恒为 1，所以每次命中都是首次即永久提升，没有复现兜底。Task 2 只给风格类偏好换了稳定维度键，非风格类偏好仍走摘要键，这个暴露在本任务必须一并处理。

两条候选。一是把 authority 收窄到能映射出稳定维度的行，代价是「以后不要用 emoji」这类合法的非风格偏好要凑够两天复现才提升。二是给非风格偏好也建维度分类，代价是引入一套新的维度词表，与 Task 1 收敛词表的方向相反。

倾向第一条。漏提升可恢复，次日复现即提升；误提升不可恢复，带 authority 的语义记录不再被审视，与 `487a9fdff` 修的缺陷同形。两侧不对称，应当偏向可恢复的那一侧。

误报证据要实测，不靠推断。可用语料是 24 个含 `semantic.json` 的助理 home（136 条记录）与 19 个 `conversations/*.jsonl`（76 行），2026-10-05 实测。语料偏小，这一点在测试里显式标注，不夸大为覆盖率证明。测试同时钉正反两侧：四条判据句命中，以及「别删那个文件」「请不要这样」这类一次性指令不命中或不带 authority。

验证：新增 `tests/infrastructure/memory/contextfiles/test_preference_detector.py`，正反两侧都有断言。

### Task 6：Phase 0 条件二端到端验收

一条场景测试走完链路。构造一个 `task` 为判据句的 turn，跑 `phase.perceive.observe`，断言 `{home}/memory/<date>.md` 出现该行；断言 `memory_search` 当轮能命中它（Task 4 的前提）；跑 `run_dream`，断言 `semantic.json` 出现 `dedupe_key=preference:verbosity` 的活跃记录；再跑一次 `run_dream`，断言行数与退役行数都不增长，即 `_already_active` 的 NOOP 生效。

这条测试就是 Phase 0 条件二的判据本身，也是 ADR-0287 §4 里「trail 追加后 `memory_search` 当轮能命中该偏好句」那一条的落点。

验证：新增 `tests/scenario/memory/test_phase0_condition2_trail_capture.py`。

## Verification

按 AGENTS.md §6，本计划跨 contracts / cognition / infrastructure / tools 四层，属「Protocol/公共签名」与「分层/import」两档。

- 每任务：`uv run ruff check` + `uv run ruff format --check` + 该任务的 pytest
- 汇总：`uv run pytest tests/contracts tests/cognition/memory tests/reflect tests/remember tests/infrastructure/memory tests/scenario/memory -q --no-cov`
- 公共签名：`uv run mypy` 对改动文件，报告须区分本次引入与 56 条既有基线
- 分层：`lint-imports` + `uv run python scripts/check_package_contracts.py`，两者当前有既有失败，报告须分开列
- 插件形状不受影响，本计划不新增 plugin；若 Task 4 触及 plugin 则加 `./scripts/lca-ops audit-plugin-shape`
- 文档门禁：`verify_md_links.py`、`notes-check`、`verify_doc_budgets.py`、`check_doc_layering.py --strict`，五个门禁当前全部 exit 1 属既有失败，只要求改动文件未被点名

## Risks

- **语料太小，误报率测不准。** 76 行对话不足以给出统计意义上的误报率。缓解是 Task 2 的稳定维度键把误报代价降到 ephemeral，而不是靠探测器精度兜底。若上线后发现 `preference:verbosity` 被误提升，回退点是 Task 5 的词表，不是 Task 2 的键形状。
- **流水体积。** 每个话轮一行，长期无上限。`run_dream` 把每行都映射成 EpisodeFact，非偏好行落 `trail:<摘要>` 且 `authority=False`、`recurrence` 恒为 1，因此停在 `ephemeral_fast`，不进 `semantic.json`，但会持续增大 episode 集合与索引。本计划只做单行长度上界，不做保留期。保留期属 ADR-0249 Night Consolidation 的 decay 职责，不在条件二范围，需要时另立。
- **隐私过滤是新增的读侧行为。** Task 3 给 `_search_indexed` 加过滤会让某些既有查询少返回结果。这是修正而不是回归，但要在 PR 描述里写明，避免被当成检索能力下降。
- **`MemoryIndex` 只有一个实现。** 给它加方法符合 §5 的闭环要求，但也说明这个 Protocol 目前是单实现抽象。本计划不借机扩实现，也不删这个 seam，删除属 `lca-find-simplifications` 的范围。
- **撤回条件。** Task 2 的稳定维度键若与 ADR-0277 待拍板⑦（`SemanticClaim` 与 `MemoryRecord` 的关系）的裁决冲突，Task 2 与 Task 5 需按裁决重做，Task 1/3/4 不受影响，因为它们的归属与键形状无关。

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
