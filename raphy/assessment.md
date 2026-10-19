# Raphy Assessment — 2026-10-19 22:45 轮

## 范围与方法

- **热点定位**：`git log --oneline -40 main`（非 merge）：最近两周最热的是 (a) 用户自己的两个 HITL/tool_defer 修复 PR（`ec141e124`、`1188c7b97`，已合 main #47/#48）；(b) browser 工具簇（RA-147~157 刚收敛完）；(c) webserver runs lifecycle（lca-1000 领地，禁区，跳过）；(d) docs/plans（文档，非代码）。
- **摩擦漫步 Area A**（子任务，只读零写入）：`lca/infrastructure/tool_defer/` 全包精读（session.py 383 行、policy.py、tool_search.py、names.py）+ HITL resume 恢复链（point.py 全文、runtime_loop.py 相关段、reducer 协议与 plugin、carrier/lifecycle.py、recovery.py、webserver handlers 相关段）。
- **摩擦漫步 Area B**（协调者亲自验证）：`lca/infrastructure/tools/browser/tools.py` 全类扫描（声明参数 vs execute 实际读取，机械扫描 + 误报剔除）+ `task_store.py` + 全仓 `url_id`/`outlink_idx`/`line_start`/`register_task`/`BrowserTaskRecord(` 生产调用者 grep。
- **运行时验证**（强制）：沿用 2026-10-14 版脚本（改 worktree 路径），4 场景全 PASS（A 基础 run COMPLETED / B 工具调用 COMPLETED / C 双轮 run COMPLETED / D 不收敛 run 返回 failed 无异常，RA-023 回归守住），failures=0，无新增 P0。
- **禁区遵守**：preamble.py、ralph Round 2（DecisionGates/Ingest/ContextFiles shims/read-runs/`infrastructure/tools/assistant/`/`lca/cognition/memory/`）、lca-1000（`contracts/event.py` PILOT、`plugins/transport/webserver/`——resume 链读的是 session 插件与 carrier/recovery，未进 webserver 禁区文件）、gate_chain_strategy.py、typed port 迁移、`CursorRecord` DI 均未碰未提案。

## 五问答案摘要

**Area A（tool_defer + HITL resume）**：
- Q1（概念是否散在多模块）：是。两个刚修好的概念都是 5 文件概念："resume 恢复 loaded 集合"（session.py → terminal/lifecycle.py → session/session.py → recovery.py → carrier/lifecycle.py）；"resume 排除暂停时长"（agent.py → point.py → runtime_loop.py → reducer.py → plugin.py）。且两者走**两条并行恢复通道**：`paused_at` 走类型化 `ApprovalResumePoint`，`loaded_namespaces` 走无类型 bundle dict 字符串键——"resume 到底恢复什么"没有单一 module 拥有。
- Q2（浅模块）：`_capture_loaded_namespaces()`（9 行）、`_paused_seconds_since`（11 行）都浅，但 deletion test 结论是**它们不是删除点**——它们承载的兼容性规则/调用点 invariant 才是问题（见候选 1、3）。`_optional_float` 等 12 个 micro-helper 是家族级 depth，单删无意义，不提案。`names.py` 薄但不浅（双向映射真逻辑），保留。
- Q3（纯函数 vs 调用方式 bug）：`_paused_seconds_since` 可单测但**零覆盖**；过去两周两个生产 bug 都住在 wiring（bundle 带没带键、snapshot.created_at 被谁写成什么），不在纯函数里。`_capture_loaded_namespaces` 的"每个 pause 路径都必须 capture" invariant 分散在 2 个调用点，无 module 强制。
- Q4（seam 泄漏）：三处——① `StateSnapshot.created_at` 在 resume 路径被重载为暂停时刻（最重，contracts 层 SSOT 在撒谎）；② `bind_resume_capabilities` 手工镜像 create-run 的 `DeferPolicy.for_vocal_mode` 推导（"Mirror the create-run policy (ADR-0248)" 注释，人肉同步）；③ terminal 层函数级局部 import 伸手进 infrastructure 的 defer ContextVar。
- Q5（测试缺口）：`ToolDeferSession(loaded_namespaces=[...])` seed 路径零直接测试；`_paused_seconds_since` + `DefaultReducer.apply_resume` 的 budget 平移零覆盖（`test_resume_point_paused_at.py` 只到 point.py round-trip 就停）；`validate_bundle` 是否校验 `loaded_namespaces`——本轮已确认：**不校验**（函数体只查 run_id/approval_request/resume_point），`_restore_from_bundle:306` 的 `bundle.get("loaded_namespaces") or ()` 绕过 load contract（`frozenset("abc")` 会静默变成字符集，错类型不炸）。

