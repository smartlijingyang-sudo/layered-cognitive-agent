# LCA 极端插件化组织规范（相对 deepseek-harness）

> Status: **镜川 Keep（确认）** · ADR-**0189** Proposed（0187=AssistantAgent 已占用）· Phase B=skill · main · 2026-09-05
> Scope: 物理布局 + 缝契约 + 可替换/可调试隔离 · **不**改 Runtime 语义  
> Relates: ADR-0061/0068/0069/0074（插件声明）、0105（8/10/15）、DSH `packages/<group>/<pkg>/`、既有 `DSH-GAP-AUDIT.md`（事件总线/model_visible，非布局）

---

## 0. 一句话结论

**可替换 Contribution 极端插件化；物理按 seam 一贡献一包；kernel 闭集最小且不插件化；禁止胖域/上帝包。**  
LCA 已有「一切皆插件」的 *声明* 强度，但 `lca/plugins/<domain>/` 胖树让替换、调试、契约边界糊在一起。DSH 的价值不是「一插件一包」口号，而是 **Definition / Provider / Consumer 三角色分文件、注册是 effect、profile+bundle 拼装**。LCA 应对齐这套 *缝契约*，用 8/10/15 当分层硬门，而不是照搬目录名。

---



## 0.1 镜川门禁（2026-09-05）· Keep / Reject

**总判**：目标不是「每个 .py 都是插件」，而是 **可替换贡献皆插件 + 内核闭集最小 + 一贡献一包防膨胀**。DSH 极端插件化 Keep 精神；把 kernel 也插件化 = **Reject**。

### Keep · 必须是插件（可 Profile 替换）

一切 **Contribution**：Sensor / Reasoner / Gate / Tool Provider / Memory / Exporter / Deriver / Route / Skill overlay / Transport handler…

路径仍是：Protocol → Seam → Provider/Adapter → Registry → Plugin → Profile/Bundle。

新能力默认进 **独立包**（一插件一包），经 Manifest `provides/requires/layer/kind/effects`，禁止塞进「顺手旁边的大包」。

### Reject · 仍是 Kernel（G0，不可被普通 plugin 旁路）

- PlanCompiler / Resolve-Compile 语义
- Reducer（facts→state 提交）
- ExecutionKernel / 固定 control slots 解释
- ScopeKernel（grant 衰减、lease）
- EvidenceLedger 追加语义（backend 可换，append 语义不可换）
- 权威不变量：authority 只衰减、effect 只经 envelope、facts 只追加、plan 只在 safe boundary 修订
- **CommandEnvelope 窄门语义**（effect 只能经 envelope 出界；具体 AuthorizationPolicy 仍是插件）
- **Plugin Manifest / Contract 校验与单一 schema**（允许换 backend，不允许平行第二套 Manifest）

附注：SemanticLaw / 架构测试属 **G0 证明面**，不必卷入是否插件化争论。

### 包边界怎么切（防上帝包）

1. **按 contribution slot / seam 切包**，不按「目录熟人」或「一次 PR 改过哪些文件」切
2. **一插件一包**：一个 Manifest id = 一个可独立版本/测试/删除的包；共享代码进 `contracts` 或极薄 `*_api`，不进兄弟插件包
3. **替换测试**：卸载包 A、换包 B，CompiledRunPlan 仍能 boot → 才算真插件；测不了替换 = 假插件化（对齐 0076）
4. **膨胀红线**：单包出现第二 seam、或同时 owns 配置 SSOT + 世界 effect + 投影写盘 → 拆；文件行数只是症状
5. **分层契约**：`contracts/` 无行为类；plugin 包只依赖 contracts + 声明 requires；禁止 plugin→plugin 硬 import（只经 Context/Registry）

### 反上帝包（拒收信号）

- `loop_cursor` / `assistant` / `observability` 类「全家桶」继续吞 deriver+persistence+capture
- 「基础设施大包」里藏业务 gate
- 为方便把多个 Manifest 塞进同一安装单元且无法单独卸
- 平行 schema / 第二套 Plugin Manifest

## 0.2 探针短页（2026-09-05）· 业界对照

【短页】DSH Cordis「一切皆插件 / 一插件一包」vs 业界细粒度规范 → layered

**结论**：迁「一能力一包 + 静态 inject + profile 组合 + 可 dispose」；不迁「宿主内核与工具同特权同进程、无闸 npm 生态、把 spine/循环本身做成可热拔插件」。业界 Agent Plugins 1.0 是分发地板（skills+MCP），不是 DSH 级 harness 内核插件化。

