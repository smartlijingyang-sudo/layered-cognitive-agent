# Raphy Assessment — Round 7 (2026-10-08 02:06, branch `raphy/arch-20261008-0206`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
→ git log 热点定域 → CONTEXT.md + 相关 ADR → 三区 friction walk（5 问必答，端到端精读非 grep）
→ mandatory runtime verification（mock LLM 真跑：basic / tool-call / 双 run + P0 复现）
→ duplication 副扫描 → self-grilling → stories 入 prd.json（`userStories` 键，RA-023 起编号）。

## Scope（YAGNI）

`git log --oneline -70` 生产代码热点（排除已做故事领地 + 纯测试 + 禁区）：
- `lca/infrastructure/host_runtime/providers/user_cli.py` ×3 → RA-014/015 已做，避开
- `lca/infrastructure/observability/loop_cursor/projection/host.py` ×3 → RA-010/011 已做，避开
- `lca/infrastructure/source_verify/verifier.py` ×2 → RA-016 已做，避开
- `lca/infrastructure/tool_defer/tool_search.py` ×2 → RA-018 已做，避开
- `lca/session/catalog.py` ×2 → RA-017 已做，避开
- `lca/infrastructure/sandbox/runtime/runtime.py` ×2 → RA-020 已做，避开
- `lca/plugins/session/*`（title_service/telemetry_capture/_shared）→ RA-019 已做，避开
- `lca/plugins/transport/webserver/**` → lca-1000 活跃迁移领地（禁区），避开
- `lca/cognition/memory/` → Round 2 冻结（禁区），避开
- `gate_chain_strategy.py` → 他人工作（禁区），避开

三区 friction walk 定域（全是近 40 commits 内动过、且无 raphy 故事覆盖的）：
- **Area A**：事件总线 + model_visible（`lca_kernel/events/bus/bus.py` 721 行全文 /
  `lca/plugins/events/hooks/model_visible/hook.py` 380 行全文 /
  `lca/plugins/events/publishers/model_visible/publisher.py` 147 行全文）
- **Area B**：双 tick 调度器（`lca/infrastructure/scheduler_file_lock.py` 97 行全文 /
  `lca/infrastructure/cron/scheduler.py` 381 行全文 /
  `lca/infrastructure/proactive/scheduler.py` 295 行全文）——lca-1000 第 0520 轮刚收敛文件锁
- **Area C**：journal narrative fold 章节（`lca/infrastructure/observability/journal/step/narrative_writer/fold.py` 216 行全文）

CONTEXT.md（13 行）已读：领域词汇只有"Profile 启动产物 / 程序化 Profile 输入 / StopPolicy"三条，
本轮三区均不触及这些概念，无需增补。ADR 相关：ADR-0183/0184（bus）、ADR-0185（model_visible/fold）、
ADR-0186（Session SSOT）、ADR-0263 §9（调度器锁）、ADR-0268（cron）——读了各文件头部的引用节，
未重读全文（头部已把不变量写清）。

## Friction walk（5 问必答）

### Area A — event bus + model_visible hook/publisher

1. **理解一个概念要在多少小模块间跳？** 理解"一次 model-visible 事件如何发布"要在四处跳：
   `hook.py`（capture_pre/post_llm 拼 payload）→ `publisher.py`（marker 类 + setup 注入 hook）→
   `bus.py`（publish S1 鉴权→S2 回执→S3 落盘→S4 派发）→ `publishers/_session_publish.publish_via_session`
   → `Session.append`（ADR-0186，不走 bus）。注意分叉：`bus.publish` 与 `publish_via_session`
   是两条发布路径，而 `hook.before_publish`/`after_dispatch` 的占位方法暗示"未来走 bus pipeline"——
   读者必须同时持有"现在走 session、未来可能走 bus"两套心智模型。