**Area B（browser tools）**：
- 机械扫描（误报已剔除：`BrowserSearchTool.items` 是 verticals schema 的 items；`BrowserSetCaptchaPreferenceTool.kind/value` 是嵌套 scope 内读取）确认三处**声明了但 execute 零读取**的参数：`BrowserOpenTool.outlink_idx`/`line_start`、`BrowserLookupCitationUrlTool.url_id`、`BrowserSteerTaskTool.user_requested_screenshot`。
- `BrowserOpenTool.url_id`（schema："此前 search 或 open 返回的页面 ID 或搜索会话 ID"）被 `str(args.get("url") or args.get("url_id"))` 直接拼进 URL：整数 page ID 5 → `_normalize_url` → `"https://5"`，然后**宣称打开成功**。全仓（lca/ + tests/）除 tools.py 自身外零 `url_id`/`outlink_idx`/`line_start` 生产者——LLM 是唯一可能调用方，拿到的是垃圾导航 + 成功谎言。RA-148 同类（叙事≠实现）。
- `BrowserTaskStore.register_task` / `BrowserTaskRecord(` 全仓 lca/ 零生产调用者（只有 tests/ 在用）：按 RA-149 pattern 这是刻意留下的测试供数 seam，不是 bug，不开 story；但记一笔——任务生命周期工具簇在生产侧当前无 producer（spawn 已 fail-closed），属产品缺口而非架构摩擦，ADR 级别，本轮不动。

## 候选表

| ID | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|---|---|---|---|---|---|
| RA-158 | `lca/infrastructure/tools/browser/tools.py`（BrowserOpenTool / BrowserLookupCitationUrlTool / BrowserSteerTaskTool） | 工具 schema 声明了实现根本不读的参数（open 的 outlink_idx/line_start；lookup 的 url_id；steer 的 user_requested_screenshot），且 open 把整数 url_id `str()` 后拼成 `https://5` 去导航并返回成功——LLM 面契约撒谎 | validate 层 fail-closed：出现不支持的参数直接返回命名错误；url_id 仅当本身是合法 URL 时才沿用旧路径，否则 fail-closed（"页面 ID 解析尚未实现，请直接传 url"） | "哪些参数真有效"的知识从"散在 schema 描述与实现的不一致"收敛到 validate 一处；leverage：以后任何参数增删都在 validate 有单一真值，LLM 得到可行动的错误而非静默垃圾 | Strong |
| RA-159 | `lca/contracts/models/core/state/state.py`（StateSnapshot）、`lca/plugins/session/runtime/resume/point.py`（resume_point_to_state_snapshot）、`lca/runtime/loop/runtime_loop.py`（_paused_seconds_since） | `StateSnapshot.created_at` 在 resume 路径被重载为 WAITING_INPUT 暂停时刻，其他路径是快照创建时间——contracts 层字段双语义，`_paused_seconds_since` 的正确性依赖 point.py 一个 if 分支 + runtime_loop.py 一段 docstring 的口头约定；1188c7b97 整个修复骑在这个重载上 | 给 StateSnapshot 加显式字段 `paused_at: datetime \| None = None`；resume_point_to_state_snapshot 写它、不再碰 created_at；_paused_seconds_since 改读 `snapshot.paused_at`（None→0 秒）；created_at 恢复单一语义 | pause 语义第一次有了自己的名字，不再寄生；leverage：以后任何 wall-clock 读者读显式字段，不再需要知道重载约定；旧 bundle（无 paused_at）自然得 None→0，迁移零风险 | Strong |
| RA-160 | `lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py`（bind_resume_capabilities）、run entry 的 policy 创建处、`lca/infrastructure/tool_defer/policy.py` | "这个 run 用什么 defer policy" 的推导写了两遍：run entry 一处，resume bind 侧手工镜像（注释 "Mirror the create-run policy (ADR-0248)"）；`for_vocal_mode` 每演进一次 resume 侧必须人肉同步 | 抽共用纯函数（如 `defer_policy_for_run(vocal_mode, ...)`），两处调用点都调它；输入显式化 | 推导知识从两处调用点收进一个 adapter；leverage：下次 policy 演进只改一处，resume 侧不可能再漏同步 | Worth exploring |
| RA-161 | `lca/plugins/transport/webserver/carrier/runs/recovery.py`（validate_bundle） | validate_bundle 自称 "the one place that decides what a resume bundle must contain"，但 `loaded_namespaces` 键绕过它（`frozenset("abc")` 式静默错义不炸） | load contract 覆盖该键：present 时必须为 `list[str]`，否则 bundle 判 corrupt（→ None → 404 路径）；absent 仍允许（兼容 10-19 前的老 bundle，沿用 `or ()` 默认） | "bundle 里能装什么"的判定权真正回到 validate_bundle；leverage：以后新增 bundle 键有现成的类型门可挂 | Worth exploring |

