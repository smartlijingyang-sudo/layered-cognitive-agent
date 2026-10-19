# Raphy Assessment — 2026-10-20 01:45 轮

## 范围与方法

- **热点定位**：`git log --oneline -40`：最近两周几乎全部是 raphy 自己的收敛工作（browser 工具簇 RA-147~157、tool_defer/HITL RA-158~161）与 webserver runs lifecycle（lca-1000 领地，禁区）。按 skill "scattered 则拓宽" 规则，选了三块**新领地**做摩擦漫步：
  - **Area A**（子任务，只读）：cordis creator assistant dynamic bridge + preset registration —— 用户刚落地的 `41e92781e`，raphy 从未碰过。精读 `lca/infrastructure/tools/dynamic/bridge.py`（262 行）、`lca/infrastructure/preset/discovery.py`（228 行）、`lca/infrastructure/preset/fs_repository.py`（358 行）、`lca/plugins/tools/cordis_control/creator_runtime.py`（200 行）、`lca/plugins/tools/cordis_control/loader.py`（143 行）、`lca/plugins/tools/cordis_control/tool.py`（269 行）+ ADR-0256 一致性测试 + 该 commit 全 diff。
  - **Area B**（子任务，只读）：审批许可链 —— 用户刚修 `8c1624fc7`（shell-tool fallthrough）。全读 `lca/infrastructure/runtime_plane/access/`（approval_engine.py 324 行 + approved_tools/classify/policy/grant/__init__）、`lca/nodes/act/authorize/authorize.py`、`lca/plugins/transport/webserver/carrier/runs/execute/execute.py`、`lca/contracts/protocols/execution/approval_strategy.py` + 两份引擎测试。
  - **Area C**（子任务，只读）：run session 写/读链 —— 最近用户改动的 `lca/runtime/session/run_session_writer.py`（685 行全读）、`lca/runtime/support/null_hook_registry.py`（22 行全读）、`lca/session/lifecycle/recovery.py`（180 行全读），读侧追踪 `lca/plugins/session/runtime/messages/messages.py`、`lca/plugins/session/runtime/projection/reader.py`、`lca/infrastructure/session/emit/lifecycle_emit.py`、`lca/session/append.py`、`lca_kernel/events/fold/inputs.py` + core.py 相关段。
- **运行时验证**（强制）：沿用 `hidden_files/raphy-runtime-verify-20261014.py`（仅改脚本头部日期），252 后台跑。4 场景全 PASS：A 基础 run COMPLETED / B 工具调用 COMPLETED / C 双轮 run COMPLETED / D 不收敛 run → status=failed 无异常（RA-023 回归守住），`DONE failures=0`。无 crash/hang/silent-failure，无新增 P0。
- **先读**：`hidden_files/runtime-findings-20261007.md`（已知 P0 已被 RA-023 修；P2 建议未动，不属架构摩擦）；`CONTEXT.md` + ADR-0256（Area A 的命名空间 fail-fast 合约）。
- **禁区遵守**：`preamble.py`、ralph Round 2（DecisionGates/Ingest/ContextFiles shims/read-runs/`tools/assistant/`/`cognition/memory/`）、lca-1000（`contracts/event.py` PILOT、`plugins/transport/webserver/`）、`gate_chain_strategy.py`、browser 工具簇、tool_defer/HITL resume 链、`resume/` 下除 recovery 引用外的文件。Area B 子任务自声明证据缺口：`tool_defer/*` 与 `tools/assistant/filter.py` 未读，凡涉 session 内部语义均标"反推，未直接验证"——凡建立在该反推上的候选均未开 story（见"记录但不开 story"）。

## 五问答案摘要