2. **哪些 module 是 shallow？** ① `publisher._build_hook()`：单行 lazy import 包装，
   interface == implementation；② `ModelVisibleHook.before_publish`/`after_dispatch`：
   no-op 的 Protocol 形状占位，注释明说"为未来 PR 切 bus pipeline 形态时 0 改动"保留——
   教科书式的 **one adapter = hypothetical seam**；③ `_coerce_tools`/`_coerce_messages`：
   两份逐字相同的 4 行函数（见 duplication 扫描）。
3. **为可测性抽出的纯函数 vs 真正藏 bug 的调用点？** `_canonical_digest`/`canonicalHeader`/
   `headerEquals` 是纯的、可测的；真正的 bug 曾藏在 `capture_pre_llm` 的 fold-key/计数器时序里——
   注释自证："此前先 +1 导致 key 恒为新 step，fold 分支不可达"。`_step_counter`/`_last_headers`/
   `_resume_run_step`/`_last_step_id` 四个并行状态结构**没有 locality**，分散在 `__init__`/
   `mark_resume`/`forget_run`/`capture_pre_llm` 四处。已修复且有注释钉住，本轮不 story，记一笔。
4. **哪里 leak 过 seam？** ① **pydantic forward-ref 缺陷泄漏**：`lca_kernel/events/payloads/model_visible.py`
   的 `AssistantRequestConfig`/`MessageDict`/`ToolCallDict`/`UsageDict` 只在 `TYPE_CHECKING` 块 stub 为
   `Any`，字段却用字符串 forward-ref 声明——pydantic v2 不解析，缺陷泄漏到**两个**消费者：
   `hook.py` 与 `fold_source.py` 各有一份 ~20 行 import-time `model_rebuild(force=True, _types_namespace=Any…)`
   仪式，外加 `publisher.py` 的 eager import（`# noqa: F401` 自证 unused，纯为触发 hook 模块的副作用）。
   缺陷的主人在 payloads 模块，补丁却住在消费者家里——**leaky seam** 实锤。② `_coerce_producer`
   名字是 producer，却被 `subscribe(plugin=…)` 复用——命名泄漏，单点 cosmetic，不 story。
   ③ `_canonical_digest` 内 `import json` 函数级导入（stdlib，无环风险，记一笔）。
5. **哪些部分测不到 / 只能绕过 interface 测？** payloads 模块**无法独立测试**：不先 import hook 或
   fold_source 触发 rebuild 副作用，直接实例化 payload 抛 `class-not-fully-defined`；
   仪式是 import 顺序依赖的，测试"碰巧"通过取决于 conftest 的 import 顺序。这是 RA-024 的 testability gap。

### Area B — cron/proactive 双 tick 调度器

1. **跳跃**：理解"一次 tick 如何互斥"现在只需读 `scheduler_file_lock.py`（收敛成功，locality 好）；
   剩余跳跃在两调度器各自的 `_acquire_lock`/`release_lock` 直通对 vs `self._file_lock` 直接调用之间——
   两层薄间接，理解"锁在哪"要多跳一次。
2. **Shallow**：两个类里**逐字重复**的 `_acquire_lock`/`release_lock` 直通对——interface == implementation，
   而真正的 seam（`SchedulerFileLock`）已经存在。另 `STALE_ABSOLUTE_CAP_S` 被两个 scheduler 模块
   import 进 `__all__` 再经 `cron/__init__.py`、`proactive/__init__.py` 二次 re-export——
   常量的主人是 `scheduler_file_lock`，两模块本体**零引用**（全仓 grep：除链条自身与定义处，零外部引用，
   tests 亦无）。
3. **纯函数 vs 调用点**：`next_run`（domain/cron）、`decide`（cognition/proactive）是纯的、有 locality；
   bug 风险在 `_tick_locked` 的 `js` dict——`last_run_ms`/`attempts`/`next_retry_ms`/`last_error`
   四个字符串 key 以字面量散落在 `_tick_locked`/`_run_job`/`_write_dead_letter`/`_prune` 四处，
   state 记录没有自己的 module（无 locality）。无失败证据，speculative，本轮不 story，记一笔。