**记录但不开 story**：① resume 双通道（类型化 point vs 无类型 bundle dict）——需要先定层边界（`loaded_namespaces` 是 webserver 层概念，`ApprovalResumePoint` 住 session 层），贸然并入可能污染层边界；RA-161 先解决其中可落地的具体子项。② 任务存储生产侧无 producer——产品缺口，ADR 级别。③ `_tool_to_spec` 双胞胎（session.py vs think.history.assemble）——刻意 duplication（分层约束），"同一性"不可测是已知 trade-off，不对抗。

## 自我诘问（per-candidate grilling）

### RA-158
- **Constraints**：工具 schema 是 LLM 面契约，不能静默改语义；RA-147 的 honesty 纪律（未知引用 fail-closed）是直接先例；`BrowserSpawnTaskTool`/`BrowserDeepResearchTool` 已是 `_UnimplementedTool`，其参数是刻意 inert——**不动它们**，只动三个"宣称能干活"的工具。`browser_preview` e2e（test_browser_preview_and_takeover_e2e.py）走的是正常 open 路径，必须保持绿。
- **Dependencies**：调用方只有 LLM（全仓零内部 producer 已验证）；`BrowserOpenTool.validate()` 已有返回错误字符串→execute 转 fail-closed Observation 的现成管道。
- **Shape of the deepened module**：validate 里加命名检查：`outlink_idx`/`line_start` 出现 → `"暂不支持 outlink_idx/line_start，请直接用 url 打开目标页"`；`url_id` 无 `url` 且非 URL 形态 → `"url_id 页面 ID 解析尚未实现，请直接传 url"`；`BrowserLookupCitationUrlTool` 的 `url_id` 出现 → 同款 fail-closed；`BrowserSteerTaskTool` 的 `user_requested_screenshot` 出现 → `"截图需求参数暂不支持，已忽略指令本身"`（fail-closed 而非静默忽略——steer 的指令注入是主要求，截图是附加，error 里说清"指令已受理、截图需求未受理"？不——fail-closed 纪律要求要么全拒要么说清。steer 的语义是"注入指令"，截图只是附加需求；最诚实的是受理指令但在 details 里声明 screenshot 未被处理。决定：steer 走"受理+details 声明未处理项"（叙事==实现，RA-148 第二选项），open/lookup 走硬 fail-closed（参数决定导航目标，错了必须拒）。）
- **Test survival**：现有 open/search/find/lookup 测试钉的是正常路径；新增测试钉 fail-closed 三条（整数 url_id、outlink_idx、lookup url_id）+ steer details 声明。
- **Deletion test verdict**：把"不支持"知识删掉 → 回到静默垃圾；validate 里的检查**集中**了"哪些参数真有效"的知识，earn 存在。concentrates。