**Area A（cordis creator bridge + preset registration）**：
- Q1（sprawl）：是。"一个插件从 author 到可执行"横跨 5 模块，且**三处各自定义"插件入口约定"**：`loader.py:extract_plugin_factory` 只认 `factory`/`<name>_factory` 且 PR12 强制 `plugin_meta`（缺则抛）；`discovery.py:_load_plugin_tool` 认 8 选 1（`factory`/`<name>_factory`/同名属性/`run` + `analyze`/`execute`/`handler`/`main`），meta 可选；`bridge.py:bridge_instance` 认 callable 或 `.execute`。三处的严格度互相矛盾。更实质：同一份 `.py` 在同一进程被 importlib exec **两次**，模块名不同（`lca_agent_presets._runtime.{name}` vs `lca_presets._autonomous.{dir}.{name}`），`sys.modules` 里是两个条目——模块级状态（单例/计数器/缓存）在两条管线里是两份。另：同一流程写盘三次（creator_runtime.py:100-104 draft → loader.py:ensure_plugin_on_disk → fs_repository.py:save + standalone copy），无一处文档说明哪份权威。
- Q2（浅模块）：`DynamicToolBridge.bridge_callable` 纯转发（可删，直接调构造函数）；`CreatorRuntime` 四方法基本是"掏 tool 私有属性 + 转发"，为宪法 §8.2 行数守卫而拆（loader.py:20-23 头注释明说），seam 无信息隐藏（见 Q4）；`resolve_plugin_path` 浅但有两调用者、真 seam，保留；`validate_preset_id` 薄但真（路径穿越防御单点），保留。
- Q3（纯函数 vs 调用方式 bug）：`DynamicPluginToolAdapter.execute` 的 JSON 归一化（bridge.py:65-78）可测（有测试），但风险在调用约定：对**所有**字符串参数做启发式 `startswith("[")/("{")` → `json.loads`，不看 `parameters` schema——合法字符串（如代码文本 `"[1, 2, 3]"`）会被静默改写成 list。`resolve_plugin_path` 零测试，且四段 fallback 哪段生效取决于上游"先落盘还是直接传"的顺序依赖，签名上不可见。`unregister_tool` 传错对象时静默跳过（无 else/无告警）。
- Q4（seam 泄漏）：① `CreatorRuntime` 穿透读 `CordisControlTool` 私有属性（`_composer`、`_actor_role`、`_preset_root`、`_caller_grant`、`_assistant_home`、`_tools_service`、`_safe_executor`），`build_cordis_control_tool` 的动态子类工厂必须把九个 privates 逐一复制进新类——加字段要改两处。② `bridge.py:unregister_tool` 掏 `tools_service._tools` 私有 dict 绕过 ToolsService 注销不变量（ADR-0256 的命名空间 fail-fast 在 register 有、pop 路径无）。③ `solo.py:filter_solo_tools` 用 `getattr(tool, "_assistant_home", None)` 做过滤——改名即静默失效。
- Q5（测试缺口）：`resolve_plugin_path` 沙箱映射分支零测试（本 commit headline 功能的最易错处）；discovery 新增的两处 fallback 无专门测试；`tests/scenario/cordis/test_cordis_creator_assistant_closed_loop.py:390` 直接调私有 `_load_plugin_tool`——"the interface is the test surface"：公共接口把"目录扫描 + quarantine + 批量物化"绑死，只能绕过去；`render_prompt_overview` 每次调用 `discover_presets` → 对每个插件 `exec_module`（import 副作用藏在"渲染"接口后），零隔离性测试。