4. **Leaky seam**：即上述 `STALE_ABSOLUTE_CAP_S` re-export 链——收敛 commit（8308bd07f）把实现收走了，
   兼容垫片没带走。按 repo COMPAT 纪律（"兼容 shim 同 PR 可删"）本应在收敛时同删。
5. **Testability**：`release_lock` 是公开面（`tests/integration/proactive/test_pipeline.py` 调 6 次），
   `_acquire_lock` 是私有仅 tick 内用——不对称说明有机生长；state dict 的形状只能经 tick 集成测试
   间接测，没有 interface。

### Area C — narrative fold 章节渲染

1. **跳跃**：理解"fold 不可用时 narrative 显示什么"要读 5 个 `_render_*` 各自开头的 guard——
   同一 `fold is None or fold.header is None` 仪式 ×5（标题各异）；理解单章实现要同时看 `fold.py`
   与 `sections.py`（`_short` 是跨模块 import 的**私有**名字）。
2. **Shallow**：5 个 guard 每个都是 `if …: return [f"…{_FOLD_NA}"]`——"本章的 N/A 策略"这个 interface
   几乎等于一行 if 的 implementation；`_tool_name`/`_tool_description` 两份近乎相同的嵌套 Mapping
   回退仪式（`function` 嵌套 key 的双层降级）。
3. **纯函数 vs 调用点**：`_render_*` 全纯、可测性好；风险在 `_render_fold_chapters` 的 budget 截断手工会计
   （`+1 for join newline`）——聚合器的字符会计没有 locality 到各章，但 budget 本就是聚合职责，不 story。
4. **Leaky seam**：`from …sections import _short`——跨模块 import 私有名字，`_short` 的主人是 sections，
   fold 应该走公开面或自有 helper；`FoldProvider` 类型别名定义在 fold.py（消费者侧）而非
   `fold_source.py`（`FoldedModelVisible` 的生产者侧）——seam 放错边。
5. **Testability**："fold 不可用→占位"是**一个**策略，却只能逐章测试（5 个测试钉同一策略）；
   `_render_fold_chapters` 的聚合 interface 测不到单章 N/A 标题——策略没有单一测试面。

## Runtime verification（mandatory，真跑）

环境：252，分支 `raphy/arch-20261008-0206`（== main `ca80cdd25`），`LLM_API_KEY=dummy`，MockLLMAdapter。

| # | 场景 | 结果 |
|---|------|------|
| (a) | basic run：`ensure_default_ctx()` + `Agent(tools=[], llm=MockLLMAdapter()).run('smoke')` | ✅ completed |
| (b) | tool-call run：CalcTool + OnceMock（首轮 tool_call，次轮收敛） | ✅ completed |
| (c) | 同一 agent 连续两次 run | ✅ completed / completed |
| **P0** | 非收敛 run：InfiniteMock（永远返回 tool_call）+ `max_steps=5` | ❌ **复现**：`await agent.run()` 直接抛 `lca.contracts.protocols.graph.errors.LoopObligationExceededError`（`phase.main.outer: edge 'act.main' → 'think.main' exhausted loop.maxIterations=24`），未返回 Result——与 2026-10-07 `runtime-findings-20261007.md` 一致，**未修复** |

P0 新证据（本轮探针）：日志里框架自己记了
`runtime_lifecycle … lifecycle_event=failed … status=failed max_steps=5`——框架**知道** run 失败了，
但异常仍逃逸到调用方，没有翻译成 failed Result。另：`max_steps=5` 未在 5 步停下，
graph 层 `loop.maxIterations=24` 先耗尽——**两套步数限制脱节**（agent 层 max_steps vs graph 层 loop bound）。

## Duplication scan（secondary，friction walk 之后）