### RA-159
- **Constraints**：StateSnapshot 是 contracts 层，改字段是 SSOT 级改动；旧 bundle（无 paused_at）必须零行为变化（None→0 秒）；`created_at` 的其他读者——实现时 grep 确认 resume 路径只有 `_paused_seconds_since` 在消费暂停语义。
- **Dependencies**：point.py（写）→ state.py（字段）→ runtime_loop.py（读）；`apply_resume(paused_seconds=)` 协议与 `DefaultReducer` 不动（输入不变，只是来源从重载字段变显式字段）；`ApprovalResumePoint.paused_at` 的 serialize/deserialize 已存在。
- **Shape of the deepened module**：`StateSnapshot.paused_at: datetime | None = None`；`resume_point_to_state_snapshot` 里 `if point.paused_at: kwargs["paused_at"] = ...` 替代现在的 `kwargs["created_at"] = ...`；`_paused_seconds_since(snapshot)` 读 `snapshot.paused_at`，None → 0.0；docstring 里那段"旧 bundle 得零"的口头约定删除（由类型默认值表达）。
- **Test survival**：`test_resume_point_paused_at.py` 的 round-trip 测试继续绿；新增：paused_at 经 snapshot round-trip、旧 snapshot（无 paused_at）→ 0 秒、`DefaultReducer.apply_resume` 的 budget 平移被 paused_at 驱动（补 Q5 的测试缺口）。
- **Deletion test verdict**：删掉重载 → pause 语义第一次有了名字；知识从"if 分支 + docstring 口头约定"**集中**到类型字段。concentrates。

### RA-160
- **Constraints**：ADR-0248 的 vocal-mode eager 策略语义零变化；先 grep 找到 run entry 的 policy 创建处（实现时做）。
- **Dependencies**：两处调用点 + `policy.py`（`for_vocal_mode` 的家）。
- **Shape of the deepened module**：`policy.py`（或其邻近）新增纯函数 `defer_policy_for_run(vocal_mode, ...)`（参数按 run entry 现状显式化）；run entry 与 `bind_resume_capabilities` 都调它，bind 侧删掉 "Mirror" 注释的手工推导。
- **Test survival**：defer policy 现有测试钉行为；零行为变化，只收敛调用点。
- **Deletion test verdict**：删掉镜像 → 推导知识从两处**集中**到一处。concentrates。

### RA-161
- **Constraints**：validate_bundle 的 fail-closed 哲学（corrupt → None → handler 404）；`write_resume_bundle` 写的是 `sorted(session.loaded_namespaces)`（list[str]）；10-19 之前的老 bundle 没有该键——absent 必须允许。
- **Dependencies**：仅 recovery.py 内部；`_restore_from_bundle` 在 validate 之后读，可信任类型。
- **Shape of the deepened module**：validate_bundle 加一段：`"loaded_namespaces" in data` 时必须 `isinstance(list)` 且全 `str`，否则 return None；absent → 通过（下游 `or ()` 保持）。
- **Test survival**：现有 resume bundle 测试；新增：错类型（str/dict）→ None，缺键 → 通过。
- **Deletion test verdict**："bundle 能装什么"的判定**集中**回自称唯一判定点的 validate_bundle。concentrates。

## Top recommendation

先做 **RA-158**：LLM 面契约撒谎是离用户最近的谎言（调用方直接拿到 `https://5` 的"成功"），且全仓零内部 producer、零兼容风险，是最干净的 Strong。接着 **RA-159**：contracts 层 SSOT 字段双语义，刚落地的生产修复骑在上面，不收敛则下一个 wall-clock 读者还会踩。然后 **RA-161**（小而实，补 load contract 缺口），最后 **RA-160**（需先定位 run entry，稍重）。

## Diversity quota

- 摩擦漫步来源：RA-158（browser 工具簇精读：被忽略的声明参数 + url_id 语义错乱）、RA-159（tool_defer/HITL 恢复链精读：contracts 层 seam 泄漏）。✓ 不是全 duplication。
- RA-160/161 是 wiring 收敛类（"two = real" 的变体：两处推导 / 判定点名实不符），属次要但非注水——每条都有 deletion test 通过的证据。

## 运行时验证记录

脚本：`/tmp/raphy-verify-20261019.py`（由 hidden_files/raphy-runtime-verify-20261014.py 改 worktree 路径），`env LLM_API_KEY=dummyprobe python3` 经 stdin 在 worktree 跑。
结果：A 基础 run COMPLETED / B 工具调用 COMPLETED / C 双轮 run COMPLETED / D 不收敛 run → status=failed 无异常（RA-023 回归守住），`DONE failures=0`。无新增 P0/P1。

---

Assessment complete: 4 stories written, top is RA-158.