| 能力 | 做法 | 可迁入点 | 不迁入 | 验证 |
|---|---|---|---|---|
| 组织粒度 | DSH：1 npm 包 = 1 cordis 插件（`apply(ctx,config)`/`Service`）+ `package.json` 的 `dsh.*`；bundle→profile→module 三层。业界 Agent Plugins 1.0：1 目录=`plugin.json`+可选 `skills/`+`mcp.json`（只打包扩展，不定义宿主）。Claude Code：plugin=分发袋（skills/hooks/MCP/agents），宿主仍有特权核。MCP：1 server 多 tool，进程隔离。 | **一能力一模块/包**作边界；分发单元与运行单元分离（类似 bundle vs profile） | 把 EP/spine/journal SSOT 做成与 tool 同级可热拔插件 | 增删一包不改 spine schema；`dump-config` 等价物可审计组合树 |
| 一切皆插件 | DSH：模型/工具/会话/沙箱/存储/循环/调度/UI 全 Cordis 叠出；第三方可替换内置。 | 边缘能力（tool/adapter/UI 投影）插件化；控制面留薄核 | 循环与真值层「也可被任意社区包替换」无门禁 | 关某插件后主循环仍可重放；替换 model adapter 不碰 journal |
| 依赖/能力边界 | DSH：`inject` 静态声明，未声明服务 Proxy 拒绝（capability）。Cordis：子 ctx + disposer，可逆副作用。 | 插件静态声明可读服务；卸载必 dispose；加载可审查 | 运行时任意拿全局；无 dispose 的上帝注册表 | 未 inject 访问必失败；unload 后无泄漏监听 |
| 组合/配置 | DSH：`cordis.patch.yml` 层叠（bundles→profile→home→overlays）；`dsh plugin` 用 pnpm reconcile `dsh.profile.bundles`。 | profile=有序组合清单；配置层可覆盖、可删 | 整行替换无 schema、静默 skip 当默认；根配置被重写成空却靠隐式层 | 同 profile 两次 reconcile 幂等；禁用一层可观测 |
| 安全/隔离 | DSH 社区观察：插件常同进程全权、无默认沙箱。MCP/多数 IDE：工具进程外。Agent Plugins：组件失败隔离，但权限属 client。 | 工具类插件默认侧车/沙箱；写盘/学习类要闸 | 同进程「一切皆插件」无沙箱当默认 | 恶意/崩溃插件不拖垮 harness；权限拒绝可测 |
| 生态粒度 | DSH：包爆炸（数百包、活跃少）。Agent Plugins/Claude：少而可移植的分发格式。 | 内部分包细、对外发布粗（能力族一包） | 一 tool 一 npm 公开包无策展 | 公开包数有策展门槛；内部模块可更细 |

**对 layered 迁移序**
1. P0：能力边界=包/模块 + 静态依赖声明 + dispose/删除条件（对齐薄控制×可插拔投影）
2. P1：profile 式有序组合（哪些投影/工具启用），不改 spine
3. P2：对外可选用 Agent Plugins 地板做 skills+MCP 分发互操作
4. 不做：spine/循环社区热拔；无沙箱同权插件；无闸自动装包

**可选下周一条**：列 layered「核 vs 可插件」清单（Keep 核 / Reject 插件化），对照 ADR 门禁。

来源：DSH 插件解剖 / publish、Cordis/Koishi 可逆插件、Agent Plugins 1.0、Claude Code plugins vs MCP。




## 0.3 终审自检维度（镜川 2026-09-05）· 写稿对照

| 维 | Keep | Reject | 本稿落点 |
|----|------|--------|----------|
| A 语义 vs 物理 | 可替换贡献皆插件；Def/Prov/Cons 不混 | Kernel 可 Profile 旁路；Def 藏执行 / Prov 改 grant / Cons 直写事实 | §0 / §0.1 / §3.1 / §4 |
| B 包与边界 | 一 Manifest=一可卸单元；按 seam 竖切；分裂条件可 CI/grep | 多 Manifest 同一不可分安装单元；plugin→plugin 硬 import | §0.1 / §3.2 / §7 / §9 |
| C 分阶段 | Phase A 门禁先于搬家；Phase B 一条竖切+替换测试 | Phase A 大搬家；Phase B 同时多条业务面 | §3.2 / §6 / §0.2 P0–P2 |
| D 既有缝 | 显式对齐 0061/0068/0069/0074/0076/0167/0178；删除条件可 grep | 平行 schema / 不留 follow-up 的 mega 搬家 | 本表下 §0.3.1 |
| E 文档形态 | 对照表 + 3～5 上帝包 + 诚实 follow-up 编号 | 「一次搬完」无 follow-up | §9 / §10 / §12 |