- `hook.py`：`_coerce_tools`/`_coerce_messages` 逐字相同（4 行 ×2）→ 并入 RA-024
- `step-{n:03d}` 派生 ×4：`hook._step_id_for` / `lca/plugins/primitive/llm_call/invoke.py:116` /
  `lca/nodes/think/llm/invoke.py:190` / `lca/cognition/brain/reasoner/reasoner.py:232`；
  其中 llm_call 与 reasoner 的 cursor→step_id 回退仪式（含 `step-unknown-{template_id}`）**逐字相同 7 行** → RA-025
- `STALE_ABSOLUTE_CAP_S` re-export 链 4 处（2 scheduler 模块 + 2 包 `__init__`），零外部引用 → RA-026
- `fold.py` N/A guard 仪式 ×5 → RA-027
- `_acquire_lock`/`release_lock` 直通对 ×2 模块 → RA-026
- 明确**不收敛**：bus.py 内部 helpers 各司其职；两 scheduler 的 tick 主体语义不同
 （cron：worker 槽/排队/重试；proactive：裁决/投递/死信）——强行收敛是 speculative

## Candidate table

| id | Files | Problem | Solution | Benefits（locality + leverage） | Strength |
|----|-------|---------|----------|-------------------------------|----------|
| RA-023 | `lca/agent/cognitive_agent.py`（run 路径）, `lca/framework/graph/interpreter.py` | 非收敛 run（真实 LLM 常见）直接把 `LoopObligationExceededError` 抛给调用方，拿不到 Result；`max_steps` 与 graph 层 `loop.maxIterations` 两套步数限制脱节（max_steps=5 实际跑了 24 次 graph 迭代） | 在 `Agent.run()` 建异常翻译 seam：graph 层机制错误 → failed Result（带 error 事实），`CancelledError` 继续透传；spike 定 max_steps 与 loop bound 的对齐方式（二选一：agent 层把 max_steps 翻译成 graph bound，或 run 内按 max_steps 主动终止） | **locality**：终止契约收进 run() 一处，调用方不再各自 try/except graph 内部错误；**leverage**：所有上层（Team pipeline、cron worker、handoff）免费获得 fail-closed | **Strong** |
| RA-024 | `lca_kernel/events/payloads/model_visible.py`, `lca/plugins/events/hooks/model_visible/hook.py`, `lca/infrastructure/observability/replay/fold_source.py`, `lca/plugins/events/publishers/model_visible/publisher.py` | payloads 模块的 forward-ref 缺陷（TYPE_CHECKING stub 为 Any，字段字符串引用）泄漏到两个消费者：hook.py 与 fold_source.py 各有一份 ~20 行 import-time rebuild 仪式；publisher.py 的 eager import（`noqa: F401`）纯为触发副作用 | 缺陷在源头自愈：payloads 模块内一次 `model_rebuild(_types_namespace=Any)`（PR-0 shim，注记 delete-when：`lca_kernel.events.types` 真实类型落地）；删两处消费者仪式 + publisher 的 eager import；顺手收敛 `_coerce_tools`/`_coerce_messages` | **locality**：Any-pinning 住在类型的主人家里，消费者不再为别人的缺陷做 import-time 手术；**leverage**：未来第 3 个 payload 消费者 0 仪式；payloads 模块可独立测试 | **Worth exploring** |
| RA-025 | `lca/plugins/events/hooks/model_visible/hook.py`（`_step_id_for`）, `lca/plugins/primitive/llm_call/invoke.py`, `lca/nodes/think/llm/invoke.py`, `lca/cognition/brain/reasoner/reasoner.py` | `step-{n:03d}` 约定四处独立派生；llm_call 与 reasoner 的 cursor→step_id 回退仪式（含 `step-unknown-{template_id}`）逐字相同 7 行——改格式要改四处，漏一处 fold key 对不上 | 给 step_id 格式一个 seam（如 contracts 层的 `step_id_for(n)` + `step_id_from_cursor(cursor, template_id)`），四处调用；spike 定落点（`lca/contracts/atoms/ids` 随 `new_id`，或 cursor 附近） | **locality**：step_id 形态单源，fold key/hook key/reasoner key 不再各自拼字符串；**leverage**：下次改格式（如下划线变体之争）只改一处 | **Worth exploring** |
| RA-026 | `lca/infrastructure/cron/scheduler.py`, `lca/infrastructure/proactive/scheduler.py`, `lca/infrastructure/cron/__init__.py`, `lca/infrastructure/proactive/__init__.py` | lca-1000 第 0520 轮把文件锁收敛进 `SchedulerFileLock`，但收尾没做完：两调度器各留逐字相同的 `_acquire_lock`/`release_lock` 直通对；`STALE_ABSOLUTE_CAP_S` 被 4 处 re-export（2 模块 + 2 包 `__init__`），全仓零外部引用（含 tests） | 删私有的 `_acquire_lock` 直通（tick 内直调 `self._file_lock.acquire`）；`release_lock` 是公开面（test_pipeline.py 用 6 次）**保留**；删 4 处 `STALE_ABSOLUTE_CAP_S` re-export（`scheduler_file_lock` 自身保留） | **locality**：锁的 seam 只剩 `SchedulerFileLock` + 公开的 `release_lock`，无薄间接层；**leverage**：小，但这是"收敛做完"的诚实收尾，避免后人误以为旧路径还活着 | **Worth exploring** |
| RA-027 | `lca/infrastructure/observability/journal/step/narrative_writer/fold.py`（+ `sections.py` 的 `_short`） | 5 个 `_render_*` 章节各重复 `fold is None or fold.header is None` 的 N/A guard（同一策略，5 个测试面）；`from …sections import _short` 跨模块 import 私有名字；`FoldProvider` 类型别名定义在消费者侧 | 章节注册表 + 单一 driver：`_chapter(title, render_body)`，driver 统一做 None-guard 与 N/A 标题；`_short` 公开化或 fold 自有；`FoldProvider` 搬到 `fold_source.py`（生产者侧） | **locality**："fold 不可用→占位"策略一处定义、一处测试；**leverage**：加第 6 章节不再复制 guard | **Worth exploring** |