**Area B（审批许可链）**：
- Q1（sprawl）："这次工具调用要不要停下来问人"需要跳 ~10 模块：`authorize.py:267-268` 每次执行**新建** 5 个 strategy 实例 → 引擎链（HITL → MachineAccess → Namespace → CronMutation → DefaultAllow）→ `NamespaceApprovalStrategy` 读 ambient `current_defer_session()` ContextVar（禁区模块）→ 手工解析 `render_turn()` wire-spec dict（:266-271）→ `canonical_tool_name`（禁区）→ 回到 authorize 的 approved-override（`authorized.py:273-285`，读 `approved_tools` ContextVar ← carrier `resume_run` 注入 ← `session.approved_tool_names`）→ 再 OR 上 `decision.needs_approval`——而这个字段**有三个生产者、两种定义**（`parse.py:112` 的 `requires_human_input` 是 HITL-only；`compose_action.py:120`/`gate/decision_classifier_provider.py:62` 的 `decision_needs_approval` 是全引擎 shim；`interrupt.py:90` 单独再调一次）。同一概念多套定义实现。
- Q2（浅模块）：`ApprovalPolicyRegistry`（approval_engine.py:161-172）：`register`/`list_strategies` 只是 sorted list 包装，**生产零调用者**（git grep：只有定义 + 自身单测）——"one adapter = hypothetical seam" 的反面：zero。`classify.py:135-164` 的 `tool_calls_need_approval`/`machine_calls_need_approval` 自称 "testable core"，但生产零调用（生产走带 ambient ContextVar 的 shim）。`NamespaceApprovalStrategy` 的 `tool_namespaces`/`approval_mapping` 构造参数生产只用无参构造。反例（真深）：`policy.decide_access` 表驱动 verdict；`approved_tools` 的 get/set（carrier 写、authorize 读，two = real）。
- Q3（纯函数 vs wiring bug）：`8c1624fc7` 是标本——bug 不在任何纯函数里，在 `NamespaceApprovalStrategy.evaluate` 的 wiring：`:280-284` 用 canonical alternate 做 visibility 解析，`:292` 调 `namespace_of_tool` 却传 raw 名，同一函数相邻两行两种拼写政策。对照组 `tool_wire_gate.py:146-147` 调同一 seam 时**试了 resolved 和 alternate 双拼写**——同一 seam、两种 miss-handling。用户的 +4 行修复没修 wiring（传 resolved），而是加了静态 `_STANDARD_SHELL_TOOLS` backstop——补丁盖在 wiring 上。`classify.py` 的 "Pure…testable" docstring vs 现实：测的是生产不走的路径。
- Q4（seam 泄漏）：① `:266-271` 手工 `render_turn()` + `spec.get("function").get("name")` 攒 visible 集合，而 session 自有 seam `turn_visible_tool_names()` 已存在（RA-142 建、wire gate 在用）——同一遍历两侧各一份，RA-142 漏网的一个手工作业。② `_SENSITIVE_SUBSTRINGS`（:25-27，对路径字符串子串匹配 `"token"` 等）vs `policy.is_credential_path`（basename/segment 精确匹配）——`"/home/user/mytokenizer/x"` 会被判 SENSITIVE_RESOURCE/HIGH，过度敏感。③ `evaluate` :149-156 的 "explicit allow" 语义只对 `strategy_name == "default_allow"` 生效，`ApprovalStrategy` Protocol 根本没定义这个第三状态——字符串拼写决定链语义。④ `engine :146-147` 非 list/tuple 输入 → `required=False`，安全门 fail-open 且无声。⑤ canonical 双胞胎（`approved_tools.canonical_tool_name` vs 禁区 `tool_defer.names.canonical_tool_name`）等价性无法验证（禁区）——评估时标记为证据缺口，不开 story。
- Q5（测试缺口）：`NamespaceApprovalStrategy` 的 session 分支只能绕 interface（先 `set_current_defer_session` 搭台子）；`_STANDARD_SHELL_TOOLS` 与真实 shell namespace 成员的同步无测试无断言——静态影子集合会默默过期（这正是补丁引入的长期负债）；`:146-147` fail-open 分支无覆盖。覆盖得好的：MachineAccess 纯路径、CronMutation、approved-override ContextVar、RA-131 拒绝不记录。