### 0.3.1 既有缝对齐（D）

| ADR | 对齐方式 |
|-----|----------|
| 0061 Manifest | 一 id = 一安装单元；provides/requires/layer/kind/effects |
| 0068 / 0069 Plan | 插件只贡献 seam；CompiledRunPlan 语义属 kernel，不插件化 |
| 0074 / 0076 | 替换测试精神：卸 A 装 B 仍 boot；测不了 = 假插件化 |
| 0167 | 真值/投影分离；Exporter/Deriver 可换，journal/spine SSOT 不热拔 |
| 0178 | assistant 若涉及：Catalog CRUD only；runtime opt-in bundle；禁胖域 |

### 0.3.2 可判定分裂条件（CI/grep 草案）

满足任一即必须拆包（Phase A 可先 warn）：

1. 单包装载 **≥2 个不同 contribution seam**（Manifest provides 计数）
2. 同包同时 owns **配置 SSOT + 世界 effect + 投影写盘**（符号/目录 ROLE 标注冲突）
3. **无法做替换测试**（没有第二 Provider 或 mock 端口）
4. plugin→plugin **硬 import**（非经 contracts/Registry）
5. （可选阈）单包 import 扇出或 LOC 超仓内分位数 — 仅作症状，不单独作为唯一依据

删除条件：旧胖包路径、平行 Manifest schema、shim 层均可 `rg` 定位，并写 delete-day。

## 1. 问题本质（第一性）

| 痛点 | 根因 | 非根因 |
|------|------|--------|
| 难替换 | 一个目录同时装定义、实现、适配、测试夹具 | 「包数量不够多」 |
| 难调试隔离 | 导入图把多个角色绑死；改 A 必拖 B | 「没 monorepo」 |
| 胖包恐惧 | 域树随功能横向膨胀，无分裂条件 | 「一插件必须一 npm 包」 |
| 契约不清 | 层间用「方便 import」穿透，无 Consumer 边界 | 「文档少」 |

**删除条件（本规范何时可废）：** 若 RuntimeFactory + ScopeKernel + Catalog 已强制「只经缝加载、无跨角色直 import」，且 CI 有 import-linter/dep-cruiser 门禁，本文件可降为附录。

---

## 2. DSH vs LCA（对照，不抄作业）

### 2.1 deepseek-harness（可迁入的缝）

- 布局：`packages/<group>/<pkg>/`，能力以包为边界。
- 缝：**Definition**（契约/类型）· **Provider**（实现）· **Consumer**（调用方只依赖 Definition）。
- 注册 = **effect**（组装期副作用），不是业务逻辑里 `if plugin_id`。
- 拼装：profile + bundle patches → 运行时视图。

### 2.2 layered-cognitive-agent（现状 · `main`）

- **声明强**：0061/0068/0069/0074 + 8/10/15（0105）已写清「插件一切」。
- **物理弱**：主体在 `lca/plugins/<domain>/` 胖树；顶层 `packages/` 几乎只有 `gateway-client`、`lca-cli`。
- **已有审计**：`DSH-GAP-AUDIT.md` 盯的是事件总线 / model_visible（0183–0185），**不是**包布局。

### 2.3 对齐策略

| 维度 | 对齐 DSH | 刻意不齐 |
|------|----------|----------|
| 三角色缝 | ✅ Definition / Provider / Consumer | — |
| 注册即 effect | ✅ Catalog/bundle 注册期 | — |
| profile+bundle | ✅ 已有 RuntimeFactory / bundle | — |
| 一插件一包 | 🎯 *目标态*，按分裂条件渐进 | ❌ 禁止「为拆而拆」空包 |
| `packages/<group>/` 目录名 | 可选迁移 | ❌ 不要求一夜搬空 `lca/plugins` |

---

## 3. 目标布局（规范）

### 3.1 逻辑单元（强制）

每个**可替换能力**拆成最多三个逻辑角色（可同仓不同目录，远期可不同包）：