## Top recommendation

**先做 RA-023**。它是本轮唯一的 Strong，也是两次运行时验证（10-07 findings + 本轮复现）钉住的真 P0：
真实 LLM 不收敛是生产常见情况，框架内部已经知道 run 失败了（日志 `status=failed`），却把 graph 内部
错误抛给业务调用方——调用方拿不到 Result，整个应用崩。这是"fail-closed"纪律在最关键的 seam
（`Agent.run()`）上的缺口。RA-024 是第二顺位：leaky seam + testability gap 的教科书案例，
修完后 payloads 模块第一次可独立测试。RA-025/026/027 是诚实的收敛收尾，按优先级 1-2 排。

## Self-grilling

### RA-023 — run() 非收敛异常翻译 + max_steps 对齐

- **Constraints**：`Agent.run()` 的公开契约是"返回 Result"（调用方不处理 graph 内部错误类型）；
  `asyncio.CancelledError` 必须继续透传（取消语义不可吞）；`max_steps` 的用户语义（"最多 N 步"）不能
  被悄悄放宽；interpreter 抛 `LoopObligationExceededError` 是机制层的合法行为（ADR 未禁止），
  约束只在"谁翻译"不在"抛不抛"。
- **Dependencies**：上游 `lca/agent/cognitive_agent.py:242`（run 只 catch CancelledError）；
  下游 `lca/framework/graph/interpreter.py:387`（raise 点）；调用方：Team pipeline、cron worker、
  handoff dispatcher——全部期望 Result。seam 移动后这些调用方**删** try/except 而非加。