**Area C（run session 写/读链）**：
- Q1（sprawl）："一个 tool_result 怎么进模型"要在 4 个模块间跳：写侧**自己混用两种词表**（同一文件内：`append_user_message` L211/`append_assistant_message` L254 用 `"surface/user_message"`，`append_tool_result` L323 用 spine 常量 `"spine.body.tool.execute.end"`）；读侧 A（writer 自带 `derive_messages` L394，`startswith("surface/") or == SURFACE_TOOL_RESULT_TYPE` 并集容忍）；读侧 B（plugins `messages.py:76` → kernel `foldSurface`，只认 spine 闭集）；存盘层（`lca/session/append.py:280`）原样存、不归一化。另：`extract_pending_intents_from_events`（L458）与 `extract_pending_browser_widgets_from_events`（L593）逐行对称——two = real，缺参数化的 widget 提取 seam。反例（做得好的）：恢复链写侧 `persist_approval`/`checkpoint` 走 typed catalog（`events.py` 的 `ApprovalPersisted`/`SessionCheckpoint`），读侧只做防御性重校验，两侧共享同一词表。
- Q2（浅模块）：`NullHookRegistry`（22 行全文件）：docstring 自称过时（"platform lifecycle uses RuntimeLifecycle SSOT"），真实现是 `CordisHookRegistry`；唯一引用 `factory_seams_seam.py:76` 的 `register("simple", ...)`，且没找到运行时 resolve `"simple"` 的选择点——one 都没有。`_drop_reasoning_after_dropped_calls`（L130）：名字+docstring 承诺清洗策略，body 直接 `return messages`——删掉它 + L394 那行调用，行为零变化的 dead code。`orphan_dropped_count` plumbing：按自己 docstring "post-PR-2 stays 0 for any well-formed multi-call decision"——为已被上游消除的 bug 类保留的仪表。
- Q3（纯函数 vs 调用方式 bug）：writer 底部 ~200 行纯函数都好测，但 bug 面在 `append_assistant_message` 的调用上下文（L254-292）：widget fallback guard 对上游 payload 形状（observation 输出、browser 工具输出）做私有再发明，无共享 schema——payload 一变，单元测试全绿、生产静默失效。`ensure_intent_widget_in_assistant_message`（L524）用 `intent_id in content` 子串匹配做去重；"已挂载"判断依赖之前落盘的 content 文本，不是结构化状态——surface replace 改写 content 后 mounted 集合会漂移。读侧对称：`derive_event_message`（messages.py:28-74）纯函数，但行为取决于写时有没有预填 `data["message"]`——`append_tool_result` 填了（ADR-0201），`append_assistant_message` 没填，于是同一纯函数对 assistant 走 `data["content"]` 分支并**丢掉 `tool_calls`**。
- Q4（写/读是否各自发明落盘格式）：**是。同一 journal，两个同名 `derive_messages`，三处语义分叉**：① tool_result 内容分叉——content 为空+无 error 时 writer 读出 `"[tool_result] (no output)"`，plugins 读出 `""`；content 空白+有 error 时判断条件不同（`text.strip()` vs `content and err_text`）。② assistant 的 tool_calls：writer 读侧保留，plugins 读侧丢失（assistant 事件无 `data["message"]` → 只剩 content）。③ 词表分叉且 fail-loud：kernel `_surface_op_of`（inputs.py:218-222）对"非合格类型携带 surfaceOp"直接 `raise ValueError`；而 writer 自己写出的正是非合格类型（`"surface/user_message"` + `surface_op="user_message"`，L211-224）。→ `Session.derive_messages()`（append.py:430 → model_visible_messages → 纯 fold 回退分支）在 projection registry 未挂载时**会对 writer 自己写出的 journal 抛错**；挂载是可选的（唯一挂载点 `projection_registry.py:152`，插件）。读者 `model_context_assembler.py:28`、`history.py:29`、`token_meter.py:42` 都走这条。恢复链例外：`recovery.py:80-107` 的 `append_approval_resolved_if_pending` 绕开已存在的 typed `ApprovalResolved`（events.py:251-253，含 `approved: bool`），用 `getattr(session_writer, "append", None)` 裸调 + **写死 `"approved": True`**（denied 路径走不通）；参数名叫 `session_writer`，但真正的 `RunSessionWriter` 根本没有 `.append(type, dict, visibility=...)` 方法——传进去静默返回 `False`；`tests/architecture/test_session_lifecycle_producers.py:56` 把这个裸写生产者 pin 死了。
- Q5（测试缺口）：两个 `derive_messages` 的分叉无测试锁定（`test_run_session_writer.py` 10 测试只用 `_InMemorySession` 替身测 writer 自身；没有任何测试把 writer 产出的真实 journal 喂给 kernel `foldSurface`）；`NullHookRegistry` 无测试文件；`append_approval_resolved_if_pending` 的 duck-typing 只能传假对象测（绕过 typed interface），而"传真 RunSessionWriter → 静默 False"的陷阱恰恰被测试替身藏起来了；widget guard 的真实 payload 形状漂移无集成测试。

## 候选表