```
<capability>/
  definition/     # 仅类型、协议、错误码、无 I/O
  provider/       # 唯一实现入口；依赖 definition + 允许的下层
  consumer/       # 可选；门面/适配；禁止回写 provider 私有符号
  tests/          # 按角色分；provider 测试不得 import 兄弟 provider 私货
```

**硬规则**

1. **Consumer 只依赖 Definition**（静态 import 门禁）。
2. **Provider 不得被其他 Provider 直 import**（经 Definition 或 Runtime 注入）。
3. **Definition 无副作用、无具体配置解析**（解析在 compile/resolve）。
4. **一个 Provider = 一个可替换单元**；调试时能单独 disable / mock 该单元。

### 3.2 物理演进（渐进，防胖包）

**Phase A（门禁，不搬目录）** — 立刻可做

- 文档化：每个 `lca/plugins/<domain>` 内标注角色边界（`# ROLE: definition|provider|consumer`）。
- CI：**至少 1 条** import-linter（或等价）对样板缝以 error/warn 进 CI；**仅 ROLE 注释不算门禁落地**。
- ADR 索引：本规范 → 建议编号 **0189**（**0187 已被 main AssistantAgent 占用**）（`main` README 已列到 ~0186；以仓库实际空号为准）。

**Phase B（样板缝）** — 选 1 条竖切

- **Phase B = skill**（耦合低、0048/overlay 清晰、易替换测试）。**llm → Phase B.2 / 0189.2b**。
- 抽出 `definition` 到独立目录（或 `packages/lca-skill-definition`）。
- Provider 保留原路径或迁 `packages/lca-skill-provider-*`；Consumer 只改 import。
- **Reject**：Phase B 同时拆 §10 五个上帝包。

**Phase C（域树瘦身）**

- **分裂条件 SSOT = §0.3.2**（任一触发即拆）；本节不另立清单，仅举例：版本分叉、多 Consumer、常 mock 可作为辅助信号并入 §0.3.2 第 5 条。
- **禁止分裂**：纯内部 helper、仅一处调用的胶水、未稳定的实验缝。

### 3.3 推荐 monorepo 形状（目标态示意）

```
packages/
  lca-kernel/              # 极薄：加载、注入、Scope、错误轴（无业务域）
  lca-<cap>-definition/    # 每能力一份契约
  lca-<cap>-provider-<impl>/
  gateway-client/          # 已有
  lca-cli/                 # 已有
lca/
  plugins/                 # 过渡期：未拆完的域；新代码禁止再胖长
bundles/
  web-standard/
  assistant-runtime/       # 与 ADR-0178 一致，opt-in
```

Kernel **禁止**变胖：业务能力只进 provider；kernel 只做组装与权限衰减。
禁止把 Deriver/Exporter 塞进 lca-kernel 包。

---

## 4. 层契约（8 / 10 / 15 + 三角色）

沿用 0105，叠三角色：

| 层 | 允许依赖 | 禁止 |
|----|----------|------|
| Definition | 标准库 + 更底层 definition | Provider、IO、具体插件 id |
| Provider | 本能力 definition + 下层 Provider（经注入） | 同层兄弟私有模块、上层 UI |
| Consumer / Bundle | Definition + Runtime API | Provider 内部路径 |
| Kernel / Factory | 注册表、Definition | 业务 Provider 实现细节 |

**调试隔离清单（每次替换必过）**

1. 关掉该 Provider 注册 → 运行时明确失败（非静默 fallback，除非 ADR 写明）。
2. Mock 只替换 Definition 端口 → Consumer 行为可测。
3. Spine/日志带 `plugin_id` / `provider_id`，不把技能正文打进 spine（对齐 0178 / 探针建议）。

---

## 5. 与「害怕胖包」的和解

- **胖的是「多角色糊在一个目录」**，不是「包字节大」。
- **新 Contribution 默认一插件一包**（Manifest 可独立卸）。分裂条件（§0.3.2）管的是**既有胖包何时必须拆**，不是放松「新能力塞进旁边大包」。annotation + 门禁只覆盖尚未触发分裂红线的过渡态。
- Bundle 继续做「产品拼装」；包做「替换与调试边界」。两者正交：一个 bundle 可挂多个 provider；一个 provider 可进多个 bundle。

---

## 6. 落地建议（`main`）