- **Shape of the deepened module**：run() 内建"终止翻译"：`except (LoopObligationExceededError, …)`
  → 构造 failed Result（error 字段带 plan/edge/taken 事实，原异常进日志/回执，不丢诊断）；
  max_steps 对齐二选一（spike 定）：（a）agent 层把 max_steps 换算成 graph loop bound 注入；
  （b）run 循环内按 max_steps 主动 break 并合成 failed Result。seam 后面是 Result 构造器，
  前面是调用方契约。
- **Test survival**：现有 run 返回 Result 的测试必须全绿；新测试 = 10-07 findings 的 InfiniteMock
  repro（`max_steps=5`）：断言返回 `status=failed` 的 Result 且**不抛**；另加 max_steps 生效测试
  （实际步数 ≤ max_steps，或文档化两套限制的换算关系）。
- **Deletion test verdict**：**concentrates**。删掉翻译 seam → 每个调用方各自 try/except graph 内部
  错误类型（发散）；留着 → 终止语义一处定义。

### RA-024 — payload forward-ref 在源头自愈

- **Constraints**：pydantic v2 行为不可改；`AssistantRequestConfig` 等四名在 PR-0 前恒为 `Any`
  （TYPE_CHECKING 块是 mypy --strict 的 stub）；ADR-0185 §3.3 的 payload 字段语义不变；
  `lca_kernel` 不能反向依赖 `lca`（层向）。
- **Dependencies**：上游 `lca_kernel/events/payloads/model_visible.py`（两 payload 类）；
  下游 hook.py（import-time ritual）、fold_source.py（import-time ritual）、publisher.py
  （eager side-effect import）。改完后三处下游**删代码**，零行为变更。
- **Shape of the deepened module**：payloads 模块尾部 `_self_heal_forward_refs()`：
  对两 payload 类做一次 `model_rebuild(force=True, _types_namespace={四个名: Any})`，
  失败记 debug 日志不挡 import（沿用现有 INTENTIONAL 语义）；注释写 delete-when
  （`lca_kernel.events.types` 真实类型落地即删）。seam 后面是 pydantic 的 quirk，
  前面是"import 即用"的干净模块。
- **Test survival**：现有 hook/fold_source/publisher 测试全绿（行为零变更）；
  新测试：**不 import 任何消费者**、只 `import lca_kernel.events.payloads.model_visible`
  就直接实例化两 payload 类——这是今天写不出来的测试（testability gap 的钉子）。
- **Deletion test verdict**：**concentrates**。workaround 从 3 个消费者收进 1 个类型主人；
  删掉自愈 → 回到每消费者一份仪式（现状）。

### RA-025 — step_id `step-{n:03d}` 单源

- **Constraints**：`step-NNN` 字符串形态是 fold key/hook key 的匹配依据，字节形态不能变；
  `step-unknown-{template_id}` 回退语义保留；`step_{n:03d}` 下划线变体（journal_fold 缺省、
  writable_matrix）**不在 scope**（不同 surface，可能 load-bearing，本轮只观察）。
- **Dependencies**：四处调用点（hook / llm_call / nodes/think / reasoner）；落点二选一
  （spike 定）：`lca/contracts/atoms/ids`（随 `new_id`，底层无反向依赖）或 cursor 附近。
  `_step_id_for` 的 docstring（"与 LoopCursor step_id 形态一致"）是约定唯一的文字记载，
  收敛时把这句话搬进新 seam 的 docstring。
- **Shape of the deepened module**：`step_id_for(step_index: int) -> str`（纯格式）+
  `step_id_from_cursor(cursor, template_id: str) -> str`（cursor 缺席/异常 → 回退串，
  收掉 llm_call 与 reasoner 的逐字 7 行）。seam 后面是 `:03d` 格式串，前面是四个调用点。