| ID | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|---|---|---|---|---|---|
| RA-162 | `lca/plugins/tools/cordis_control/loader.py`（extract_plugin_factory）、`lca/infrastructure/preset/discovery.py`（_load_plugin_tool） | 同一份插件 `.py` 在同一进程被 importlib exec 两次（模块名 `lca_agent_presets._runtime.{name}` vs `lca_presets._autonomous.{dir}.{name}`，`sys.modules` 里是两个条目——模块级状态在 creator 管线和 discovery 管线里是两份）；且两处"找入口函数"启发式互相不一致（PR12 强制 `plugin_meta` vs 8 选 1 宽松），"我的插件怎么写才会被找到"没有单一答案 | 统一 exec 模块命名并复用 `sys.modules` 已加载模块（单 exec）；把入口发现收敛为一个共享函数（放在 loader.py 或 preset 包），两处调用；两处的"严格度"差异收进显式参数（creator 线 require_meta=True，discovery 线 False） | "插件怎么被加载/怎么被发现"的知识从两套拷贝收进一个 adapter；leverage：以后入口约定只改一处；消除真实的模块级状态分叉风险（单例/缓存双份） | Strong |
| RA-163 | `lca/runtime/session/run_session_writer.py`（append_* 词表）、`lca_kernel/events/fold/inputs.py`（词表 SSOT） | writer 的 append_* 用斜杠词表（`"surface/user_message"`），kernel fold 的 surface 合格类型是 spine category 闭集；`Session.derive_messages()` 的纯 fold 回退分支会对 writer 自己写出的 journal 抛 `ValueError`（`_surface_op_of` inputs.py:218-222）——projection registry 挂载是可选的，这条是真实的 fail-loud 分叉，不是风格问题 | writer 的 append_* 改用 spine category 词表（或在 `Session.append` 入口做一次归一映射），让写侧与两个读侧消费同一词表；实现前先在测试里复现 `ValueError` | 词表 SSOT 第一次真正单一；leverage：以后任何新 surface 事件只认一个词表，纯 fold 回退不再对自己人抛错 | Strong |
| RA-164 | `lca/infrastructure/runtime_plane/access/approval_engine.py:161-172` | `ApprovalPolicyRegistry`（`register`/`list_strategies`）只是 sorted list 包装，`git grep` 确认生产零调用者（只有定义 + 自身单测）——"one adapter = hypothetical seam" 的反面：zero。留着就是"以为有人用"的扩展点诱惑 | 删除类及其单测 | deletion test 纯删零转移；代码库少一个没人用的可插拔点 | Strong |
| RA-165 | `lca/infrastructure/tools/dynamic/bridge.py:65-78`（DynamicPluginToolAdapter.execute） | JSON 归一化对**所有**字符串参数做启发式 `startswith("[")/("{")` → `json.loads`，不看 `parameters` schema——合法字符串（如一段代码文本 `"[1, 2, 3]"`）会被静默改写成 list，且调用者从 interface 上看不出"我的字符串可能被 json.loads"。这是 LLM 参数容错的全局启发式藏在通用 adapter 层 | 只对 `parameters` schema 声明为 array/object 的字段做字符串还原（或加显式开关）；改写时打 debug 日志 | "LLM 参数容错"从不可见的全局启发式变成 schema 感知的局部行为；消除一类静默数据损坏，修 bug 的人不用再查插件函数本身之外的暗处 | Worth exploring |
| RA-166 | `lca/runtime/session/run_session_writer.py:394`（derive_messages）vs `lca/plugins/session/runtime/messages/messages.py:76`（derive_messages） | 同名 `derive_messages` 两个实现，三处语义分叉（orphan-drop、assistant tool_calls 保留与否、空结果占位文本）——"two = real" 的 seam fracture。"写下去的东西谁在读"取决于调用方随手选了哪个同名函数，这是长期误读源 | 选一边为 SSOT（建议 kernel fold 纯函数 + projection 增量），另一边删掉或降级为明确标注的兼容垫片；实现前先裁定每个分叉点的正确语义（以 ADR-0201 和现有 scenario 测试为据） | derive 语义第一次有单一真值；leverage：以后任何"消息怎么算出来"的问题只查一处 | Worth exploring |
| RA-167 | `lca/infrastructure/runtime_plane/access/approval_engine.py:288-300`（NamespaceApprovalStrategy） | `namespace_of_tool` 只试 raw 拼写，而同一 seam 的另一个消费者 `tool_wire_gate.py:146-147` 试 resolved + alternate 双拼写——同一 seam、两种 miss-handling，这正是 `8c1624fc7` 的 bug 形状；用户的 +4 行修复（`_STANDARD_SHELL_TOOLS`）是盖在 wiring 上的创可贴，是与 defer catalog 手工同步的静态影子集合，无测试锁定其同步 | 对齐 wire gate 策略（试 resolved + alternate），删除 `_STANDARD_SHELL_TOOLS` backstop；拼写归一的调用策略在 approval 侧显式化 | 把拼写政策收进一致的调用策略，消灭"新 shell 工具别名默默 bypass 审批"的复发面；`8c1624fc7` 从创可贴变成缝合 | Worth exploring |