1. **本周 / P0**：本文件进 PR（`docs/specs/extreme-plugin-organization.md` 或 ADR-0189）；能力边界=包 + 静态依赖声明 + dispose；Phase A 门禁矩阵 CI warn。
2. **下周 / P1→B**：profile 式组合不改 spine；**Phase B = skill**（须替换测试；异议再改）；llm = **Phase B.2**；P2 对外 Agent Plugins 地板可选后置。
3. **并行**：ADR-0178 AssistantAgent 仍只加文档；`web-standard` 不动；GitHub 重连后 PR → `main`。
4. **不做什么**：不重开 `back-ui-821-other-keep`；不覆盖 `0169-loop-cursor-control`；不为了目录好看全仓大搬迁。

---

## 7. 决策表（可判定）

| 提议 | Do | Don't |
|------|----|-------|
| 新能力 | 先写 Definition + 注册 effect | 直接在域树里堆函数 |
| 想拆包 | 对照 §3.2 分裂条件 | 「看起来乱就拆」 |
| 跨插件调用 | 经 Definition / 注入 | `from lca.plugins.x._impl import` |
| 调试某能力 | disable 该 provider 注册 | 改全局 flag 绕过 |
| 对齐 DSH | 三角色 + effect 注册 | 复制 packages 目录名当 KPI |

---

## 8. 开放问题（交给镜川 / 探针）

1. Phase B：**= skill**（镜川 Keep）；llm → Phase B.2 / 0189.2b。
2. import 门禁工具：import-linter vs 自研 AST（与现有 CI 契合度）
3. ~~ADR 号 0187 空号？~~ **已核：0187=AssistantAgent（Accepted）；本规范用 0189**（0188=session title）。

---

*End of draft · owner: 山姆 · review: 镜川（架构） / 探针（业界对照可选）*


## 9. 对照表（DSH × layered · 可验证）

| DSH 做法 | layered 现状缺口 | Keep 迁入 | Reject 不迁 | 验证 |
|----------|------------------|-----------|-------------|------|
| 一贡献一包 + Manifest | `lca/plugins/<domain>/` 胖树；多 seam 同包 | 新 Contribution 独立包 + Manifest provides/requires | 不为拆而拆空包 | grep Manifest id；包可单独 pip/uv 卸 |
| Definition/Provider/Consumer | 角色糊在同目录 | ROLE 标注 → contracts + provider 包 | Kernel 不做 Consumer 旁路 | import-linter；禁止 plugin→plugin |
| 注册即 effect | 业务里偶发 plugin_id 分支 | Registry/Profile 注册期 effect | 运行中热改 PlanCompiler 语义 | 替换测试：卸 A 装 B 仍 boot |
| Profile + bundle 拼装 | 有 RuntimeFactory/bundle，物理边界弱 | Bundle 只拼装，不拥有第二 seam | 平行第二套 Manifest schema | 单 Manifest schema grep |
| 可替换贡献 | 假插件：卸不掉/mock 不了 | 替换测试门禁（0076 精神） | Kernel 闭集条目不可换语义 | CI：CompiledRunPlan boot after swap |

每条 Keep 迁入的 **删除条件**：旧胖目录内不再出现第二 seam 的实现符号（可 grep）；对应 Manifest 可独立卸载。

---

## 10. 上帝包候选（点名 · 镜川 Keep 2026-09-05）

基于反上帝包信号 + main 现状，优先拆这 5 个（调研级点名，落地前再对路径）：

1. **`loop_cursor` / Loop 控制全家桶** — 若仍吞 deriver + persistence + capture + 投影：拆成 **薄控制状态机（runtime 可信缝，对齐 0169；不是 G0 Kernel）** × 可插拔 Deriver/Projection plugins（对齐 0168 Conditional Go）。
2. **`observability` / logging 捕获全家桶** — capture + sink + 投影写盘同包 → 按 Exporter/Deriver/Sensor 切；SSOT 语义留 0167，实现可换。
3. **assistant 相关域 — Keep 预警** — 0178 未落地前：**禁止萌芽成胖域**（配置 SSOT + effect + UI 同树）。对齐 0178：Catalog CRUD only，runtime opt-in bundle。勿暗示 main 上已有必拆大树。
4. **`llm` 或 model 调用胖包** — Provider + route + 业务 gate 同装：Gate/Route 独立 Manifest；contracts 只留协议。
5. **`skill` 执行/安装胖包** — overlay + install + evolve + 持久化同目录：Skill overlay 一包；install/evolve 经 0067 Creator 门，不进兄弟私货。