- **Test survival**：现有 step_id 相关测试（fold key 匹配、hook 测试）全绿；
  新测试：`step_id_for(3) == "step-003"` + `step_id_from_cursor(None, "t") == "step-unknown-t"`——
  约定第一次有直接测试面。
- **Deletion test verdict**：**concentrates**。格式知识从四处收进一处；删掉 → 回到改格式改四处。

### RA-026 — 调度器收敛收尾

- **Constraints**：`release_lock` 是公开面（test_pipeline.py 用 6 次），**保留**；
  `SchedulerFileLock` 的语义（stale 收割记 warning）不动；ADR-0263 §9 不动。
- **Dependencies**：两 scheduler 的 tick()（`_acquire_lock` 唯一调用方）；
  `STALE_ABSOLUTE_CAP_S` 的 4 处 re-export——grep 证零外部引用，删无波及。
- **Shape**：tick 内直调 `self._file_lock.acquire(now_ms)`；删两模块的 `_acquire_lock`；
  删 4 处 re-export（模块 `__all__` 与包 `__init__` 同步清）。
- **Test survival**：cron/proactive 调度器测试全绿；`grep -rn STALE_ABSOLUTE_CAP_S` 只剩
  `scheduler_file_lock.py` 自身。
- **Deletion test verdict**：**concentrates**（删的是薄间接层与死垫片，不是搬移）。

### RA-027 — fold 章节 N/A 策略单源

- **Constraints**：5 章节的 N/A 标题文案**逐字保留**（viewer 快照可能 pin 住）；
  `char_budget` 截断语义不动；`_render_fold_chapters` 的聚合签名不动。
- **Dependencies**：上游 `fold.py` 5 个 `_render_*`；下游 `writer._render_step`（调聚合函数）；
  `sections._short`（私有，被跨模块 import）。
- **Shape of the deepened module**：`_chapter(na_title: str, body: Callable[[FoldedModelVisible], list[str]])`
  driver——None-guard 与 N/A 标题一处做，各章只给 body；`_short` 公开化（改名 `short_text`）
  或 fold 自有 `_truncate`；`FoldProvider` 搬 `fold_source.py`。
- **Test survival**：现有 narrative 测试全绿（文案逐字）；新测试：driver 级——
  传 None 得 5 章 N/A 标题（一个测试钉整个策略，替代 5 个逐章测试）。
- **Deletion test verdict**：**concentrates**。"fold 不可用→占位"从 5 处收进 1 处。

## 丢弃（有证据）

- `ConsumerHandle.unregister` no-op 占位：bus.py docstring 明说"框架不提供退订路径"——刻意设计，非 friction。
- `_coerce_producer` 被 subscribe 复用：命名小瑕疵，单点、无杠杆，不开 story。
- bus.py 的 ambient trace_id 三件套（set/reset/current）：与 `_resolve_trace_id` 解析链同模块是**好**的
  locality，搬出去是发散。
- `ProactiveScheduler` 的 stringly-typed `js` state dict：真 friction（key 字面量散四处、无 module），
  但无失败证据，fix 形状 speculative——记入 patterns，留待未来有 bug 时立案。
- `ModelVisibleHook` 的四并行状态结构（counter/headers/resume/last_step_id）：过去出过 fold-key bug
  但已修复且注释钉住，无新证据，不开 story。
- `run(None)` 的 TypeError、`NativeToolCall.arguments` 传 str 的晦涩报错（10-07 findings P2）：
  真问题但属小 fail-loud 缺口，杠杆低于本轮 5 个——defer 给 iter-quality lane，不在本轮立案。
- `step_{n:03d}` 下划线变体（journal_fold 缺省 / writable_matrix）：观察到，未立案（不同 surface，
  可能 load-bearing）。
- before_publish/after_dispatch 占位：hypothetical seam，按 YAGNI 应删——但它是 ADR-0185 PR-3 的
  显式计划（"0 改动切换"），删了是跟 ADR 对着干；记入 patterns，PR-3 落地或流产时再议。