**记录但不开 story**：
- ① Area A 的 `CreatorRuntime` 私有属性穿透（`_composer`/`_actor_role`/`_preset_root`/`_caller_grant`/`_assistant_home`/`_tools_service`/`_safe_executor` 九个 privates）：Worth exploring 级，但纯重构、改动面涉及动态子类工厂 + solo 过滤（`solo.py` 读 `_assistant_home`），比本轮 6 个更软；已记录在本评估，下一轮热点若仍在 creator 线再开。
- ② Area C 的 `append_approval_resolved_if_pending` 绕 typed `ApprovalResolved`（recovery.py:80-107）：Worth exploring 级，但 `approved=False`/denied 路径的调用方在禁区 `plugins/transport/webserver/` 内，改前需确认调用方是否依赖当前"静默 False"行为；禁区内语义未验证，本轮不开。
- ③ Area B 的 `visible` 手工解析（approval_engine.py:266-271）→ 改用 session seam `turn_visible_tool_names()`：seam 在禁区模块内，同语义断言建立在"调用方用法反推"上（子任务已声明证据缺口），且实现需进禁区验证；本轮不开。
- ④ Area C 的 `NullHookRegistry`、`_drop_reasoning_after_dropped_calls` no-op、`orphan_dropped_count` 仪表、`recovery_from_events` 一行业名：deletion 级 micro 发现，无架构摩擦深度，留给 hygiene 性机会或下一轮。

## 自我诘问（per-candidate grilling）

### RA-162
- **Constraints**：ADR-0256 的 tool namespace fail-fast（`tests/contracts/test_tool_namespace_adr0256_conformance.py`）是 plugin 注册的硬约束，动加载管线不能动注册语义；PR12 的 `plugin_meta` 强制是 creator 线的既有契约（`PluginMetaMissing`），收敛时 creator 线保持 `require_meta=True`，不能为求统一而放松；动态子类的 `_assistant_home` 等私有字段（`build_cordis_control_tool`）是另一组耦合，本 story 不动。
- **Dependencies**：调用方：`creator_runtime.author` → `loader.load_plugin_source`/`extract_plugin_factory`；`discovery.discover_presets` → `_load_plugin_tool`；`creator_promotion.promote` → `DynamicToolBridge.bridge_instance`。共享函数放在 loader.py（或 preset 包）后，discovery 导入它——discovery 与 loader 当前是 sibling 关系，无循环（loader 不 import discovery）。
- **Shape of the deepened module**：`extract_entry(module, *, require_meta: bool) -> (factory, meta)` 一个函数；`exec_plugin_source(path, module_name=统一前缀) ` 保证同 path 只 exec 一次（`sys.modules` 命中则复用）。creator 线 require_meta=True（保持 PR12），discovery 线 require_meta=False（保持 8 选 1 宽松——严格度差异是产品语义，不是 bug）。
- **Test survival**：`tests/scenario/cordis/test_cordis_creator_assistant_closed_loop.py`（含直接调 `_load_plugin_tool` 私有的那处，story 实现后可改走新公共函数——这是 story 的顺带收益）、`test_dynamic_tool_bridge.py`、`test_tool_namespace_adr0256_conformance.py`。新增：同 path 两次加载 → 同一模块对象（`sys.modules` 单条目）；creator 线缺 meta 仍抛 `PluginMetaMissing`。
- **Deletion test verdict**：删掉任一处拷贝 → 入口约定知识**集中**到共享函数；删掉双 exec → 模块级状态分叉消失。concentrates。

