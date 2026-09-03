# Agent Note: lca/plugins/ 单入口宇宙 —— 全部插件走同一声明与同一装配通道

Status: proposed

## Problem

`lca/plugins/` 下当前共存四条装配通道,各自决定"什么东西以什么形态进入运行系统",`@plugin` 只是其中之一:

1. `@plugin` + `bundles/*.yaml` 的 `$module` 入口 —— `lca/harness/profile/resolve.py:119-196` 导入、校验 `id` 与 `$module` 一致、按 `provides→requires` DAG 启动。覆盖 ~230 插件。
2. `lca_kernel/events/config/**/*.yaml` 的类路径白名单(`publishers:` / `consumer_rules:`)—— `lca_kernel/events/registry.py:50-145` 解析为类对象,`lca_kernel/events/bus.py:200-256` 在 `publish`/`subscribe` 时按白名单鉴权。覆盖 17 个 `lca/plugins/events/**` 组件。
3. `profiles/event-pipeline/*.yaml` 的 hooks/sinks/consumer_rules 段 —— `lca/harness/profile/pipeline_loader.py` 按 `module.ClassName` 字符串实例化(`pipeline.py:171-189`)。覆盖 Pipeline 自定义逻辑。
4. 组合根直接 `import` —— `lca/application/spawn.py:21-26` 导入 `lca.plugins.composer.*`;webserver `loop_drivers.py:17-21` 导入 `modes_catalog` / `FileRoleLibrary` / `LLMTeamCaster`;`lca_kernel/observability.py:67-208` 直接组装五缝实现;`lca/plugins/events/publishers/spine_reflector_*/plugin.py` 15 个标记类被 `lca/cognition/*`、`lca/runtime/*`、`lca/agent/*` 反向静态 import。

通道②③④绕开 `scripts/check_plugin_shape.py` 与 `check_plugin_metadata.py`,因此"`lca/plugins/` 实际有 ~230 插件"与"门禁视野内 ~230 插件"等同;但"`lca/plugins/events/` 下没有 `@plugin`"、`spine_file_sink` 绕过 yaml 白名单却自订阅全部 `spine.*`、`SpineChainSink` 与 `SpineStepTreeAccumulator` 在 yaml 中授权但生产零 `subscribe`、`JournalSink` 装载即抛(`spine.yaml` 授权 1/101) 等漂移均发生在门禁盲区。

形态侧:`lca/plugins/` 484 个 .py 文件里 ~141 个是非 `__init__` 非插件文件;目录同时承担"kind 维度"(`seams/` 54、`providers/` 50)与"领域维度"(~30 个目录)两条互不相交的轴,产生 12 处 `kind` 与目录矛盾(id 为 PROVIDER 但住在 `seams/`、id 为 PRIMITIVE 但住在 `providers/`);id 文法 4 种并存(`lca-` 连字符 148、点分 76、`lca.` 点分 5、裸下划线 1),`lca-` 后缀 7 种无规则变体(`-seam` / `-service` / `-provider` / `-factory` / `-contributor` / `-default` / `-builtin`);`tools/cordis_control/__init__.py:78` 在 `__init__.py` 里写 `@plugin`、`events/publishers/delegation_cache/` 保留 `manifest.py + plugin.py` 双形态,均违反 AGENTS.md §5 范式;`lca/plugins/__init__.py` 文档串仍描述旧的 "manifest + apply()" 模型,`legacy_blacklist.txt` 注释数字 194 与现实 230 偏离。

插件位置逃逸:`lca/runtime/reducer.py:458`、`lca/cognition/team/modes/*` ×4、`lca/application/session_live_builder_provider.py:18`、`lca_kernel/events/manifest.py:33`(最后一个是 kernel 元插件,位置合法) 共 7 个 `@plugin` 不在 `lca/plugins/` 下;`lca/agent/orchestration_strategies/` 7 个策略类生产零引用;6 个 scenario bundle(`scenario-ralph` / `scenario-memgpt` / `scenario-lats` / `scenario-research-debate` / `researcher-code-tools` / `researcher-doc-tools` / `researcher-web-tools`) 引用的 `$module` 路径不存在;4 个 `@plugin`(`plugins/think/null_critic.py`、`null_synthesizer.py`、`composer/composition/sub_composers.py`、`bundles/coding_agent_tools.py`)无任何出厂 bundle 引用。

