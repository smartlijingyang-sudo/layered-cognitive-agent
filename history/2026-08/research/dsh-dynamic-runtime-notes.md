# DSH 动态运行时研究笔记

**日期：** 2026-08-21
**用途：** 为 LCA 声明式插件宪法 v4 的动态创造与时空架构补充提供可追溯输入；本文件只记录已核验事实与待核验问题。

## 已核验的官方表述

官方开发者预览页面将 DeepSeek Harness 定位为基于 Cordis 的插件运行时：模型、工具、技能、会话、沙箱、存储、循环、调度与 UI 都可作为插件被选择、替换或重组。Cordis 内核负责插件挂载、卸载和依赖关系；官方强调开发者可通过配置扩展能力而不修改 Harness 源码。[1]

官方页面同时说明，每次运行的模型可见输入、推理、工具调用、子代理调度与上下文注入写入 append-only session log，resume、fork、search 和 replay 使用同一事件流。Creator mode 被定义为：检查当前运行时、在内存中试验 Cordis 插件、并把它们组合成新模式。[1]

## 文档访问结果

官方文档导航入口为 `https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart`。推测的 `/en/guide/creator` 路径返回 404，因此不能将该路径作为引用；后续应从官方导航或仓库源码定位准确的 Creator / Cordis 文档页面。

## 对 LCA 的初步启发（待设计验证）

LCA 可吸收的不是无约束 runtime mutation，而是以下三项能力：其一，运行时可检查的已解析插件树；其二，在隔离 staging 空间内加载、试验、验证和比较候选插件；其三，将验证通过的能力以显式、可回滚、带授权和证据的方式提升到指定 scope。LCA 应保留现有认知闭集、Control Slot、capability 衰减、Journal 事实来源和执行窄门，不把 Creator 权限扩张为任意 hook 或任意进程内代码执行。

## 待核验问题

1. DSH / Cordis 关于 `space` 与 `time` 的正式定义、数据模型和 lifecycle 语义。
2. Creator 的具体工具接口、mount / unmount / inspect 行为及持久化边界。
3. Cordis Fiber 在动态装卸时的依赖等待、effects、dispose 与失败恢复保障。
4. DSH 对 runtime 修改的开发体验限制：类型、配置、调试、依赖与回滚方面的具体问题。

## 参考

[1]: https://deepseek.com/harness/en/ "DeepSeek Harness developer preview: Everything is a plugin"

## 官方插件开发与生命周期资料

官方“Your first plugin”文档定义 DSH 插件为导出 `apply(ctx)` 的 TypeScript 模块。它可以在加载时通过 `ctx` 注册能力；以配置 overlay 的 `insert` 条目加载本地插件。插件可声明 `inject` 依赖，框架会在所有依赖服务就绪后再调用 `apply`。经 `ctx` 注册的事件监听、工具或定时器会随卸载自动清理；需要显式释放的网络连接等资源则通过 `ctx.effect()` 返回 disposer，并在卸载时执行。[2]

文档侧边栏明确包含“Plugin lifecycle”“Services and dependencies”“Event system”以及 Cordis 教程中的“Composition and HMR”章节，表明动态组合与热模块替换是官方框架的正式开发主题。官方入门示例同时暴露了开发体验代价：插件最小表面只是一段可操作 `ctx` 的 `apply` 代码，配置通过绝对路径进行 overlay 插入；业务能力、依赖、效果、控制归属和运行期权限并不会在该最小表面中被强制结构化表达。[2]

## 对 LCA 的新增设计约束

LCA 应保留 Cordis / Fiber 的“依赖就绪后加载、effect 归属、卸载时逆向清理”能力，但不把任意 `ctx` 读写视为 LCA 插件的架构 API。动态候选插件必须先被解析为 Manifest、Control Slot、capability、effect、authority、evidence 和测试声明；只有通过 staging 验证后，才可以被提升到 run / agent / profile scope。绝对本地路径、隐式 global context、自由事件和不可追溯 overlay 都不能成为生产动态修改的事实来源。

## 参考（续）

[2]: https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/ "DeepSeek Harness: Your first plugin"

## 官方 HMR、Fiber 与动态创造的关键事实

Cordis 的配置项以稳定 `id` 区分编辑、删除和新增；`disabled: true` 可卸载既有插件而保留其配置项，重新启用时该插件以及等待其服务的插件可以再次加载。group 可以一起加载 / 卸载子列表，`isolate` 可使不同 group 看到彼此隔离的同名 service 实例。HMR 通过卸载旧插件并重新加载新代码实现；旧实例 effects 被释放，依赖驱动装载重新满足后执行新 `apply`。[3]

Cordis 官方生命周期状态为 `PENDING → LOADING → ACTIVE`，异常可进入 `FAILED`，已激活插件则经 `UNLOADING → DISPOSED` 退出。`inject` 依赖在全部服务 ready 前保持 PENDING；provider 在替换期间消失会使依赖插件自动卸载，provider 返回后再加载。Plugin 注册的 listener、tool、adapter 和 effect 都随 Fiber 自动清理；child Fiber 从父 Context 继承环境但拥有独立 lifecycle，父插件卸载时递归清理。[4]

官方 DSH 动态 Cordis 工具区分 `inspect`、`define`、`run`、`stop`、`undefine`。`define` 仅记录并语法预检，`run` 才产生 effect；host-only 包在 vm 中运行，带 browser half 的包要求真人页面允许。动态包的定义和活动范围限定在进程内存、定义它的 session 可见性和明确的 stop / undefine 生命周期；不会自动写入配置或跨重启恢复。官方同时明确 vm sandbox 不是安全边界，动态包应按 bash 级别信任处理。[5] [6]

## 对 LCA 的设计结论

LCA 应吸收三个可验证机制：稳定实例 ID 的 diff、隔离 child scope / Fiber 的 effect 生命周期、以及 `define → validate → stage → activate → quiesce → retire` 的显式状态机。LCA 不应直接照搬 DSH 的自由 `apply(ctx)` 和 process-memory 动态包模型：它们对实验很快，但不能单独保证静态类型、Control Slot 合法性、Journal 完整性、权限单调性、可恢复性、跨运行可重放或生产发布审查。LCA 的动态运行时应把 DSH 动态包降为“候选能力”，只有通过 Manifest / Plan / grant / evidence / test gates 后才进入可影响认知或执行的 scope。

## 参考（续）

[3]: https://deepseek-harness.github.io/deepseek-harness/en/develop/cordis-tutorial/06-composition-and-hmr "DeepSeek Harness: Composition and HMR"
[4]: https://deepseek-harness.github.io/deepseek-harness/en/develop/framework/ "DeepSeek Harness: Plugins and lifecycle"
[5]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/extensions/tool-cordis "DSH tool-cordis source and README"
[6]: https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/extensions/cordis-host-runner "DSH cordis-host-runner source and README"