### RA-163
- **Constraints**：kernel fold 的 `_surface_op_of` fail-loud 语义是 dsh 对位设计（`inputs.py` 注释），不能改 kernel 去"容忍"斜杠词表——修的是 writer 侧，不是 fold 侧；`append_tool_result` 已用 spine 常量，改动只涉 `append_user_message`/`append_assistant_message`（及可能的 seed prior turns）。
- **Dependencies**：writer 的 append_* 调用方全仓 grep（agent core、memory fold 等）；两个读侧（writer 派生 + plugins messages）都要重新验证；`Session.append` 原型不变（只改传入的 type 字符串或其映射表）。
- **Shape of the deepened module**：最小改法是 writer 内加 `SURFACE_*` 常量映射到 `lca_kernel/events/fold/inputs.py` 的 `SURFACE_*_TYPE`（如 `SURFACE_USER_TYPE` 若存在，否则用对应 spine category）；或 `Session.append` 入口加一次 `type` 归一（需确认 append 的其他调用方无斜杠类型依赖——实现时 grep）。
- **Test survival**：`tests/unit/runtime/session/test_run_session_writer.py`（10 测试，用 `_InMemorySession` 替身）——词表改动后断言的事件 type 字符串要同步；新增测试：writer 产出 journal → kernel `foldSurface` 纯函数路径不抛 `ValueError`（本轮评估确认缺失的关键测试）。
- **Deletion test verdict**：删掉斜杠词表 → "surface 事件长什么样"的知识**集中**到 kernel inputs 的闭集。concentrates。

### RA-164
- **Constraints**：零行为变化（生产零调用者）；`build_default_approval_engine` 不用 registry（已确认：`approval_engine.py:314-324` 是硬编码链）。
- **Dependencies**：仅 `tests/infrastructure/runtime_plane/access/test_approval_engine.py:114` 的单测。
- **Shape of the deepened module**：删类 + 删 import + 删单测。三行式。
- **Test survival**：删掉的单测是 registry 自身的；其余引擎测试（chain 顺序、策略 verdict）不受影响。
- **Deletion test verdict**：删掉 → 复杂度消失，不转移。passes trivially。

### RA-165
- **Constraints**：`test_dynamic_tool_adapter_json_string_argument_unpacking` 钉的是 happy path（LLM 传 JSON 字符串给 object 参数的容错），不能破坏；现有插件可能已**依赖**宽松还原（改前先 grep 全仓插件的 parameters 声明，看有没有 string 字段实际收 JSON 文本）。
- **Dependencies**：`DynamicPluginToolAdapter.execute` 是所有动态桥接工具的执行入口；改动影响全部动态插件。
- **Shape of the deepened module**：`execute` 里查 `self.parameters["properties"][k]["type"]`，仅当 type in ("array", "object") 时做字符串还原；其余保持原样；还原成功打 debug 日志（含字段名）。
- **Test survival**：现有 unpacking 测试保持绿；新增：string 字段传 `"[1, 2]"` 不再被改写；object 字段传 JSON 字符串仍还原。
- **Deletion test verdict**：删掉启发式 → 容错知识从"全局暗改"**集中**到"schema 声明的局部行为"。concentrates（部分：显式开关替代方案也算集中）。

### RA-166
- **Constraints**：ADR-0201（tool_result 预计算 `data["message"]`）是 plugins 读侧的设计依据；`assemble.py`、`model_context_assembler`、`token_meter` 等多个读者依赖当前任一语义——实现前必须先裁定每个分叉点的正确语义，不能"选一边"了事。
- **Dependencies**：读者：`lca/nodes/think/history/assemble.py`、`model_context_assembler.py`、`history.py`、`token_meter.py`（走 `Session.derive_messages()`）；写侧 `run_session_writer.py`。
- **Shape of the deepened module**：建议 SSOT = kernel fold 纯函数 + projection 增量（kernel 侧有 dsh 对位、有 fail-loud 校验）；writer 的 `derive_messages` 降级为"明确标注的兼容垫片"（docstring 写清委托 + 差异），或在确认零独有消费者后删除。
- **Test survival**：分叉点逐项 pin 测试先写（orphan-drop、tool_calls、空占位文本），再收敛——按 RA-154 模式，旧塑形若被测试钉住且 story 废除它，测试随契约改。
- **Deletion test verdict**：删掉一边 → derive 语义**集中**到唯一实现。concentrates。