## Proposal

按 5 原则收敛到"一个插件宇宙",以 **11 个独立 PR** 实施,每 PR 独立验证、可独立合并、可独立回滚。

### 原则

1. **`@plugin` 是唯一声明形态**。所有装配点(bundle entry、事件 yaml `publishers:` / `consumer_rules:`、Pipeline yaml `hooks:` / `sinks:`)只引用**插件 id**,禁止裸类路径。事件治理数据(哪个 category 授权给谁、失败语义、前缀规则) 留在 yaml —— 那是治理数据不是代码;实体引用必须经 id,由 registry 在装载期解析 id → manifest 并与 yaml 互校验。
2. **目录按领域组织,kind 进 manifest**。放弃现行 AGENTS.md §5 "目录名 = kind" 规则(已被现实证伪:`seams/` + `providers/` 两棵树制造 12 处 kind 矛盾,且把一对 seam/provider 拆到两处)。`lca/plugins/<domain>/<name>.py` 一个文件,内含唯一 `@plugin`;`<domain>` 对齐认知闭集与功能群(perceive / think / act / memory / collaboration / transport / observability / phase_graph / control / learning / creator / tools / runtime / events/{publishers,sinks,subscribers})。kind、layer、effects、functional_group 全部由 manifest 声明,目录只承担人类导航。
3. **文件构成硬约束**。`__init__.py` 永远不许出现 `@plugin`;一个插件 = 一个含 `@plugin` 的 .py 文件,或一个包内**只有一个文件**含该 id 的 `@plugin`(包形态仅在实现太大时使用);每个插件必须被至少一个出厂 bundle 引用(否则报"孤儿插件");每个 bundle `$module` 必须存在且与文件内 `@plugin(id=)` 一致(否则报"死引用");事件 yaml 与 Pipeline yaml 内裸类路径在迁移完成后物理禁止(架构测试 rg 守护)。`scripts/check_plugin_shape.py` 现有三维(`missing_effects` / `dual_form_residue` / `duplicate_id`) 扩展为 8 维,基线快照进 `docs/notes/baselines/plugin-shape.json`。
4. **组合根退出 plugins/**。`lca/plugins/composer/`(34 文件,仅 6 个是插件)整体迁至 `lca/application/composer/`(组合根),`spawn.py` import 路径同步更新;`lca/plugins/factories/` 保留(本身是插件化的组合);`lca/plugins/bundles/coding_agent_tools.py`(零引用) 改写为 `bundles/coding_agent_tools.yaml` 或删除。
5. **id 文法收敛**。新插件强制点分 `<domain>.<name>`(可选 `.seam` / `.provider` 角色后缀);存量 `lca-` id 登记迁移表逐步改名,优先级最低(表面问题非机制问题)。

### PR 拆分

下表每行 = 一 PR。所有 PR 独立可合并、独立可回滚、独立验证。**软依赖** 列标记"实施时建议的顺序",但不构成合并前置条件。

| # | 标题 | 软依赖 | 改动 | 验证 / 验收 | 独立性 / delete-when |
|---|---|---|---|---|---|
| PR-1 | `check_plugin_shape` 扩到 8 维 + 基线快照 | 无 | `scripts/check_plugin_shape.py` 新增 5 维:① `@plugin` 位置(只允许 `lca/plugins/` 与 `lca_kernel/events/manifest.py`)、② 孤儿插件(无 bundle `$module` 引用)、③ 死 bundle 引用(`$module` 不可 import 或 `id` 与 manifest 不一致)、④ `@plugin` in `__init__.py`、⑤ 同 id 多入口文件;`docs/notes/baselines/plugin-shape.json` 字段扩展并重写基线;`lca-ops audit-plugin-shape` 帮助文本更新 | `uv run python scripts/check_plugin_shape.py` exit 0,基线 JSON 包含新字段;`scripts/check_plugin_shape.py` 单测覆盖 5 个新维度 fixture;既有测试 `tests/plugins/**` 不被新门禁触发 | 与任何运行时无关,纯加法;`rg "lca\.plugins\..*\.[A-Z]" lca_kernel/events/config profiles/event-pipeline` 在 PR-5 之前不强制 0 |
| PR-2 | `plugins/` 文档串与现状对齐 | 无 | `lca/plugins/__init__.py` 文档串改写为"每个子目录由 @plugin 声明 + 私有辅助 + 组合根组成(组合根外迁后剩余声明 + 私有辅助)";`README.md` 模块清单删除(改用"插件声明见 `lca-ops inspect-tree <profile>`,helper 模块按目录物理列示");`legacy_blacklist.txt` 数字 `194` → `230` | `uv run lca-ops notes-slop docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md` + plugin-shape gate 不报旧字串;README 中不再有具体文件路径清单 | 仅文档,不涉及代码 |
| PR-3 | C 组死代码与死引用清理 | 无 | (a) `lca/agent/orchestration_strategies/` 整个子目录删除(生产零引用);(b) 4 个无 bundle 引用 `@plugin` 中 `null_critic` / `null_synthesizer` 保留但加入 `bundles/web-app.yaml` 或 `legacy_blacklist.txt`,`sub_composers.py` 删除(被 4 个 per-composer provider 取代),`bundles/coding_agent_tools.py` 改写为 `bundles/coding_agent_tools.yaml` 形式或删除;(c) 6 个 scenario bundle(`scenario-ralph` / `scenario-memgpt` / `scenario-lats` / `scenario-research-debate` / `researcher-code-tools` / `researcher-doc-tools` / `researcher-web-tools`)的 dead `$module` 条目整段删除,bundle 文件删除(无其他 profile 引用) | `uv run pytest tests/plugins tests/harness tests/architecture tests/integration -q` 全过;内联 `python -c` 循环 import 所有出厂 bundle 的 `$module` exit 0;`rg "lca.plugins.policy.goal_stack\|lca.plugins.tools.str_replace_editor\|lca.plugins.tools.git\|lca.plugins.brain.lats\|lca.plugins.synthesizer.evidence_weighted\|lca.plugins.observability.spine.reflectors.signature"` = 0 | 纯删除;每条删除有删-when:`orchestration_strategies` 删-when `rg "lca.agent.orchestration_strategies" lca/ = 0`(已满足);scenario bundle 删-when 同上 |
| PR-4 | 事件组件补 `@plugin` + bundle 装配 | PR-5 之前完成 | `lca/plugins/events/publishers/spine_reflector_*/plugin.py`、`spine_loop_cursor/`、`spine_writable_matrix/`、`spine_chain_sink/sink.py`、`subscribers/spine_step_tree_accumulator/subscriber.py` 共 17 个组件,在文件顶部加 `@plugin(id="events.<name>", provides=["event.bus.<name>"], requires=["event.bus"], layer=..., kind=PRIMITIVE, effects=..., event_publishes/event_subscribes=[...])`;`delegation_cache/manifest.py` 与 `plugin.py` 合并为单文件 `@plugin`(消除 AGENTS.md §5 禁止的双形态);新增 `bundles/event-bus-components.yaml` 列出全部事件插件,`profiles/web-standard.yaml` 与 `profiles/event-pipeline/web-standard.yaml` 装配此 bundle | `uv run python scripts/check_plugin_shape.py` 229 → 246+ 全 0;`uv run python scripts/check_plugin_metadata.py` 扫描数同步上升;`uv run pytest tests/lca_kernel/events tests/plugins/events tests/architecture/test_event_bus_invariants.py tests/integration/test_e2e_journal_wiring.py -q` 全过;`lca-ops inspect-tree web-standard` 事件插件全部可见;端到端 run (`lca-ops runs create --user-text "ping"`) 产生的 `<run_id>.spine.jsonl` 事件计数与迁移前一致 | yaml 仍走类路径白名单,manifest 声明为加法,不破坏运行;`delegation_cache` 双形态消除是该 PR 内的微清理;merge 后 yaml 的合法性可由 PR-5 替换 |
| PR-5 | 事件 yaml + Pipeline yaml 改为 id 引用(双轨兼容) | 软顺序 PR-4 之前可合并(对 4 个现有 manifest 的 id 引用已经有效) | `lca_kernel/events/registry.py` 扩展 `EventRegistry.load` 的解析: `publishers:` / `subscribers:` 接受 `events.<id>` 或 `lca.plugins...ClassName` 两种形态,前者按 id 解析(`manifest = registry.by_id(id)`),后者兼容现有形态(标记 deprecation 日志);`lca_kernel/events/registry.py:140-145` 的 `can_consume` 同步支持 id 与类对象双键;`lca/harness/profile/pipeline_loader.py` 对 `hooks:` / `sinks:` 段新增 `plugin:` 字段(与现有 `hook:` / `backend:` 类路径字段并存);逐步把 `spine.yaml` 与 `team.yaml` 的 `publishers:` / `subscribers:` 改写为 id 形式(按文件子集,每 PR 内迁移一段,直至全 0) | 新增 `scripts/verify_yaml_id_authority.py`:在双轨并存状态下读新旧 yaml,断言任一 category 的授权集合与迁移目标(id-only)完全相等;`uv run lca-ops runs create --user-text "ping"` 端到端仍过且事件计数不变;`rg "lca\.plugins\..*\.[A-Z][A-Za-z]+$" lca_kernel/events/config profiles/event-pipeline` 在 PR-5 完成全部迁移后 = 0(分批 `delete-when`) | 完全独立;`delete-when` = 双轨兼容分支所有调用方迁完(rg 全 0 后删 `EventRegistry.load` 的类路径兼容分支);新增的 `plugin:` 字段保留作为唯一引用形态 |
| PR-6 | 事件鉴权与订阅三方一致性 | PR-4 / PR-5 之一之后 | (a) `spine_file_sink` 在 yaml `consumer_rules` 增列(取消绕过白名单的自订阅);(b) `JournalSink`(101/1 授权,装载即抛) 整目录删除;(c) `SpineChainSink` 与 `SpineStepTreeAccumulator` 任一:`rg "\.subscribe(" lca/ lca_kernel/ tests/ = 0` 则整组件 + yaml 授权同步删除(决断写进 PR body);(d) 新增架构测试 `tests/architecture/test_event_bus_authority_consistency.py` 三方一致:"yaml 授权 ⟺ manifest `event_subscribes` 声明 ⟺ 生产 `subscribe()` 调用" | 架构测试三向一致性 100%;`uv run pytest tests/lca_kernel/events tests/plugins/events tests/integration/test_event_bus_e2e.py -q` 全过;`scripts/check_plugin_shape.py` 不报 dead reference | 完全独立(只动 events surface);(b) 与 (c) 是纯删除,delete-when 即"已删除并通过架构测试";(a) 加法 |
| PR-7 | 观测五缝插件化 + profile `observability:` 段改 bundle | 无 | (a) `lca_kernel/observability.py:67-208` 的 `LoopCursorFactory` / `StdProjectionHost` / `StdModelVisibleCapture` / `StdCloseBarrier` / `NullPersistenceCoordinator` 五个硬编码实现迁出至 `lca/plugins/observability/seams/`(seam) + `lca/plugins/observability/providers/(null|std)_<name>.py`(provider),新增 seam+provider plugin 对;(b) `profiles/web-standard.yaml:13-28` 的 `observability:` 段删除,改为 `bundles/observability-default.yaml` 装配五缝;(c) `LoopCursorFactory.from_profile` / `ObservabilityRuntime.from_profile` 改为接受 resolved plan 而非 `raw profile dict`,从 capability 注入各 seam | `uv run lca-ops inspect-tree web-standard` 新增 5 个 capability;`uv run lca-ops runs create --user-text "ping"` 端到端通过且 spine 事件链一致;新增 `tests/plugins/observability/test_seam_replacement.py`:在 profile 中替换一个 provider 为 stub,断言运行仍可启动且仅该 provider 行为变化;`rg "from lca.infrastructure.observability.loop_cursor" lca/ = 0`(组件迁完) | 完全独立;(c) 重构后保留 `from_profile` 旧签名作为 1 行 wrapper,delete-when `rg "ObservabilityRuntime.from_profile" lca/lca_kernel/ = 0` |
| PR-8 | 组合根迁出 + 装饰器/传输插件化 | 无 | (a) `lca/plugins/composer/` 整体迁至 `lca/application/composer/`(`spawn.py:21-26` 的 5 条 import 同步);(b) `lca/plugins/composer/think/brain.py:18-45` 的 `instrument_llm` 强制 `TelemetryLLMAdapter`/`ModelVisibleLLMAdapter` 拆出为 `lca/plugins/providers/think/decorators/{telemetry,model_visible}.py`,默认在 `bundles/web-app.yaml` 启用,profile 可关闭;(c) `lca/plugins/composer/collaboration/team_transport.py:10-22` 的 `InternalTransport`/`A2ATransport`/`MCPTransport` 改注册制,各自成为 `@plugin`(seam+provider),由 `bundles/web-app.yaml` 选择装配;(d) `lca/plugins/composer/act/perceive.py:17-39` 强制包 `TelemetryMemoryAdapter` 同步改为 (b) 形态;(e) `apply_lead_brain` 的 `isinstance(brain, ModularBrain)` 改走 capability protocol check | `uv run pytest tests/ tests/integration -q` 全过;`uv run lca-ops runs create --user-text "ping"` 端到端通过且 telemetry 事件计数一致(迁移前后一致);新增 `tests/plugins/think/test_decorator_disable.py`:profile 关闭 `telemetry_decorator` 后 `TelemetryLLMAdapter` 不被 wrap;`rg "from lca.plugins.composer" lca/application` 仅命中 `lca.application.composer`(已迁完) | 独立;(a) 是纯移动 + import 更新,(b)(c)(d) 是组件替换,(e) 是单行替换;`delete-when`:`lca/application/composer/` 与 `lca/plugins/composer/` 同时存在 ≤ 1 个 PR,合并后旧路径删除 |
| PR-9 | 7 个位置逃逸的 `@plugin` 归位 | 无 | (a) `lca/runtime/reducer.py:458` 的 `@plugin` + `setup` 移至 `lca/plugins/runtime/reducer.py`,`bundles/base.yaml:497 $module` 改为 `lca.plugins.runtime.reducer`,`lca_kernel/boot.py` 与 `composer/runtime/fixture_runtime_adapter.py:44` 的硬编码 import 改 capability 注入;(b) `lca/cognition/team/modes/{solo_mode,team_mode,cognitive_loop,cordis_creator_mode}.py` 共 4 个 `@plugin` 移至 `lca/plugins/collaboration/modes/`(domain 维度),`$module` 字符串更新;(c) `lca/application/session_live_builder_provider.py:18` 移至 `lca/plugins/runtime/session_live_builder.py`;(d) `lca_kernel/events/manifest.py` 保留(kernel 元插件,合法位置) | PR-1 的位置门禁 0 违例;`uv run pytest tests/runtime tests/agent tests/integration -q` 全过;`uv run lca-ops inspect-tree web-standard` capability 数与迁移前一致 | 纯移动 + `$module` 字符串更新;delete-when:`rg "from lca.cognition.team.modes import\|from lca.application.session_live_builder" lca/ = 0`(迁移完) |
| PR-10 | seams/providers 104 插件按领域归位(脚本化批改) | 无 | 脚本迁移: `seams/<area>/<name>.py` → `<area>/<name>_seam.py`(domain 维度:perceive/think/act/memory/collaboration/transport/observability/...),`providers/<area>/<name>.py` → `<area>/<name>_provider.py`;所有 `bundles/*.yaml` 的 `$module` 字符串批量更新;新增 `tests/harness/test_seam_provider_locality.py`:对每个迁移对(seam + provider) 断言二者 ID namespace 一致且在同 domain 目录下 | `uv run pytest tests/ tests/integration -q` 全过;`uv run lca-ops inspect-tree web-standard` capability 集合与迁移前等价(等价脚本 `scripts/verify_migration_capability_equivalence.py` exit 0);PR-1 的 kind-directory 一致性维度 0 违例 | 脚本化批改;一次性提交,工作量集中;delete-when:`seams/` 与 `providers/` 目录为空(迁完后目录删除) |
| PR-11 | id 文法收敛(滚动,不进 1 PR) | PR-10 之后 | `scripts/check_plugin_metadata.py` 新增维度"新插件 id 必须是 `<domain>.<name>` 形式,角色后缀可选 `.seam` / `.provider`";存量 `lca-` id 进入 `docs/notes/baselines/plugin-id-grammar.json`,按文档块逐批改名(每批一个独立 PR,改 `lca/plugins/...`、`bundles/*.yaml` 对应 `$module` 与测试夹具);本文档不强制 1 PR 完成所有存量改名 | 门禁对新插件 0 违例;存量改名每批一个 PR,每批完成时 `grep "lca-" docs/notes/baselines/plugin-id-grammar.json` 计数下降 | 滚动,非一次性;delete-when:`baselines/plugin-id-grammar.json` 计数归 0(全部改完) |

### 实施顺序(软建议)

```
PR-1 ─┬─→ PR-2 ─┬─→ PR-3
       │
       ├─→ PR-4 ─→ PR-5 ─→ PR-6
       │
       ├─→ PR-7
       │
       ├─→ PR-8
       │
       ├─→ PR-9
       │
       └─→ PR-10 ─→ PR-11
```

- PR-1 必须最先(否则后续 PR 没有守护);PR-2、PR-3 互相独立,可在 PR-1 后任意位置合;PR-4 → PR-5 → PR-6 形成事件子闭环;PR-7、PR-8、PR-9 互相独立;PR-10 在 PR-1 之后可任意时点合并;PR-11 滚动收尾。
- 软依赖不为合并阻塞条件:每 PR 单独验证 + 单独回滚成立。

## Alternatives considered

### Why not 沿用 deepseek-harness 的"一插件一 npm 包"?

事实是 deepseek-harness 的每个插件是独立 npm 包(`packages/*/<plugin>/` + `package.json` + `src/index.ts` + `tests/*.spec.ts` + `tsconfig.json` + 三语 README),bundle 以 `cordis.patch.yml` row + npm 包名引用,由 pnpm 工作区管理依赖闭包。这解决**独立发布 + 依赖闭包**两个问题。LCA 是单仓单部署,发布需求为零,依赖闭包由 uv 锁文件统一管理;包形态只会增加每个插件的 package.json/tsconfig/lib/node_modules 簿记成本,与你感受到的臃肿一致。值得借鉴的是 dsh 的两条:**① 激活是纯行驱动**(bundle row 是唯一激活真值,LCA 等价物是 bundle `$module` 引用 + 门禁守护,已在 PR-1 落),**② 单一入口约定由工具强制**(LCA 已通过 `@plugin` 装饰器做到,需要在 PR-1/PR-2 把它写进门禁而不是写在文档)。

### Why not 目录按"kind × domain"二维编排?

事实是新增一个维度需要双文件结构(`<domain>/seams/<name>.py` + `<domain>/providers/<name>.py`),路径加倍且不解决 seam-provider 必须配对这一**真正的耦合约束**(seam 没 provider 是空壳,provider 没 seam 是孤注册),还会让现有 AGENTS.md §5 的范式从"一种错误"变成"两种错误"。改为"domain 为目录主轴、kind 在 manifest 声明、配对通过 id 命名约定 `<name>_seam` / `<name>_provider` 在同 domain 共置" 是降维:让一对 seam+provider 物理上聚拢,理解一个能力只需扫一个目录(成本 ↓),kind 维度由 manifest 与门禁保证(治理不丢)。

### Why not 把所有改动压成 1 个大 PR?

事实是 5 原则 + 11 任务 + 跨 7 层(contracts / infrastructure / cognition / runtime / agent / application / lca_kernel)+ ≥ 60 文件改动,**单 PR 不可审、不可回滚、不可分批集成测试**(改动前后等价性无法在 CI 上证明)。AGENTS.md §1 "契约改动必须同 PR 改实现 + 测试"是同质约束;§"卫生清单"的"无新增无期限 TODO"在 PR 切分下更容易维持;每 PR 自带 delete-when 与验证脚本,事故定位成本最低。压成大 PR 等于放弃工程的渐进性,把风险攒到一笔投资,违反本仓库一贯的 12-PR / 5-PR / 4-PR 切分风格(ADR-0183、ADR-0178、本目录的观察收口 note 都是 4-12 PR 切分)。

### Why not 只做门禁与文档不动代码?

事实是门禁不修复"`@plugin` 不在 `lca/plugins/`"、"事件组件无 manifest"、"组合根在 plugins 树里"这些事实漂移,只记录它们。`lca-ops audit-plugin-shape` 的报告读得再多也只是体检报告。PR-1 让违规可见但不消除违规;PR-2 修文档;PR-3 删死代码;之后 PR-4 到 PR-11 逐项消除真实漂移。**纯门禁是看医生不做手术**。

## Acceptance criteria

- `uv run python scripts/check_plugin_shape.py` 报告 8 维全 0;`docs/notes/baselines/plugin-shape.json` 同步更新。
- `uv run python scripts/check_plugin_metadata.py` critical 数从 10 降到 0(PR-2、PR-3 顺手清理);warning 数随 contract= 覆盖推进单调下降。
- `rg "from lca.plugins.composer" lca/` 仅命中 `lca.application.composer`(已迁完);`rg "lca\.plugins\..*\.[A-Z]" lca_kernel/events/config profiles/event-pipeline` = 0(全 id 引用)。
- `rg "lca.plugins.policy.goal_stack\|lca.plugins.brain.lats\|lca.plugins.tools.str_replace_editor\|lca.plugins.tools.git\|lca.plugins.synthesizer.evidence_weighted\|lca.plugins.observability.spine.reflectors.signature"` = 0(死引用清完)。
- `uv run lca-ops inspect-tree profiles/web-standard.yaml` capability 集合与本文档落地前等价(`scripts/verify_migration_capability_equivalence.py` exit 0)。
- `uv run lca-ops runs create --user-text "ping"` 端到端跑通,`<run_id>.spine.jsonl` 事件计数与 PR-1 合并前一致(等价性证据:同一 fixture 输入下事件数差为 0)。
- `tests/architecture/test_event_bus_authority_consistency.py` 三方一致性(yaml 授权 ⟺ manifest 声明 ⟺ 生产 `subscribe()`) 全过。
- `tests/plugins/observability/test_seam_replacement.py`(PR-7 新增) 可在 profile 替换五缝任一 provider 为 stub,行为变化可控。
- 7 个位置逃逸的 `@plugin` 迁入 `lca/plugins/` 后,PR-1 的位置门禁 0 违例;`lca_kernel/events/manifest.py` 是唯一例外(kernel 元插件,合法)。

## Risks

- **跨 ADR-0183 边界**:Pipeline yaml 形态由 ADR-0183 §3.3 规定(hooks/sinks 用类路径)。本文档 PR-5 提出 `plugin:` 字段与之共存,不破坏 ADR-0183 §2.2 边界面(bus 路由机制、Pipeline 编排权属、SinkBackend 协议等核心不变量不变),但改变了 yaml 数据的**实体引用语法**。如果评估判定这一改动跨 ADR-0183 边界,PR-5 应独立走 ADR 流程(本文档降级为 ADR 的 §A.2 索引)。预案:PR-1 + PR-4 先合,先不动 yaml 形态,把通道②③④的鉴权白名单从"裸类路径"过渡到"manifest 与 yaml 互校验",留 yaml 语法升级给后续 ADR。
- **PR-10 批改冲突面大**:104 个插件跨 6 个 domain 迁移,bundle `$module` 字符串集中修改,可能与同期其他 PR 产生大量 merge conflict。建议在低活动窗口合并,且分 3-4 个子批(`act/memory` → `collaboration/transport` → `observability/journal/state` → `think/gate/perceive`)分批合,每子批独立验证。
- **kernel 边界扩大风险**:事件 yaml 改为 id 引用后,registry 需要在装载期解析 id → class,这增加了内核装载负担。需在 `EventRegistry.load` 内做一次缓存(每 profile 一次,幂等);若性能不可接受,可降级为 lazy 解析。监控:`lca-ops runs create --user-text "ping"` 端到端启动时间 p95 退化 ≤ 5%。
- **PR-7 的 from_profile 重构**可能影响多 profile 的隐式兼容:web-app.yaml 的 `observability:` 段不存在,改造后若其他 profile 也有 `observability:` 段(grep 全文确认),需要同步迁移。建议在 PR-7 PR body 列出所有受影响 profile。
- **删除项的兼容性**:PR-3 删 6 个 scenario bundle + `orchestration_strategies/` + 4 个孤儿插件(`sub_composers`、`coding_agent_tools`);若有外部消费者(其他仓库 / 文档链接),需要提前公告。预案:每个删除在 PR 描述中提供"近期 14 天 `rg` 证据 = 0"作为删除门槛。
- **id 文法滚动收敛(PR-11)**成本不可见:存量 148 个 `lca-` id 全量改名会引发测试夹具 / 文档 / ADR 引用的连锁修改。建议**不强求 1 周期内完成**,而是 baseline 化后按需推进;若全量改名预算超出可接受范围,可降级为"`lca-` id 保留,新插件不再欠债" 的最小收敛。
- **门禁与现有违规的"零宽容"风险**:PR-1 直接扩展 5 维到现有 484 文件可能触发大量既有违规,导致 check 永远红。预案:PR-1 在新维度上以 baseline 形式记录违规(基线 JSON 包含每个新维度的当前值,后续 PR 负责单调下降),不是把 5 维直接提升到 hard 失败。

## Migration plan

- 本文档(PR-1 ~ PR-11)所有变更**每 PR 一个 merge commit**,遵循 Conventional Commits;每 PR 自带架构测试或脚本验证,不依赖后续 PR 状态。
- 升级到 `implemented/`:PR-1 合并时(`scripts/check_plugin_shape.py` 8 维生效且基线已存) 把本文档从 `proposed/seam/` 移至 `implemented/seam/`,`Status:` 改为 `implemented`,`## Proposal` 改写为现在时 `## Decision`,Acceptance 与 Risks 折叠为 `## Consequences` 与 `## Verification`。其余 PR 不需要单独的 note 升级(每 PR body 描述的验证与 delete-when 即足够);最后一个 PR(PR-11 的最后批次,或滚动结束) 再次同步本文档确认 acceptance criteria 全达成。
- 与既有 note 的关系:[`2026-09-03-plugin-shape-baseline.md`](../implemented/seam/2026-09-03-plugin-shape-baseline.md) 当时把 9 个孤儿 publisher 与 1 个 accumulator 标记为"由 ADR-0183 后续 PR 决定迁/删";本文档 PR-6 是该债的最终归属。[`2026-09-03-event-bus-chain-wired.md`](../implemented/seam/2026-09-03-event-bus-chain-wired.md) 落地了 sink 派发与 pipeline 装载;本文档 PR-5/PR-6 在其上做 yaml 形态升级,不重做其机制。[`2026-09-03-observation-ssot-registry.md`](../implemented/seam/2026-09-03-observation-ssot-registry.md) 的 9 条 lint 与 PR-1 的 5 维门禁并立,各自职责不同:observation 守的是 SSOT 字符串使用,plugin-shape 守的是插件形态。
- 与 ADR 的关系:ADR-0085 §1 的"Plugin = Setup + Manifest + Optional semantic address + Optional control contributions + Lifecycle/evidence/verification contract" 抽象与本文档 5 原则兼容(本文档是其在当前实现的形态收编);ADR-0115 kernel-transport 边界与本文档不交;ADR-0180/0183 事件总线机制由 PR-5/PR-6 在不改变 §2.2 边界面的前提下做 yaml 数据形态升级;若评估判定形态升级跨 ADR 边界,PR-5 需独立走 ADR 流程(见 Risks §跨 ADR-0183 边界)。