可选 P2（不强制进 Top5）：`gateway/runs`（loop_drivers + 投影泄漏）——若 main 上比 assistant 更实，可与 #3 对调「现存胖」优先级。

**拒收**：继续把多个 Manifest 塞进同一安装单元且无法单独卸。

---

## 11. 修订相对原稿

- 原「语义极端 / 物理三角色」保留，但 **明确 kernel 闭集不插件化**（镜川 Reject）。
- 「一插件一包」从软目标升为 **Contribution 默认**；分裂条件改为膨胀红线（第二 seam / SSOT+effect+投影同包）。
- Phase A 仍不搬目录，但验收加上 **替换测试草案**（可先 warn）。
- Phase B 样板缝 = skill（能演示「卸 A 换 B 仍 boot」）；llm → Phase B.2。


## 11.1 镜川 Conditional Keep 硬改

本轮硬改摘要（Conditional Keep）：

1. Kernel 闭集补充 **CommandEnvelope** 窄门与 **单一 Manifest schema**；SemanticLaw/架构测试属 G0 证明面，不卷入插件化争论。
2. `loop_cursor` thin control SM = **runtime 可信缝对齐 0169，不是 G0 Kernel** × 可插拔 Deriver/Projection（0168）；禁止「kernel 侧」误称。
3. `assistant`：**Keep 预警** — 0178 未落地前禁止萌芽成胖域；Catalog CRUD only + opt-in bundle。
4. §10 可选 P2：gateway/runs 可与 #3 对调「现存胖」优先级。
5. **Phase B = skill**；llm → Phase B.2 / 0189.2b。
6. §3.2 **分裂条件（统一 · 任一触发即拆）** 与膨胀红线对齐。
7. Phase A：**仅 ROLE 注释不算门禁落地**；样板缝至少 1 条 import-linter（或等价）error/warn 进 CI。
8. 禁止把 Deriver/Exporter 塞进 `lca-kernel` 包。


## 12. Follow-ups（诚实编号 · 禁止 mega 一次搬完）

| 编号（建议） | 内容 | 依赖 |
|--------------|------|------|
| **ADR-0189** | 本规范正文（语义极端插件化 + 物理 seam 包 + kernel 闭集 + Phase A/B） | **0189 已核空号** |
| 0189.1 | Phase A 门禁：import-linter 矩阵 + 替换测试骨架 + 胖包 warn 规则 | 0189 Keep |
| 0189.2 | Phase B = **skill** 竖切（卸 A 装 B）；llm → **0189.2b** | 0189.1 |
| 0189.3 | 上帝包拆分清单落地（从 §10 候选逐个 RFC，非一次 PR） | 0189.2 验证方法 |
| 0189.4 | P2 可选：对外 Agent Plugins 地板（skills+MCP 分发） | 非阻塞；P0/P1 后 |

定稿前：**0189 已核空号**（0187=AssistantAgent）；若后再撞则顺延，不硬占。

## 附录 A. 核 vs 可插件清单（占位 · 并进 ADR-0189）

> 来源：探针 §0.2「可选下周」+ 镜川 Keep。正式条目以 §0.1 Kernel 闭集 = 核、Contribution = 可插件为准；本附录在升 ADR 时展开对照既有 ADR，不另开文。

| 核（G0 / 不可 Profile 旁路） | 可插件（Contribution） |
|------------------------------|------------------------|
| PlanCompiler / Resolve-Compile | Sensor / Reasoner / Gate |
| Reducer | Tool Provider / Memory |
| ExecutionKernel / control slots | Exporter / Deriver / Route |
| ScopeKernel | Skill overlay / Transport |
| EvidenceLedger append 语义 | AuthorizationPolicy（策略可换） |
| CommandEnvelope 窄门 | 具体 adapter / UI 投影 |
| 单一 Manifest schema 校验 | Profile/Bundle 组合内容 |

## 11.2 Conditional Keep checklist 再修（同日）

- §3.2 分裂条件改为指向 §0.3.2 SSOT，消灭双标准
- §5：新 Contribution 默认一包；分裂条件只约束既有胖包何时拆
- Phase B：默认 skill（异议再改）；非用户点名亦不 Reject 整篇
- Envelope / Manifest / §10#1 runtime 缝：维持已改状态