### RA-167
- **Constraints**：`8c1624fc7` 的 `_STANDARD_SHELL_TOOLS` 是用户刚落地的生产修复，不能简单 revert——story 是"缝合"不是"回滚"：新语义必须覆盖旧集合拦住的全部 case（实现时把 `_STANDARD_SHELL_TOOLS` 成员列成测试用例，逐个验证双拼写策略同样 require_approval）。
- **Dependencies**：`NamespaceApprovalStrategy.evaluate` 内部；`tool_wire_gate.py:146-147` 是对照实现（同 seam 的双拼写用法，可直接读，无需进禁区）；`defer_session.namespace_of_tool` 的 alias 语义（exact-match，wire gate 的"试两次"写法是证据）。
- **Shape of the deepened module**：`evaluate` 内对 `namespace_of_tool` 试 `(resolved, alternate)` 双拼写（照抄 wire gate 顺序）；删 `_STANDARD_SHELL_TOOLS` 及 :295-298 backstop 分支。
- **Test survival**：`tests/.../test_namespace_approval_strategy.py`；新增：`_STANDARD_SHELL_TOOLS` 的每个成员在新策略下同样被 require_approval（防回归网）。
- **Deletion test verdict**：删掉影子集合 → 拼写政策**集中**到与 wire gate 一致的调用策略。concentrates。

## Top recommendation

先做 **RA-163**：这是本轮唯一的**真实 fail-loud 分叉**——writer 自己写出的 journal 能在 projection registry 未挂载时把 `Session.derive_messages()` 炸成 `ValueError`，且证据链完整（writer L211-224 的写出形态 + inputs.py:218-222 的 raise + append.py:430 的调用链 + registry 挂载可选性已验证）。修完它，Area C 的其他收敛（RA-166）才有资格谈"一致"。接着 **RA-162**：creator/dynamic 管线是用户刚落地的新功能，`sys.modules` 双条目是真实的状态分叉风险，越早收敛越便宜。然后 **RA-164**（三行删除，零风险热身）、**RA-167**（把用户的创可贴缝合成真正的拼写政策）、**RA-165**、**RA-166**（需先裁定语义，最重，放最后）。

## Diversity quota

- 摩擦漫步来源：RA-162/RA-165（Area A creator bridge 精读：双 exec + 入口启发式分叉 / schema-unaware JSON 启发式）、RA-163/RA-166（Area C run session 写/读链精读：词表 fail-loud 分叉 / 同名 derive 双实现）、RA-164/RA-167（Area B 审批链精读：zero-caller registry / 拼写政策 wiring 分叉）。✓ 全部来自摩擦漫步，无 duplication 类。
- 证据缺口已声明：Area B 的 `turn_visible_tool_names` 收敛（禁区内语义未验证）、`canonical_tool_name` 双胞胎等价性——均未开 story。

## 运行时验证记录

- 脚本：`hidden_files/raphy-runtime-verify-20261020.py`（由 2026-10-14 版仅改头部日期），252 后台跑，`LLM_API_KEY=dummy`，落盘 `~/.lca-worktrees/zz-verify-20261020.log`。
- 结果：A 基础 run COMPLETED / B 工具调用 COMPLETED / C 双轮 run COMPLETED / D 不收敛 run → status=failed 无异常（RA-023 回归守住），`DONE failures=0`。
- 结论：无 crash/hang/silent-failure，无新增 P0/P1。10-07 发现的 P2（`run(None)` 晦涩报错、`arguments` 传 str 晦涩）未复测——属体验类，非架构摩擦，本轮不立 story。
- 小插曲：首次启动时 `env LLM_API_KEY=<redacted>` 里的尖括号被 bash 当重定向解析导致启动失败（"bash: redacted: No such file or directory"），第二次用 `LLM_API_KEY=dummy` 正常启动。教训已记入本轮 progress（见下）。

---

Assessment complete: 6 stories written, top is RA-163.
